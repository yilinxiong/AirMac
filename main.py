from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import os
import socket
import time
import uuid
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from starlette.websockets import WebSocketDisconnect

from auth import (
    DeviceStore,
    PairingBusy,
    PairingError,
    PairingInvalid,
    PairingManager,
    PairingRateLimited,
)
from mac_controller import MacController
from protocol import TypeTextAction, parse_action_message, parse_auth_message


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d %(levelname)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("AirMac")
PROJECT_DIR = Path(__file__).resolve().parent
PORT = 8000
PWA_ICONS = {
    "apple-touch-icon.png",
    "icon-192.png",
    "icon-512.png",
    "icon-maskable-512.png",
}
AUTH_TIMEOUT_SECONDS = 5.0
SESSION_IDLE_TIMEOUT_SECONDS = 16.0
SESSION_MONITOR_INTERVAL_SECONDS = 1.0
METRICS_LOG_INTERVAL_SECONDS = 30.0
EVENT_LOOP_LAG_WARNING_SECONDS = 0.1
ALLOWED_NETWORKS = tuple(
    ipaddress.ip_network(network)
    for network in (
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "127.0.0.0/8",
        "::1/128",
        "fc00::/7",
        "fe80::/10",
    )
)


def get_local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
            connection.connect(("8.8.8.8", 80))
            return str(connection.getsockname()[0])
    except OSError:
        return "127.0.0.1"


def is_allowed_ip(ip_string: str) -> bool:
    try:
        address = ipaddress.ip_address(ip_string.split("%", 1)[0])
    except ValueError:
        return False
    return any(address in network for network in ALLOWED_NETWORKS)


def is_allowed_origin(websocket: WebSocket) -> bool:
    origin = websocket.headers.get("origin")
    host = websocket.headers.get("host")
    if not origin or not host:
        return False
    parsed = urlsplit(origin)
    return parsed.scheme in {"http", "https"} and parsed.netloc.lower() == host.lower()


def disconnect_category(code: int) -> str:
    if code == 4002:
        return "client_background"
    if code in {1000, 1001}:
        return "normal"
    if code == 1005:
        return "mobile_suspend_or_ungraceful"
    return "network_or_abnormal"


def request_ip(request: Request) -> str:
    if request.client is None:
        raise HTTPException(status_code=403, detail="无法识别客户端地址")
    client_ip = request.client.host
    if not is_allowed_ip(client_ip):
        logger.warning("Rejected non-local request from %s", client_ip)
        raise HTTPException(status_code=403, detail="仅允许可信局域网访问")
    return client_ip


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class PairingStartRequest(ApiModel):
    device_name: str = Field(min_length=1, max_length=40)

    @field_validator("device_name")
    @classmethod
    def normalize_device_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("device_name must not be blank")
        if not all(character.isprintable() for character in value):
            raise ValueError("device_name must contain only visible characters")
        return value


class PairingCompleteRequest(ApiModel):
    challenge_id: str = Field(min_length=16, max_length=64)
    code: str = Field(pattern=r"^\d{6}$")


@dataclass
class ActiveSession:
    device_id: str
    websocket: WebSocket
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    last_activity: float = field(default_factory=time.monotonic)
    projection_ids: deque[str] = field(default_factory=lambda: deque(maxlen=128))
    closing: bool = False
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class SessionRegistry:
    def __init__(self, controller: MacController, idle_timeout: float) -> None:
        self.controller = controller
        self.idle_timeout = idle_timeout
        self.active: ActiveSession | None = None
        self.lock = asyncio.Lock()
        self.completed_projections: dict[tuple[str, str], float] = {}

    async def claim(self, session: ActiveSession) -> bool:
        old_session: ActiveSession | None = None
        async with self.lock:
            if self.active and self.active.device_id != session.device_id:
                age = time.monotonic() - self.active.last_activity
                if age <= self.idle_timeout:
                    return False
            old_session = self.active
            self.active = session
        await self.controller.reset()
        if old_session and old_session.websocket is not session.websocket:
            try:
                if old_session.device_id == session.device_id:
                    await old_session.websocket.close(code=4010, reason="replaced")
                else:
                    await old_session.websocket.close(code=4004, reason="idle_timeout")
            except RuntimeError:
                pass
        return True

    async def release(self, websocket: WebSocket) -> None:
        should_reset = False
        async with self.lock:
            if self.active and self.active.websocket is websocket:
                self.active = None
                should_reset = True
        if should_reset:
            await self.controller.reset()

    async def snapshot(self) -> ActiveSession | None:
        async with self.lock:
            return self.active

    async def record_projection(self, device_id: str, request_id: str) -> None:
        now = time.monotonic()
        async with self.lock:
            self.completed_projections[(device_id, request_id)] = now
            cutoff = now - 600
            stale = [
                key
                for key, completed_at in self.completed_projections.items()
                if completed_at < cutoff
            ]
            for key in stale:
                self.completed_projections.pop(key, None)

    async def projection_completed(self, device_id: str, request_id: str) -> bool:
        async with self.lock:
            return (device_id, request_id) in self.completed_projections


