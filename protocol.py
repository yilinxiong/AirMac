from __future__ import annotations

import json
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    field_validator,
)


MAX_MESSAGE_BYTES = 65_536
PROTOCOL_VERSION = 2
SUPPORTED_PROTOCOL_VERSIONS = frozenset({1, PROTOCOL_VERSION})
HEARTBEAT_INTERVAL_MS = 5_000
MAX_TEXT_BYTES = 32_768
MAX_MOVE_DELTA = 500
MAX_SCROLL_DELTA = 1_000

QuickActionCommand = Literal[
    "window_left",
    "window_right",
    "window_fill",
    "window_center",
    "volume_down",
    "volume_mute",
    "volume_up",
    "brightness_down",
    "brightness_up",
    "screenshot",
    "lock_screen",
    "open_control_center",
    "close_fullscreen",
    "cycle_audio_output",
]


class StrictMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class AuthenticateMessage(StrictMessage):
    type: Literal["authenticate"]
    device_id: Annotated[str, StringConstraints(min_length=36, max_length=36)]
    token: Annotated[str, StringConstraints(min_length=32, max_length=128)]
    protocol_version: Annotated[int, Field(ge=1, le=65_535)] = 1
    client_version: Annotated[
        str,
        StringConstraints(min_length=1, max_length=32, pattern=r"^[ -~]+$"),
    ] | None = None


class ActionBase(StrictMessage):
    action: str


class NoPayloadAction(ActionBase):
    action: Literal[
        "auto_copy",
        "mouse_down",
        "mouse_up",
        "triple_click",
        "mission_control",
        "app_launcher",
        "space_left",
        "space_right",
        "cmd_tab",
        "display_sleep",
        "wake_watch",
        "heartbeat",
    ]


FiniteMove = Annotated[
    float,
    Field(ge=-MAX_MOVE_DELTA, le=MAX_MOVE_DELTA, allow_inf_nan=False),
]


class MoveAction(ActionBase):
    action: Literal["move", "mouse_drag"]
    dx: FiniteMove
    dy: FiniteMove


class ClickAction(ActionBase):
    action: Literal["click"]
    button: Literal["left", "right"] = "left"


class ScrollAction(ActionBase):
    action: Literal["scroll"]
    dy: Annotated[
        float,
        Field(ge=-MAX_SCROLL_DELTA, le=MAX_SCROLL_DELTA, allow_inf_nan=False),
    ]


class TypeAction(ActionBase):
    action: Literal["type"]
    char: Annotated[str, StringConstraints(min_length=1, max_length=16)]


class KeydownAction(ActionBase):
    action: Literal["keydown"]
    key: Literal["Backspace", "Enter"]


class MediaAction(ActionBase):
    action: Literal["media"]
    command: Literal["playpause", "fullscreen"]


class QuickAction(ActionBase):
    action: Literal["quick_action"]
    command: QuickActionCommand


