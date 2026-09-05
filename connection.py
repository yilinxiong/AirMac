"""Authenticated, transport-neutral AirMac client connection handling."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from typing import Protocol

from pydantic import ValidationError

from airmac_version import AIRMAC_VERSION
from protocol import (
    HEARTBEAT_INTERVAL_MS,
    PROTOCOL_VERSION,
    SUPPORTED_PROTOCOL_VERSIONS,
    AuthenticateMessage,
    AuthFailedMessage,
    AuthOkMessage,
    ErrorMessage,
    HeartbeatAckMessage,
    ProtocolLimits,
    ServerMessage,
    TypeTextAction,
    TypeTextResultMessage,
    parse_server_message,
)
from sessions import ActiveSession, SessionRegistry
from transport import ClientTransport, TransportDisconnected


logger = logging.getLogger("AirMac")
SERVER_CAPABILITIES = [
    "typed_server_messages",
    "text_projection",
    "quick_deck",
    "audio_switching",
]


class DeviceStoreProtocol(Protocol):
    def authenticate(self, device_id: str, token: str) -> bool: ...

    def touch(self, device_id: str, min_interval_seconds: float = 60.0) -> bool: ...


class ControllerProtocol(Protocol):
    async def wake_if_display_asleep(self) -> bool: ...

    async def dispatch(self, action: object, notify: object) -> bool: ...


class AuthFailureLimiter:
    def __init__(self, limit: int = 10, window_seconds: float = 60.0) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.failures: dict[str, deque[float]] = defaultdict(deque)
        self.lock = asyncio.Lock()

    async def is_limited(self, peer: str) -> bool:
        async with self.lock:
            attempts = self._current(peer, time.monotonic())
            return len(attempts) >= self.limit

    async def record_failure(self, peer: str) -> None:
        async with self.lock:
            now = time.monotonic()
            attempts = self._current(peer, now)
            attempts.append(now)

    async def clear(self, peer: str) -> None:
        async with self.lock:
            self.failures.pop(peer, None)

    def _current(self, peer: str, now: float) -> deque[float]:
        cutoff = now - self.window_seconds
        for key in list(self.failures):
            attempts = self.failures[key]
            while attempts and attempts[0] <= cutoff:
                attempts.popleft()
            if not attempts:
                del self.failures[key]
        return self.failures[peer]


class ConnectionHandler:
    def __init__(
        self,
        device_store: DeviceStoreProtocol,
        controller: ControllerProtocol,
        sessions: SessionRegistry,
        *,
        auth_timeout: float = 5.0,
        auth_limiter: AuthFailureLimiter | None = None,
    ) -> None:
        self.device_store = device_store
        self.controller = controller
        self.sessions = sessions
        self.auth_timeout = auth_timeout
        self.auth_limiter = auth_limiter or AuthFailureLimiter()
        self.tasks: set[asyncio.Task] = set()
        self.last_disconnect_category: str | None = None

    async def close(self) -> None:
        tasks = tuple(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def handle(self, transport: ClientTransport) -> None:
        task = asyncio.create_task(self._handle(transport), name="airmac-connection")
        try:
            await task
        except asyncio.CancelledError:
            if asyncio.current_task().cancelling():
                raise

    async def _handle(self, transport: ClientTransport) -> None:
        task = asyncio.current_task()
        self.tasks.add(task)
        claimed = False
        session: ActiveSession | None = None
        try:
            if await self.auth_limiter.is_limited(transport.peer):
                await transport.send(ErrorMessage(code="authentication_rate_limited"))
                await transport.close(4012, "authentication_rate_limited")
                return
            try:
                first_message = await asyncio.wait_for(
                    transport.receive(), timeout=self.auth_timeout
                )
            except asyncio.TimeoutError:
                await self.auth_limiter.record_failure(transport.peer)
                logger.warning("Connection authentication timeout client=%s", transport.peer)
                await transport.close(4008, "authentication_timeout")
                return
            except (ValidationError, ValueError):
                await self._reject_authentication(transport)
                return
            if not isinstance(first_message, AuthenticateMessage):
                await self._reject_authentication(transport)
                return
            if first_message.protocol_version not in SUPPORTED_PROTOCOL_VERSIONS:
                logger.info(
                    "Unsupported protocol client=%s version=%s",
                    transport.peer,
                    first_message.protocol_version,
                )
                await transport.send(ErrorMessage(code="unsupported_protocol"))
                await transport.close(4011, "unsupported_protocol")
                return
            try:
                authenticated = await asyncio.to_thread(
                    self.device_store.authenticate,
                    first_message.device_id,
                    first_message.token,
                )
            except Exception:
                logger.exception("Unable to read the paired-device database")
                await transport.close(1011, "credential_store_unavailable")
                return
            if not authenticated:
                logger.warning(
                    "Connection authentication failed client=%s device=%s",
                    transport.peer,
                    first_message.device_id,
                )
                await self._reject_authentication(transport)
                return
            await self.auth_limiter.clear(transport.peer)

            session = ActiveSession(first_message.device_id, transport)
            if not await self.sessions.claim(session):
                logger.info(
                    "Controller busy client=%s device=%s",
                    transport.peer,
                    first_message.device_id,
                )
                await transport.send(ErrorMessage(code="controller_busy"))
                await transport.close(4009, "controller_busy")
                return
            claimed = True
            try:
                await asyncio.to_thread(self.device_store.touch, session.device_id)
            except Exception:
                logger.exception("Unable to update last_seen device=%s", session.device_id)
            await transport.send(self._auth_ok(first_message, session))
            logger.info(
                "Client connected session=%s client=%s device=%s",
                session.session_id,
                transport.peer,
                first_message.device_id,
            )
            try:
                await self.controller.wake_if_display_asleep()
            except Exception:
                logger.exception(
                    "Unable to check display sleep state session=%s device=%s",
                    session.session_id,
                    session.device_id,
                )

            async def notify(payload: ServerMessage | dict[str, object]) -> None:
                payload = parse_server_message(payload)
                if isinstance(payload, dict):
                    payload_type = payload.get("type")
                    payload_action = payload.get("action")
                    request_id = payload.get("request_id")
                    status = payload.get("status")
                else:
                    payload_type = payload.type
                    payload_action = getattr(payload, "action", None)
                    request_id = getattr(payload, "request_id", None)
                    status = getattr(payload, "status", None)
                if (
                    payload_type == "action_result"
                    and payload_action == "type_text"
                    and isinstance(request_id, str)
                ):
                    if status == "ok":
                        await self.sessions.record_projection(session.device_id, request_id)
                    elif status == "error":
                        try:
                            session.projection_ids.remove(request_id)
                        except ValueError:
                            pass
                async with session.send_lock:
                    if await self.sessions.is_active(session):
                        await asyncio.wait_for(transport.send(payload), 5)

            while True:
                try:
                    message = await transport.receive()
                except (ValidationError, ValueError):
                    logger.warning(
                        "Rejected invalid message session=%s client=%s device=%s bytes=%s",
                        session.session_id,
                        transport.peer,
                        session.device_id,
                        transport.last_message_size,
                    )
                    await notify(ErrorMessage(code="invalid_message"))
                    continue
                session.last_activity = time.monotonic()
                if not await self.sessions.is_active(session):
                    await transport.close(4010, "replaced")
                    return
                if isinstance(message, AuthenticateMessage):
                    await notify(ErrorMessage(code="invalid_message"))
                    continue
                if message.action == "heartbeat":
                    await notify(HeartbeatAckMessage())
                    continue
                if isinstance(message, TypeTextAction):
                    if (
                        message.request_id in session.projection_ids
                        or await self.sessions.projection_completed(
                            session.device_id, message.request_id
                        )
                    ):
                        await notify(
                            TypeTextResultMessage(
                                request_id=message.request_id,
                                status="duplicate",
                            )
                        )
                        continue
                    session.projection_ids.append(message.request_id)
                if not await self.sessions.dispatch(session, message, notify):
                    logger.warning(
                        "Input queue full session=%s action=%s device=%s",
                        session.session_id,
                        message.action,
                        session.device_id,
                    )
                    if isinstance(message, TypeTextAction):
                        try:
                            session.projection_ids.remove(message.request_id)
                        except ValueError:
                            pass
                        await notify(
                            TypeTextResultMessage(
                                request_id=message.request_id,
                                status="error",
                                code="queue_full",
                            )
                        )
                    else:
                        await notify(ErrorMessage(code="queue_full"))
        except TransportDisconnected as exc:
            self.last_disconnect_category = disconnect_category(exc.code)
            logger.info(
                "Client disconnected session=%s client=%s device=%s code=%s reason=%s",
                session.session_id if session else "-",
                transport.peer,
                session.device_id if session else "unauthenticated",
                exc.code,
                exc.reason or "-",
            )
        except asyncio.CancelledError:
            if session and session.closing:
                self.last_disconnect_category = "server_closed"
            raise
        finally:
            try:
                if session is not None:
                    await self.sessions.release(transport)
            finally:
                self.tasks.discard(task)

    async def _reject_authentication(self, transport: ClientTransport) -> None:
        await self.auth_limiter.record_failure(transport.peer)
        await transport.send(AuthFailedMessage())
        await transport.close(4003, "authentication_failed")

    @staticmethod
    def _auth_ok(
        authentication: AuthenticateMessage, session: ActiveSession
    ) -> AuthOkMessage:
        if authentication.protocol_version < PROTOCOL_VERSION:
            return AuthOkMessage()
        return AuthOkMessage(
            protocol_version=PROTOCOL_VERSION,
            server_version=AIRMAC_VERSION,
            session_id=session.session_id,
            capabilities=SERVER_CAPABILITIES,
            heartbeat_interval_ms=HEARTBEAT_INTERVAL_MS,
            limits=ProtocolLimits(),
        )


def disconnect_category(code: int) -> str:
    if code == 4002:
        return "client_background"
    if code in {1000, 1001}:
        return "normal"
    if code == 1005:
        return "mobile_suspend_or_ungraceful"
    if code == 4003:
        return "device_revoked"
    if code == 4004:
        return "idle_timeout"
    if code == 4010:
        return "replaced"
    return "network_or_abnormal"
