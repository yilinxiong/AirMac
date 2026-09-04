from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from protocol import (
    MAX_MESSAGE_BYTES,
    AuthOkMessage,
    ProtocolLimits,
    encode_server_message,
    parse_action_message,
    parse_auth_message,
    parse_server_message,
)


def test_auth_message_is_strict() -> None:
    message = parse_auth_message(
        json.dumps(
            {
                "type": "authenticate",
                "device_id": "00000000-0000-4000-8000-000000000000",
                "token": "x" * 43,
            }
        )
    )
    assert message.type == "authenticate"
    assert message.protocol_version == 1
    assert message.client_version is None

    with pytest.raises(ValidationError):
        parse_auth_message(
            json.dumps(
                {
                    "type": "authenticate",
                    "device_id": "client-generated",
                    "token": "x" * 43,
                }
            )
        )


def test_auth_message_accepts_v2_metadata_and_rejects_invalid_versions() -> None:
    message = parse_auth_message(
        json.dumps(
            {
                "type": "authenticate",
                "device_id": "00000000-0000-4000-8000-000000000000",
                "token": "x" * 43,
                "protocol_version": 2,
                "client_version": "0.3.0-web",
            }
        )
    )
    assert message.protocol_version == 2
    assert message.client_version == "0.3.0-web"

    with pytest.raises(ValidationError):
        parse_auth_message(
            json.dumps(
                {
                    "type": "authenticate",
                    "device_id": "00000000-0000-4000-8000-000000000000",
                    "token": "x" * 43,
                    "protocol_version": 0,
                }
            )
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"action": "move", "dx": 1.5, "dy": -2},
        {"action": "mouse_drag", "dx": 500, "dy": -500},
        {"action": "scroll", "dy": 1000},
        {"action": "click", "button": "right"},
        {"action": "type", "char": "你好"},
        {"action": "keydown", "key": "Backspace"},
        {"action": "media", "command": "playpause"},
        {"action": "quick_action", "command": "window_left"},
        {"action": "quick_action", "command": "screenshot"},
        {"action": "quick_action", "command": "open_control_center"},
        {"action": "quick_action", "command": "close_fullscreen"},
        {"action": "quick_action", "command": "cycle_audio_output"},
        {"action": "type_text", "request_id": "request_123", "text": "hello"},
        {"action": "mouse_up"},
        {"action": "app_launcher"},
        {"action": "heartbeat"},
    ],
)
def test_valid_actions(payload: dict[str, object]) -> None:
    assert parse_action_message(json.dumps(payload)).action == payload["action"]


@pytest.mark.parametrize(
    "raw",
    [
        '{"action":"move","dx":NaN,"dy":0}',
        '{"action":"move","dx":501,"dy":0}',
        '{"action":"scroll","dy":1001}',
        '{"action":"type","char":"12345678901234567"}',
        '{"action":"unknown"}',
        '{"action":"quick_action","command":"run_shell"}',
        '{"action":"quick_action","command":"open_wifi"}',
        '{"action":"quick_action","command":"open_bluetooth"}',
        '{"action":"quick_action","command":"open_airdrop"}',
        '{"action":"mouse_up","extra":true}',
        '[]',
    ],
)
def test_invalid_actions_are_rejected(raw: str) -> None:
    with pytest.raises((ValidationError, ValueError)):
        parse_action_message(raw)


def test_oversized_message_is_rejected() -> None:
    raw = json.dumps(
        {
            "action": "type_text",
            "request_id": "request_oversized",
            "text": "x" * MAX_MESSAGE_BYTES,
        }
    )
    with pytest.raises(ValueError, match="message_too_large"):
        parse_action_message(raw)


def test_type_text_limit_is_measured_in_utf8_bytes() -> None:
    assert parse_action_message(
        json.dumps(
            {
                "action": "type_text",
                "request_id": "request_utf8_ok",
                "text": "界" * 10_922,
            },
            ensure_ascii=False,
        )
    ).action == "type_text"
    with pytest.raises(ValidationError, match="32 KiB"):
        parse_action_message(
            json.dumps(
                {
                    "action": "type_text",
                    "request_id": "request_utf8_large",
                    "text": "界" * 10_923,
                },
                ensure_ascii=False,
            )
        )


def test_type_text_requires_safe_request_id() -> None:
    with pytest.raises(ValidationError):
        parse_action_message(json.dumps({"action": "type_text", "text": "missing"}))
    with pytest.raises(ValidationError):
        parse_action_message(
            json.dumps(
                {
                    "action": "type_text",
                    "request_id": "bad request id",
                    "text": "invalid",
                }
            )
        )


def test_server_messages_are_strict_and_json_ready() -> None:
    payload = encode_server_message(
        AuthOkMessage(
            protocol_version=2,
            server_version="0.3.0",
            session_id="session_1234",
            capabilities=["typed_server_messages"],
            heartbeat_interval_ms=5_000,
            limits=ProtocolLimits(),
        )
    )
    assert payload == {
        "type": "auth_ok",
        "protocol_version": 2,
        "server_version": "0.3.0",
        "session_id": "session_1234",
        "capabilities": ["typed_server_messages"],
        "heartbeat_interval_ms": 5_000,
        "limits": {
            "message_bytes": 65_536,
            "text_bytes": 32_768,
            "move_delta": 500,
            "scroll_delta": 1_000,
        },
    }
    assert parse_server_message({"type": "heartbeat_ack"}).type == "heartbeat_ack"

    with pytest.raises(ValidationError):
        parse_server_message({"type": "error", "code": "bad", "extra": True})
    with pytest.raises(ValidationError):
        parse_server_message(
            {
                "type": "action_result",
                "action": "type_text",
                "request_id": "request_123",
                "status": "closed",
            }
        )
