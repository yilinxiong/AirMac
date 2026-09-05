"""FastAPI WebSocket adapter for the AirMac transport protocol."""

from __future__ import annotations

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

from protocol import ClientMessage, ServerMessage, encode_server_message, parse_client_message
from transport import TransportDisconnected


class WebSocketTransport:
    """Translate text WebSocket frames into the transport-neutral protocol."""

    def __init__(self, websocket: WebSocket, peer: str) -> None:
        self.websocket = websocket
        self._peer = peer
        self._last_message_size = 0

    @property
    def peer(self) -> str:
        return self._peer

    @property
    def last_message_size(self) -> int:
        return self._last_message_size

    async def receive(self) -> ClientMessage:
        try:
            raw = await self.websocket.receive_text()
        except WebSocketDisconnect as exc:
            raise TransportDisconnected(exc.code, exc.reason or "") from exc
        self._last_message_size = len(raw.encode("utf-8"))
        return parse_client_message(raw)

    async def send(self, message: ServerMessage | dict[str, object]) -> None:
        try:
            await self.websocket.send_json(encode_server_message(message))
        except (RuntimeError, WebSocketDisconnect) as exc:
            raise TransportDisconnected() from exc

    async def close(self, code: int, reason: str) -> None:
        try:
            await self.websocket.close(code=code, reason=reason)
        except (RuntimeError, WebSocketDisconnect) as exc:
            raise TransportDisconnected(code, reason) from exc
