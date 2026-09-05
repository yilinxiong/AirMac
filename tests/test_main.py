from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import main
from auth import DeviceStore
from protocol import MoveAction


class FakeController:
    def __init__(self) -> None:
        self.actions: list[Any] = []
        self.reset_count = 0
        self.auto_wake_checks = 0

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def reset(self) -> None:
        self.reset_count += 1

    async def wake_if_display_asleep(self) -> bool:
        self.auto_wake_checks += 1
        return False

    async def dispatch(self, action: Any, notify: Any) -> bool:
        self.actions.append(action)
        return True

    def snapshot_metrics(self) -> dict[str, int]:
        return {"pointer_depth": 0, "control_depth": 0}


class FakePairingManager:
    async def start(self, device_name: str, client_ip: str):
        return SimpleNamespace(
            challenge_id="challenge_identifier_1",
            expires_at=asyncio.get_running_loop().time() + 120,
        )

    async def complete(self, challenge_id: str, code: str, client_ip: str):
        return "device-id", "secret-token", "Test Phone"

    async def close(self) -> None:
        pass


class CompletingController(FakeController):
    async def dispatch(self, action: Any, notify: Any) -> bool:
        self.actions.append(action)
        if isinstance(action, main.TypeTextAction):
            await notify(
                {
                    "type": "action_result",
                    "action": "type_text",
                    "request_id": action.request_id,
                    "status": "ok",
                }
            )
        return True


class FailingProjectionController(FakeController):
    async def dispatch(self, action: Any, notify: Any) -> bool:
        self.actions.append(action)
        if isinstance(action, main.TypeTextAction):
            await notify(
                {
                    "type": "action_result",
                    "action": "type_text",
                    "request_id": action.request_id,
                    "status": "error",
                }
            )
        return True


@pytest.fixture
def app_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    store = DeviceStore(tmp_path / "devices.json")
    controller = FakeController()
    monkeypatch.setattr(main, "is_allowed_ip", lambda _: True)
    monkeypatch.setattr(main, "is_loopback_ip", lambda _: True)
    application = main.create_app(store=store, controller=controller)
    with TestClient(application) as client:
        yield client, store, controller


def authenticate_socket(client: TestClient, device_id: str, token: str):
    return client.websocket_connect(
        "/ws", headers={"origin": "http://testserver", "host": "testserver"}
    )


def test_websocket_requires_authentication(app_client: tuple[Any, ...]) -> None:
    client, _, controller = app_client
    with client.websocket_connect(
        "/ws", headers={"origin": "http://testserver", "host": "testserver"}
    ) as websocket:
        websocket.send_json({"action": "mouse_down"})
        assert websocket.receive_json() == {"type": "auth_failed"}
        with pytest.raises(WebSocketDisconnect) as closed:
            websocket.receive_json()
        assert closed.value.code == 4003
    assert controller.actions == []


def test_websocket_authentication_times_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(main, "is_allowed_ip", lambda _: True)
    monkeypatch.setattr(main, "AUTH_TIMEOUT_SECONDS", 0.01)
    application = main.create_app(
        store=DeviceStore(tmp_path / "devices.json"), controller=FakeController()
    )
    with TestClient(application) as client:
        with client.websocket_connect(
            "/ws", headers={"origin": "http://testserver", "host": "testserver"}
        ) as websocket:
            with pytest.raises(WebSocketDisconnect) as closed:
                websocket.receive_json()
            assert closed.value.code == 4008


def test_websocket_rejects_wrong_token(app_client: tuple[Any, ...]) -> None:
    client, store, controller = app_client
    device_id, _ = store.issue_device("Test Phone")
    with authenticate_socket(client, device_id, "x" * 43) as websocket:
        websocket.send_json(
            {"type": "authenticate", "device_id": device_id, "token": "x" * 43}
        )
        assert websocket.receive_json() == {"type": "auth_failed"}
        with pytest.raises(WebSocketDisconnect) as closed:
            websocket.receive_json()
        assert closed.value.code == 4003
    assert controller.actions == []