def create_app(
    *,
    store: DeviceStore | None = None,
    pairing: PairingManager | None = None,
    controller: MacController | None = None,
    session_idle_timeout: float = SESSION_IDLE_TIMEOUT_SECONDS,
    monitor_interval: float = SESSION_MONITOR_INTERVAL_SECONDS,
) -> FastAPI:
    device_store = store or DeviceStore()
    pairing_manager = pairing or PairingManager(device_store)
    mac_controller = controller or MacController()
    sessions = SessionRegistry(mac_controller, session_idle_timeout)

    async def watch_sessions() -> None:
        last_metrics_log = time.monotonic()
        last_metrics_snapshot: dict[str, int] | None = None
        while True:
            await asyncio.sleep(monitor_interval)
            now = time.monotonic()
            session = await sessions.snapshot()
            if session and not session.closing:
                idle_seconds = now - session.last_activity
                if idle_seconds > session_idle_timeout:
                    session.closing = True
                    logger.info(
                        "Closing idle session session=%s device=%s idle_seconds=%.1f",
                        session.session_id,
                        session.device_id,
                        idle_seconds,
                    )
                    try:
                        await session.websocket.close(
                            code=4004, reason="idle_timeout"
                        )
                    except RuntimeError:
                        pass
                else:
                    try:
                        authorized = await asyncio.to_thread(
                            device_store.contains, session.device_id
                        )
                    except Exception:
                        logger.exception("Unable to read the paired-device database")
                    else:
                        if not authorized:
                            session.closing = True
                            logger.warning(
                                "Disconnecting revoked device session=%s device=%s",
                                session.session_id,
                                session.device_id,
                            )
                            try:
                                await session.websocket.close(
                                    code=4003, reason="device_revoked"
                                )
                            except RuntimeError:
                                pass

            if now - last_metrics_log >= METRICS_LOG_INTERVAL_SECONDS:
                snapshot = getattr(mac_controller, "snapshot_metrics", lambda: {})()
                if snapshot and (session is not None or snapshot != last_metrics_snapshot):
                    logger.info(
                        "Input metrics %s",
                        " ".join(
                            f"{key}={value}" for key, value in snapshot.items()
                        ),
                    )
                last_metrics_snapshot = snapshot
                last_metrics_log = now

    async def watch_event_loop_lag() -> None:
        interval = 1.0
        expected = time.monotonic() + interval
        while True:
            await asyncio.sleep(interval)
            now = time.monotonic()
            lag = max(0.0, now - expected)
            if lag >= EVENT_LOOP_LAG_WARNING_SECONDS:
                logger.warning("Event loop lag duration_ms=%.1f", lag * 1000)
            expected = now + interval

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if os.environ.get("AIRMAC_DEBUG") == "1":
            loop = asyncio.get_running_loop()
            loop.set_debug(True)
            loop.slow_callback_duration = 0.1
            logger.info("Asyncio debug mode enabled")
        await mac_controller.start()
        monitor_tasks = (
            asyncio.create_task(
                watch_sessions(), name="airmac-session-monitor"
            ),
            asyncio.create_task(
                watch_event_loop_lag(), name="airmac-event-loop-monitor"
            ),
        )
        local_ip = get_local_ip()
        logger.info("AirMac started: http://%s:%s", local_ip, PORT)
        print("\n" + "=" * 50)
        print("🚀 AirMac Server Started!")
        print(f"📱 Open http://{local_ip}:{PORT} on your iPhone")
        print("=" * 50 + "\n")
        try:
            yield
        finally:
            for task in monitor_tasks:
                task.cancel()
            await asyncio.gather(*monitor_tasks, return_exceptions=True)
            await pairing_manager.close()
            await mac_controller.stop()

    application = FastAPI(lifespan=lifespan)
    application.state.device_store = device_store
    application.state.pairing_manager = pairing_manager
    application.state.mac_controller = mac_controller
    application.state.sessions = sessions

    @application.get("/")
    async def get_frontend(request: Request) -> HTMLResponse:
        request_ip(request)
        return HTMLResponse(
            (PROJECT_DIR / "index.html").read_text(encoding="utf-8"),
            headers={"Cache-Control": "no-store"},
        )

    @application.get("/icon.png")
    async def get_icon(request: Request) -> Response:
        request_ip(request)
        icon_path = PROJECT_DIR / "icon.png"
        if icon_path.exists():
            return FileResponse(
                icon_path,
                media_type="image/png",
                headers={"Cache-Control": "public, max-age=86400"},
            )
        return Response(status_code=404)

    @application.get("/icons/{filename}")
    async def get_pwa_icon(filename: str, request: Request) -> Response:
        request_ip(request)
        if filename not in PWA_ICONS:
            return Response(status_code=404)
        return FileResponse(
            PROJECT_DIR / "icons" / filename,
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=604800"},
        )

    @application.get("/manifest.webmanifest")
    async def get_manifest(request: Request) -> FileResponse:
        request_ip(request)
        return FileResponse(
            PROJECT_DIR / "manifest.webmanifest",
            media_type="application/manifest+json",
            headers={"Cache-Control": "public, max-age=3600"},
        )

    @application.get("/service-worker.js")
    async def get_service_worker(request: Request) -> FileResponse:
        request_ip(request)
        return FileResponse(
            PROJECT_DIR / "service-worker.js",
            media_type="text/javascript",
            headers={
                "Cache-Control": "no-cache",
                "Service-Worker-Allowed": "/",
            },
        )

    @application.get("/offline.html")
    async def get_offline_page(request: Request) -> FileResponse:
        request_ip(request)
        return FileResponse(
            PROJECT_DIR / "offline.html",
            media_type="text/html",
            headers={"Cache-Control": "public, max-age=3600"},
        )

    @application.get("/frontend_state.js")
    async def get_frontend_state(request: Request) -> FileResponse:
        request_ip(request)
        return FileResponse(
            PROJECT_DIR / "frontend_state.js",
            media_type="text/javascript",
            headers={"Cache-Control": "no-store"},
        )

    @application.get("/ui_components.js")
    async def get_ui_components(request: Request) -> FileResponse:
        request_ip(request)
        return FileResponse(
            PROJECT_DIR / "ui_components.js",
            media_type="text/javascript",
            headers={"Cache-Control": "no-store"},
        )

    @application.get("/api/health")
    async def get_health(request: Request) -> dict[str, object]:
        request_ip(request)
        session = await sessions.snapshot()
        return {
            "status": "ok",
            "controller": "connected" if session else "idle",
        }

    @application.post("/api/pairing/start")
    async def start_pairing(
        payload: PairingStartRequest, request: Request
    ) -> dict[str, Any]:
        client_ip = request_ip(request)
        try:
            challenge = await pairing_manager.start(
                payload.device_name, client_ip
            )
        except PairingBusy as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        except PairingRateLimited as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        except PairingError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return {
            "challenge_id": challenge.challenge_id,
            "expires_in": max(0, int(challenge.expires_at - asyncio.get_running_loop().time())),
        }

    @application.post("/api/pairing/complete")
    async def complete_pairing(
        payload: PairingCompleteRequest, request: Request
    ) -> dict[str, str]:
        client_ip = request_ip(request)
        try:
            device_id, token, device_name = await pairing_manager.complete(
                payload.challenge_id, payload.code, client_ip
            )
        except PairingInvalid as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except PairingError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return {
            "device_id": device_id,
            "token": token,
            "device_name": device_name,
        }

    @application.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        client = websocket.client
        if (
            client is None
            or not is_allowed_ip(client.host)
            or not is_allowed_origin(websocket)
        ):
            await websocket.close(code=1008, reason="access_denied")
            return

        await websocket.accept()
        if websocket.query_params.get("device_id"):
            logger.info("Rejected legacy WebSocket identity from %s", client.host)
            await websocket.send_json({"type": "auth_failed"})
            await websocket.close(code=4003, reason="legacy_identity_not_supported")
            return
        claimed = False
        session: ActiveSession | None = None
        try:
            raw_auth = await asyncio.wait_for(
                websocket.receive_text(), timeout=AUTH_TIMEOUT_SECONDS
            )
            auth_message = parse_auth_message(raw_auth)
            try:
                authenticated = await asyncio.to_thread(
                    device_store.authenticate,
                    auth_message.device_id,
                    auth_message.token,
                )
            except Exception:
                logger.exception("Unable to read the paired-device database")
                await websocket.close(code=1011, reason="credential_store_unavailable")
                return
            if not authenticated:
                logger.warning(
                    "WebSocket authentication failed client=%s device=%s",
                    client.host,
                    auth_message.device_id,
                )
                await websocket.send_json({"type": "auth_failed"})
                await websocket.close(code=4003, reason="authentication_failed")
                return

            session = ActiveSession(auth_message.device_id, websocket)
            if not await sessions.claim(session):
                logger.info(
                    "Controller busy client=%s device=%s",
                    client.host,
                    auth_message.device_id,
                )
                await websocket.send_json(
                    {"type": "error", "code": "controller_busy"}
                )
                await websocket.close(code=4009, reason="controller_busy")
                return
            claimed = True
            try:
                await asyncio.to_thread(device_store.touch, session.device_id)
            except Exception:
                logger.exception(
                    "Unable to update last_seen device=%s", session.device_id
                )
            await websocket.send_json({"type": "auth_ok"})
            logger.info(
                "WebSocket connected session=%s client=%s device=%s",
                session.session_id,
                client.host,
                auth_message.device_id,
            )
            try:
                await controller.wake_if_display_asleep()
            except Exception:
                logger.exception(
                    "Unable to check display sleep state session=%s device=%s",
                    session.session_id,
                    session.device_id,
                )

            async def notify(payload: dict[str, object]) -> None:
                if (
                    payload.get("type") == "action_result"
                    and payload.get("action") == "type_text"
                    and isinstance(payload.get("request_id"), str)
                ):
                    request_id = str(payload["request_id"])
                    if payload.get("status") == "ok":
                        await sessions.record_projection(
                            session.device_id, request_id
                        )
                    elif payload.get("status") == "error":
                        try:
                            session.projection_ids.remove(request_id)
                        except ValueError:
                            pass
                active = await sessions.snapshot()
                if active is not session:
                    return
                async with session.send_lock:
                    await websocket.send_json(payload)

            while True:
                raw_message = await websocket.receive_text()
                session.last_activity = time.monotonic()
                try:
                    action = parse_action_message(raw_message)
                except (json.JSONDecodeError, ValidationError, ValueError):
                    logger.warning(
                        "Rejected invalid message session=%s client=%s device=%s bytes=%s",
                        session.session_id,
                        client.host,
                        session.device_id,
                        len(raw_message.encode("utf-8")),
                    )
                    await notify({"type": "error", "code": "invalid_message"})
                    continue
                if await sessions.snapshot() is not session:
                    await websocket.close(code=4010, reason="replaced")
                    return
                if action.action == "heartbeat":
                    await notify({"type": "heartbeat_ack"})
                    continue
                if isinstance(action, TypeTextAction):
                    if (
                        action.request_id in session.projection_ids
                        or await sessions.projection_completed(
                            session.device_id, action.request_id
                        )
                    ):
                        await notify(
                            {
                                "type": "action_result",
                                "action": "type_text",
                                "request_id": action.request_id,
                                "status": "duplicate",
                            }
                        )
                        continue
                    session.projection_ids.append(action.request_id)
                if not await mac_controller.dispatch(action, notify):
                    logger.warning(
                        "Input queue full session=%s action=%s device=%s",
                        session.session_id,
                        action.action,
                        session.device_id,
                    )
                    if isinstance(action, TypeTextAction):
                        try:
                            session.projection_ids.remove(action.request_id)
                        except ValueError:
                            pass
                        await notify(
                            {
                                "type": "action_result",
                                "action": "type_text",
                                "request_id": action.request_id,
                                "status": "error",
                                "code": "queue_full",
                            }
                        )
                    else:
                        await notify({"type": "error", "code": "queue_full"})
        except asyncio.TimeoutError:
            logger.warning("WebSocket authentication timeout client=%s", client.host)
            await websocket.close(code=4008, reason="authentication_timeout")
        except (json.JSONDecodeError, ValidationError, ValueError):
            await websocket.send_json({"type": "auth_failed"})
            await websocket.close(code=4003, reason="authentication_failed")
        except WebSocketDisconnect as exc:
            logger.info(
                "WebSocket disconnected session=%s client=%s device=%s code=%s category=%s reason=%s",
                session.session_id if session else "-",
                client.host,
                session.device_id if session else "unauthenticated",
                exc.code,
                disconnect_category(exc.code),
                exc.reason or "-",
            )
        except RuntimeError as exc:
            logger.debug("WebSocket closed during operation: %s", exc)
        finally:
            if claimed:
                await sessions.release(websocket)

    return application


app = create_app()
