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


class StrictMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class AuthenticateMessage(StrictMessage):
    type: Literal["authenticate"]
    device_id: Annotated[str, StringConstraints(min_length=36, max_length=36)]
    token: Annotated[str, StringConstraints(min_length=32, max_length=128)]


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


FiniteMove = Annotated[float, Field(ge=-500, le=500, allow_inf_nan=False)]


class MoveAction(ActionBase):
    action: Literal["move", "mouse_drag"]
    dx: FiniteMove
    dy: FiniteMove


class ClickAction(ActionBase):
    action: Literal["click"]
    button: Literal["left", "right"] = "left"


class ScrollAction(ActionBase):
    action: Literal["scroll"]
    dy: Annotated[float, Field(ge=-1000, le=1000, allow_inf_nan=False)]


class TypeAction(ActionBase):
    action: Literal["type"]
    char: Annotated[str, StringConstraints(min_length=1, max_length=16)]


class KeydownAction(ActionBase):
    action: Literal["keydown"]
    key: Literal["Backspace", "Enter"]


class MediaAction(ActionBase):
    action: Literal["media"]
    command: Literal["playpause", "fullscreen"]


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
    text: Annotated[str, StringConstraints(min_length=1, max_length=32_768)]

    @field_validator("text")
    @classmethod
    def limit_utf8_size(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 32_768:
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
    | TypeTextAction,
    Field(discriminator="action"),
]

AUTH_ADAPTER = TypeAdapter(AuthenticateMessage)
ACTION_ADAPTER = TypeAdapter(ActionMessage)


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