def test_frontend_is_not_cached(app_client: tuple[Any, ...]) -> None:
    client, _, _ = app_client
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert '<dialog class="settings-dialog"' not in response.text
    assert 'id="settings-overlay" hidden' in response.text
    assert 'id="settings-close"' in response.text
    assert 'id="language-toggle"' in response.text
    assert "/ui_components.js?v=16" in response.text
    assert "<script>" not in response.text
    assert "<style>" not in response.text
    for filename in main.WEB_ASSETS:
        assert client.get(f"/web/{filename}?v=16").status_code == 200
    assert client.get("/web/auth.py").status_code == 404
    assert client.get("/web/%2e%2e/auth.py").status_code == 404
    text_view_end = response.text.index(
        "</section>", response.text.index('id="text-view"')
    )
    guide_position = response.text.index('class="gesture-guide"')
    nav_end = response.text.index("</nav>")
    assert text_view_end < nav_end < guide_position


def test_pwa_assets_are_served_with_safe_types(app_client: tuple[Any, ...]) -> None:
    client, _, _ = app_client
    manifest = client.get("/manifest.webmanifest")
    assert manifest.status_code == 200
    assert manifest.headers["content-type"].startswith("application/manifest+json")
    assert manifest.json()["display"] == "standalone"

    worker = client.get("/service-worker.js")
    assert worker.status_code == 200
    assert worker.headers["service-worker-allowed"] == "/"
    assert worker.headers["cache-control"] == "no-cache"

    components = client.get("/ui_components.js")
    assert components.status_code == 200
    assert components.headers["content-type"].startswith("text/javascript")
    assert components.headers["cache-control"] == "no-store"

    icon = client.get("/icons/icon-192.png")
    assert icon.status_code == 200
    assert icon.headers["content-type"].startswith("image/png")
    assert client.get("/icons/../auth.py").status_code == 404


def test_health_endpoint_is_sanitized(app_client: tuple[Any, ...]) -> None:
    client, _, _ = app_client
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "controller": "idle"}


def test_http_responses_include_browser_security_headers(
    app_client: tuple[Any, ...]
) -> None:
    client, _, _ = app_client
    response = client.get("/")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    csp = response.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in csp
    assert "script-src 'self'" in csp


def test_diagnostics_are_loopback_only_and_sanitized(
    app_client: tuple[Any, ...]
) -> None:
    client, _, _ = app_client
    response = client.get("/api/diagnostics")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["version"] == "0.3.0"
    assert payload["protocol_version"] == 2
    assert payload["controller"] == "idle"
    assert payload["queue_metrics"] == {
        "pointer_depth": 0,
        "control_depth": 0,
    }
    serialized = json.dumps(payload).lower()
    for forbidden in ("device_id", "token", "client_ip", "text_content"):
        assert forbidden not in serialized


def test_diagnostics_reject_non_loopback_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(main, "is_allowed_ip", lambda _: True)
    monkeypatch.setattr(main, "is_loopback_ip", lambda _: False)
    application = main.create_app(
        store=DeviceStore(tmp_path / "devices.json"), controller=FakeController()
    )
    with TestClient(application) as client:
        assert client.get("/api/diagnostics").status_code == 403


def test_pairing_posts_require_matching_origin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(main, "is_allowed_ip", lambda _: True)
    application = main.create_app(
        store=DeviceStore(tmp_path / "devices.json"),
        pairing=FakePairingManager(),
        controller=FakeController(),
    )
    with TestClient(application) as client:
        payload = {"device_name": "Test Phone"}
        assert client.post("/api/pairing/start", json=payload).status_code == 403
        assert (
            client.post(
                "/api/pairing/start",
                json=payload,
                headers={"origin": "http://evil.example"},
            ).status_code
            == 403
        )
        accepted = client.post(
            "/api/pairing/start",
            json=payload,
            headers={"origin": "http://testserver"},
        )
        assert accepted.status_code == 200
        assert accepted.json()["challenge_id"] == "challenge_identifier_1"
        completed = client.post(
            "/api/pairing/complete",
            json={"challenge_id": "challenge_identifier_1", "code": "123456"},
            headers={"origin": "http://testserver"},
        )
        assert completed.status_code == 200
        assert completed.json()["device_id"] == "device-id"


