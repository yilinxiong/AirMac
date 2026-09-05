from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import socket
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from auth import (
    DeviceStore,
    PairingBusy,
    PairingError,
    PairingInvalid,
    PairingManager,
    PairingRateLimited,
)
from connection import ConnectionHandler, disconnect_category
from mac_controller import MacController
from protocol import AuthFailedMessage, TypeTextAction
from sessions import SessionRegistry
from transport import TransportDisconnected
from websocket_transport import WebSocketTransport


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
    connection_handler = ConnectionHandler(
        device_store,
        mac_controller,
        sessions,
        auth_timeout=AUTH_TIMEOUT_SECONDS,
    )

    async def watch_metrics() -> None:
        last_metrics_log = time.monotonic()
        last_metrics_snapshot: dict[str, int] | None = None
        while True:
            await asyncio.sleep(monitor_interval)
            now = time.monotonic()
            session = await sessions.snapshot()
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
                sessions.monitor(device_store, monitor_interval),
                name="airmac-session-monitor",
            ),
            asyncio.create_task(
                watch_metrics(), name="airmac-metrics-monitor"
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
            await connection_handler.close()
            await pairing_manager.close()
            await mac_controller.stop()

    application = FastAPI(lifespan=lifespan)
    application.state.device_store = device_store
    application.state.pairing_manager = pairing_manager
    application.state.mac_controller = mac_controller
    application.state.sessions = sessions
    application.state.connection_handler = connection_handler

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
        transport = WebSocketTransport(websocket, client.host)
        if websocket.query_params.get("device_id"):
            logger.info("Rejected legacy WebSocket identity from %s", client.host)
            try:
                await transport.send(AuthFailedMessage())
                await transport.close(4003, "legacy_identity_not_supported")
            except TransportDisconnected:
                pass
            return
        await connection_handler.handle(transport)

    return application


app = create_app()
