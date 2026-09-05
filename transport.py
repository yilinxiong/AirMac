"""Transport-neutral client connection interfaces and WebSocket adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from protocol import ClientMessage, ServerMessage


@dataclass(slots=True)
class TransportDisconnected(Exception):
    code: int = 1005
    reason: str = ""


@runtime_checkable
class ClientTransport(Protocol):
    @property
    def peer(self) -> str: ...

    @property
    def last_message_size(self) -> int: ...

    async def receive(self) -> ClientMessage: ...

    async def send(self, message: ServerMessage | dict[str, object]) -> None: ...

    async def close(self, code: int, reason: str) -> None: ...