def test_legacy_query_identity_is_rejected_without_retry(
    app_client: tuple[Any, ...]
) -> None:
    client, _, controller = app_client
    with client.websocket_connect(
        "/ws?device_id=00000000-0000-4000-8000-000000000000&device_name=Old",
        headers={"origin": "http://testserver", "host": "testserver"},
    ) as websocket:
        assert websocket.receive_json() == {"type": "auth_failed"}
        with pytest.raises(WebSocketDisconnect) as closed:
            websocket.receive_json()
        assert closed.value.code == 4003
    assert controller.actions == []


def test_authenticated_websocket_dispatches_valid_actions(
    app_client: tuple[Any, ...]
) -> None:
    client, store, controller = app_client
    device_id, token = store.issue_device("Test Phone")
    with authenticate_socket(client, device_id, token) as websocket:
        websocket.send_json(
            {"type": "authenticate", "device_id": device_id, "token": token}
        )
        assert websocket.receive_json() == {"type": "auth_ok"}
        websocket.send_json({"action": "move", "dx": 2, "dy": -3})
    assert isinstance(controller.actions[0], MoveAction)
    assert controller.reset_count >= 2
    assert controller.auto_wake_checks == 1


def test_v2_authentication_negotiates_protocol_metadata(
    app_client: tuple[Any, ...]
) -> None:
    client, store, _ = app_client
    device_id, token = store.issue_device("V2 Phone")
    with authenticate_socket(client, device_id, token) as websocket:
        websocket.send_json(
            {
                "type": "authenticate",
                "device_id": device_id,
                "token": token,
                "protocol_version": 2,
                "client_version": "0.3.0-web",
            }
        )
        response = websocket.receive_json()
        assert response["type"] == "auth_ok"
        assert response["protocol_version"] == 2
        assert response["server_version"] == "0.3.0"
        assert response["session_id"]
        assert response["heartbeat_interval_ms"] == 5_000
        assert response["limits"]["message_bytes"] == 65_536
        assert "typed_server_messages" in response["capabilities"]


def test_unsupported_protocol_is_rejected_before_control_claim(
    app_client: tuple[Any, ...]
) -> None:
    client, store, controller = app_client
    device_id, token = store.issue_device("Future Phone")
    with authenticate_socket(client, device_id, token) as websocket:
        websocket.send_json(
            {
                "type": "authenticate",
                "device_id": device_id,
                "token": token,
                "protocol_version": 99,
            }
        )
        assert websocket.receive_json() == {
            "type": "error",
            "code": "unsupported_protocol",
        }
        with pytest.raises(WebSocketDisconnect) as closed:
            websocket.receive_json()
        assert closed.value.code == 4011
    assert controller.actions == []
    assert controller.auto_wake_checks == 0