class TypeTextAction(ActionBase):
    action: Literal["type_text"]
    request_id: Annotated[
        str,
        StringConstraints(
            min_length=8,
            max_length=64,
            pattern=r"^[A-Za-z0-9_-]+$",
        ),
    ]
    text: Annotated[str, StringConstraints(min_length=1, max_length=MAX_TEXT_BYTES)]

    @field_validator("text")
    @classmethod
    def limit_utf8_size(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_TEXT_BYTES:
            raise ValueError("text must not exceed 32 KiB in UTF-8")
        return value


ActionMessage = Annotated[
    NoPayloadAction
    | MoveAction
    | ClickAction
    | ScrollAction
    | TypeAction
    | KeydownAction
    | MediaAction
    | QuickAction
    | TypeTextAction,
    Field(discriminator="action"),
]
ClientMessage = AuthenticateMessage | ActionMessage


class ProtocolLimits(StrictMessage):
    message_bytes: Literal[MAX_MESSAGE_BYTES] = MAX_MESSAGE_BYTES
    text_bytes: Literal[MAX_TEXT_BYTES] = MAX_TEXT_BYTES
    move_delta: Literal[MAX_MOVE_DELTA] = MAX_MOVE_DELTA
    scroll_delta: Literal[MAX_SCROLL_DELTA] = MAX_SCROLL_DELTA


class AuthOkMessage(StrictMessage):
    type: Literal["auth_ok"] = "auth_ok"
    protocol_version: Literal[1, PROTOCOL_VERSION] | None = None
    server_version: Annotated[
        str, StringConstraints(min_length=1, max_length=32)
    ] | None = None
    session_id: Annotated[
        str, StringConstraints(min_length=8, max_length=64)
    ] | None = None
    capabilities: list[
        Annotated[str, StringConstraints(min_length=1, max_length=64)]
    ] | None = None
    heartbeat_interval_ms: Annotated[
        int, Field(ge=1_000, le=60_000)
    ] | None = None
    limits: ProtocolLimits | None = None


class AuthFailedMessage(StrictMessage):
    type: Literal["auth_failed"] = "auth_failed"


class HeartbeatAckMessage(StrictMessage):
    type: Literal["heartbeat_ack"] = "heartbeat_ack"


class ErrorMessage(StrictMessage):
    type: Literal["error"] = "error"
    code: Annotated[str, StringConstraints(min_length=1, max_length=64)]


class CopySuccessMessage(StrictMessage):
    type: Literal["copy_success"] = "copy_success"
    preview: Annotated[str, StringConstraints(max_length=160)]


class TypeTextResultMessage(StrictMessage):
    type: Literal["action_result"] = "action_result"
    action: Literal["type_text"] = "type_text"
    request_id: Annotated[
        str,
        StringConstraints(
            min_length=8,
            max_length=64,
            pattern=r"^[A-Za-z0-9_-]+$",
        ),
    ]
    status: Literal["ok", "duplicate", "error"]
    code: Annotated[str, StringConstraints(min_length=1, max_length=64)] | None = None


class QuickActionResultMessage(StrictMessage):
    type: Literal["action_result"] = "action_result"
    action: Literal["quick_action"] = "quick_action"
    command: QuickActionCommand
    status: Literal["ok", "closed", "ignored", "error"]
    output_name: Annotated[str, StringConstraints(max_length=80)] | None = None


ServerMessage = (
    AuthOkMessage
    | AuthFailedMessage
    | HeartbeatAckMessage
    | ErrorMessage
    | CopySuccessMessage
    | TypeTextResultMessage
    | QuickActionResultMessage
)

AUTH_ADAPTER = TypeAdapter(AuthenticateMessage)
ACTION_ADAPTER = TypeAdapter(ActionMessage)
CLIENT_MESSAGE_ADAPTER = TypeAdapter(ClientMessage)
SERVER_MESSAGE_ADAPTER = TypeAdapter(ServerMessage)


def decode_json_message(raw: str) -> object:
    if len(raw.encode("utf-8")) > MAX_MESSAGE_BYTES:
        raise ValueError("message_too_large")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("message_must_be_object")
    return value


def parse_auth_message(raw: str) -> AuthenticateMessage:
    return AUTH_ADAPTER.validate_python(decode_json_message(raw))


def parse_action_message(raw: str) -> ActionMessage:
    return ACTION_ADAPTER.validate_python(decode_json_message(raw))


def parse_client_message(raw: str) -> ClientMessage:
    return CLIENT_MESSAGE_ADAPTER.validate_python(decode_json_message(raw))


def parse_server_message(value: object) -> ServerMessage:
    """Validate an internal or received server payload against the public protocol."""

    return SERVER_MESSAGE_ADAPTER.validate_python(value)


def encode_server_message(message: ServerMessage | dict[str, object]) -> dict[str, object]:
    """Return a JSON-ready, strictly validated server message."""

    validated = parse_server_message(message)
    return validated.model_dump(mode="json", exclude_none=True)
