"""Transport-neutral controller session ownership and idempotency state."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from typing import Protocol

from transport import ClientTransport, TransportDisconnected


logger = logging.getLogger("AirMac")


class ResettableController(Protocol):
    async def reset(self) -> None: ...


@dataclass
class ActiveSession:
    device_id: str
    transport: ClientTransport
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    last_activity: float = field(default_factory=time.monotonic)
    projection_ids: deque[str] = field(default_factory=lambda: deque(maxlen=128))
    closing: bool = False
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    owner: asyncio.Task | None = field(default_factory=asyncio.current_task)


class IdempotencyCache:
    """Bounded monotonic TTL cache for completed request identifiers."""

    def __init__(self, ttl_seconds: float = 600.0, max_entries: int = 1_024) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self.entries: OrderedDict[tuple[str, str], float] = OrderedDict()

    def record(self, device_id: str, request_id: str, now: float | None = None) -> None:
        current = time.monotonic() if now is None else now
        self._prune(current)
        key = (device_id, request_id)
        self.entries.pop(key, None)
        self.entries[key] = current
        while len(self.entries) > self.max_entries:
            self.entries.popitem(last=False)

    def contains(self, device_id: str, request_id: str, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        self._prune(current)
        return (device_id, request_id) in self.entries

    def _prune(self, now: float) -> None:
        cutoff = now - self.ttl_seconds
        while self.entries:
            _, completed_at = next(iter(self.entries.items()))
            if completed_at >= cutoff:
                break
            self.entries.popitem(last=False)


class SessionRegistry:
    def __init__(self, controller: ResettableController, idle_timeout: float) -> None:
        self.controller = controller
        self.idle_timeout = idle_timeout
        self.active: ActiveSession | None = None
        self.lock = asyncio.Lock()
        self.transition_lock = asyncio.Lock()
        self.completed_projections = IdempotencyCache()

    async def claim(self, session: ActiveSession) -> bool:
        async with self.transition_lock:
            return await self._claim(session)

    async def _claim(self, session: ActiveSession) -> bool:
        old_session: ActiveSession | None = None
        async with self.lock:
            if self.active and self.active.device_id != session.device_id:
                age = time.monotonic() - self.active.last_activity
                if age <= self.idle_timeout:
                    return False
            old_session = self.active
            self.active = None
        await self.controller.reset()
        async with self.lock:
            self.active = session
        if old_session and old_session.transport is not session.transport:
            try:
                if old_session.device_id == session.device_id:
                    await asyncio.wait_for(old_session.transport.close(4010, "replaced"), 1)
                else:
                    await asyncio.wait_for(old_session.transport.close(4004, "idle_timeout"), 1)
            except (TransportDisconnected, TimeoutError):
                pass
            finally:
                if old_session.owner and old_session.owner is not asyncio.current_task():
                    old_session.owner.cancel()
        return True

    async def release(self, transport: ClientTransport) -> None:
        async with self.transition_lock:
            await self._release(transport)

    async def _release(self, transport: ClientTransport) -> None:
        should_reset = False
        async with self.lock:
            if self.active and self.active.transport is transport:
                self.active = None
                should_reset = True
        if should_reset:
            await self.controller.reset()

    async def snapshot(self) -> ActiveSession | None:
        async with self.lock:
            return self.active

    async def is_active(self, session: ActiveSession) -> bool:
        async with self.lock:
            return self.active is session

    async def dispatch(self, session: ActiveSession, message, notify) -> bool:
        async with self.transition_lock:
            if not await self.is_active(session):
                raise TransportDisconnected(4010, "replaced")
            return await self.controller.dispatch(message, notify)

    async def disconnect(self, session: ActiveSession, code: int, reason: str) -> None:
        session.closing = True
        try:
            await asyncio.wait_for(session.transport.close(code, reason), 0.25)
        except (TransportDisconnected, TimeoutError):
            pass
        finally:
            if session.owner and session.owner is not asyncio.current_task():
                session.owner.cancel()
            await self.release(session.transport)

    async def record_projection(self, device_id: str, request_id: str) -> None:
        async with self.lock:
            self.completed_projections.record(device_id, request_id)

    async def projection_completed(self, device_id: str, request_id: str) -> bool:
        async with self.lock:
            return self.completed_projections.contains(device_id, request_id)

    async def monitor(self, device_store: object, interval: float) -> None:
        while True:
            await asyncio.sleep(interval)
            session = await self.snapshot()
            if session is None or session.closing:
                continue
            idle_seconds = time.monotonic() - session.last_activity
            if idle_seconds > self.idle_timeout:
                session.closing = True
                logger.info(
                    "Closing idle session session=%s device=%s idle_seconds=%.1f",
                    session.session_id,
                    session.device_id,
                    idle_seconds,
                )
                await self.disconnect(session, 4004, "idle_timeout")
                continue
            try:
                authorized = await asyncio.to_thread(
                    getattr(device_store, "contains"), session.device_id
                )
            except Exception:
                logger.exception("Unable to read the paired-device database")
                continue
            if not authorized:
                session.closing = True
                logger.warning(
                    "Disconnecting revoked device session=%s device=%s",
                    session.session_id,
                    session.device_id,
                )
                await self.disconnect(session, 4003, "device_revoked")