def test_default_controller_is_used_for_auto_wake(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = DeviceStore(tmp_path / "devices.json")
    controller = FakeController()
    monkeypatch.setattr(main, "is_allowed_ip", lambda _: True)
    monkeypatch.setattr(main, "MacController", lambda: controller)
    application = main.create_app(store=store)
    device_id, token = store.issue_device("Auto Wake Phone")

    with TestClient(application) as client:
        with authenticate_socket(client, device_id, token) as websocket:
            websocket.send_json(
                {"type": "authenticate", "device_id": device_id, "token": token}
            )
            assert websocket.receive_json() == {"type": "auth_ok"}

    assert application.state.mac_controller is controller
    assert controller.auto_wake_checks == 1


def test_heartbeat_is_acknowledged_without_dispatch(
    app_client: tuple[Any, ...]
) -> None:
    client, store, controller = app_client
    device_id, token = store.issue_device("Heartbeat Phone")
    with authenticate_socket(client, device_id, token) as websocket:
        websocket.send_json(
            {"type": "authenticate", "device_id": device_id, "token": token}
        )
        assert websocket.receive_json() == {"type": "auth_ok"}
        websocket.send_json({"action": "heartbeat"})
        assert websocket.receive_json() == {"type": "heartbeat_ack"}
    assert controller.actions == []


def test_duplicate_text_projection_is_not_dispatched_twice(
    app_client: tuple[Any, ...]
) -> None:
    client, store, controller = app_client
    device_id, token = store.issue_device("Projection Phone")
    payload = {
        "action": "type_text",
        "request_id": "projection_request_1",
        "text": "only once",
    }
    with authenticate_socket(client, device_id, token) as websocket:
        websocket.send_json(
            {"type": "authenticate", "device_id": device_id, "token": token}
        )
        assert websocket.receive_json() == {"type": "auth_ok"}
        websocket.send_json(payload)
        websocket.send_json(payload)
        assert websocket.receive_json() == {
            "type": "action_result",
            "action": "type_text",
            "request_id": "projection_request_1",
            "status": "duplicate",
        }
    assert len(controller.actions) == 1


def test_completed_projection_is_deduplicated_after_reconnect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = DeviceStore(tmp_path / "devices.json")
    controller = CompletingController()
    monkeypatch.setattr(main, "is_allowed_ip", lambda _: True)
    application = main.create_app(store=store, controller=controller)
    device_id, token = store.issue_device("Retry Phone")
    payload = {
        "action": "type_text",
        "request_id": "projection_retry_1",
        "text": "send once across reconnect",
    }
    with TestClient(application) as client:
        with authenticate_socket(client, device_id, token) as first:
            first.send_json(
                {"type": "authenticate", "device_id": device_id, "token": token}
            )
            assert first.receive_json() == {"type": "auth_ok"}
            first.send_json(payload)
            assert first.receive_json()["status"] == "ok"
        with authenticate_socket(client, device_id, token) as second:
            second.send_json(
                {"type": "authenticate", "device_id": device_id, "token": token}
            )
            assert second.receive_json() == {"type": "auth_ok"}
            second.send_json(payload)
            assert second.receive_json()["status"] == "duplicate"
    assert len(controller.actions) == 1


def test_failed_projection_can_retry_same_request_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = DeviceStore(tmp_path / "devices.json")
    controller = FailingProjectionController()
    monkeypatch.setattr(main, "is_allowed_ip", lambda _: True)
    application = main.create_app(store=store, controller=controller)
    device_id, token = store.issue_device("Retry Failure Phone")
    payload = {
        "action": "type_text",
        "request_id": "projection_failure_1",
        "text": "retry me",
    }
    with TestClient(application) as client:
        with authenticate_socket(client, device_id, token) as websocket:
            websocket.send_json(
                {"type": "authenticate", "device_id": device_id, "token": token}
            )
            assert websocket.receive_json() == {"type": "auth_ok"}
            websocket.send_json(payload)
            assert websocket.receive_json()["status"] == "error"
            websocket.send_json(payload)
            assert websocket.receive_json()["status"] == "error"
    assert len(controller.actions) == 2


def test_websocket_rejects_bad_origin(app_client: tuple[Any, ...]) -> None:
    client, store, _ = app_client
    device_id, token = store.issue_device("Test Phone")
    with pytest.raises(WebSocketDisconnect) as closed:
        with client.websocket_connect(
            "/ws", headers={"origin": "http://evil.example", "host": "testserver"}
        ) as websocket:
            websocket.send_json(
                {"type": "authenticate", "device_id": device_id, "token": token}
            )
    assert closed.value.code == 1008


def test_second_device_is_busy(app_client: tuple[Any, ...]) -> None:
    client, store, _ = app_client
    first_id, first_token = store.issue_device("First")
    second_id, second_token = store.issue_device("Second")
    with authenticate_socket(client, first_id, first_token) as first:
        first.send_json(
            {"type": "authenticate", "device_id": first_id, "token": first_token}
        )
        assert first.receive_json() == {"type": "auth_ok"}
        with authenticate_socket(client, second_id, second_token) as second:
            second.send_json(
                {
                    "type": "authenticate",
                    "device_id": second_id,
                    "token": second_token,
                }
            )
            assert second.receive_json() == {
                "type": "error",
                "code": "controller_busy",
            }
            with pytest.raises(WebSocketDisconnect) as closed:
                second.receive_json()
            assert closed.value.code == 4009


def test_same_device_new_connection_replaces_old(app_client: tuple[Any, ...]) -> None:
    client, store, _ = app_client
    device_id, token = store.issue_device("Same Phone")
    with authenticate_socket(client, device_id, token) as first:
        first.send_json(
            {"type": "authenticate", "device_id": device_id, "token": token}
        )
        assert first.receive_json() == {"type": "auth_ok"}
        with authenticate_socket(client, device_id, token) as second:
            second.send_json(
                {"type": "authenticate", "device_id": device_id, "token": token}
            )
            assert second.receive_json() == {"type": "auth_ok"}
            with pytest.raises(WebSocketDisconnect) as closed:
                first.receive_json()
            assert closed.value.code == 4010


def test_explicit_network_ranges() -> None:
    assert main.is_allowed_ip("192.168.1.10")
    assert main.is_allowed_ip("10.20.30.40")
    assert main.is_allowed_ip("172.16.0.1")
    assert main.is_allowed_ip("fd00::1")
    assert not main.is_allowed_ip("8.8.8.8")
    assert not main.is_allowed_ip("172.15.255.255")


def test_disconnect_categories_include_mobile_lifecycle() -> None:
    assert main.disconnect_category(4002) == "client_background"
    assert main.disconnect_category(1000) == "normal"
    assert main.disconnect_category(1005) == "mobile_suspend_or_ungraceful"
    assert main.disconnect_category(1006) == "network_or_abnormal"


def test_blank_device_name_is_rejected() -> None:
    with pytest.raises(ValueError):
        main.PairingStartRequest(device_name="   ")
    with pytest.raises(ValueError):
        main.PairingStartRequest(device_name="Phone\u200b")


def test_revoked_active_device_is_disconnected(app_client: tuple[Any, ...]) -> None:
    client, store, _ = app_client
    device_id, token = store.issue_device("Revoked Phone")
    with authenticate_socket(client, device_id, token) as websocket:
        websocket.send_json(
            {"type": "authenticate", "device_id": device_id, "token": token}
        )
        assert websocket.receive_json() == {"type": "auth_ok"}
        assert store.revoke(device_id)
        time.sleep(1.1)
        with pytest.raises(WebSocketDisconnect) as closed:
            websocket.receive_json()
        assert closed.value.code == 4003


def test_idle_session_is_closed_and_releases_controller(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = DeviceStore(tmp_path / "devices.json")
    controller = FakeController()
    monkeypatch.setattr(main, "is_allowed_ip", lambda _: True)
    application = main.create_app(
        store=store,
        controller=controller,
        session_idle_timeout=0.03,
        monitor_interval=0.01,
    )
    device_id, token = store.issue_device("Idle Phone")
    with TestClient(application) as client:
        with authenticate_socket(client, device_id, token) as websocket:
            websocket.send_json(
                {"type": "authenticate", "device_id": device_id, "token": token}
            )
            assert websocket.receive_json() == {"type": "auth_ok"}
            with pytest.raises(WebSocketDisconnect) as closed:
                websocket.receive_json()
            assert closed.value.code == 4004
    assert controller.reset_count >= 2
