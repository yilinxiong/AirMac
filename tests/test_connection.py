import asyncio
import json
from contextlib import suppress

import pytest

from connection import AuthFailureLimiter, ConnectionHandler
from protocol import TypeTextAction, encode_server_message, parse_client_message
from sessions import IdempotencyCache, SessionRegistry
from transport import TransportDisconnected


class MemoryTransport:
    peer = "192.168.1.2"
    last_message_size = 0

    def __init__(self):
        self.incoming = asyncio.Queue()
        self.outgoing = asyncio.Queue()
        self.closed = None
        self.sending = False

    async def receive(self):
        value = await self.incoming.get()
        if isinstance(value, Exception):
            raise value
        return parse_client_message(json.dumps(value))

    async def send(self, message):
        assert not self.sending
        self.sending = True
        await asyncio.sleep(0)
        self.outgoing.put_nowait(encode_server_message(message))
        self.sending = False

    async def close(self, code, reason):
        self.closed = (code, reason)
        self.incoming.put_nowait(TransportDisconnected(code, reason))

    async def result(self):
        return await asyncio.wait_for(self.outgoing.get(), 1)


class Store:
    authorized = True

    def authenticate(self, device_id, token):
        return token == "a" * 43

    def touch(self, device_id):
        pass

    def contains(self, device_id):
        return self.authorized


class Controller:
    def __init__(self):
        self.actions = []
        self.resets = 0
        self.notify = None

    async def reset(self):
        self.resets += 1

    async def wake_if_display_asleep(self):
        pass

    async def dispatch(self, message, notify):
        self.actions.append(message)
        self.notify = notify
        if isinstance(message, TypeTextAction):
            await notify(dict(type="action_result", action="type_text",
                              request_id=message.request_id, status="ok"))
        return True


AUTH = dict(type="authenticate", device_id="00000000-0000-4000-8000-000000000000", token="a" * 43)


@pytest.fixture
def setup():
    store, controller = Store(), Controller()
    sessions = SessionRegistry(controller, 16)
    return ConnectionHandler(store, controller, sessions), store, controller


async def connect(handler, auth=None):
    transport = MemoryTransport()
    transport.incoming.put_nowait(auth or AUTH)
    task = asyncio.create_task(handler.handle(transport))
    response = await transport.result()
    return transport, task, response


@pytest.mark.asyncio
async def test_transport_authentication_and_limiter(setup):
    handler, _, controller = setup
    for _ in range(10):
        transport, task, response = await connect(handler, dict(action="mouse_down"))
        assert response == {"type": "auth_failed"}
        await task
    transport, task, response = await connect(handler)
    assert response["code"] == "authentication_rate_limited"
    await task
    assert transport.closed[0] == 4012
    assert controller.actions == []


@pytest.mark.asyncio
async def test_success_clears_failures_and_timeout_is_bounded(setup):
    handler, _, _ = setup
    await handler.auth_limiter.record_failure(MemoryTransport.peer)
    transport, task, response = await connect(handler)
    assert response["type"] == "auth_ok"
    assert MemoryTransport.peer not in handler.auth_limiter.failures
    await handler.close()
    await task
    handler.auth_timeout = 0.01
    silent = MemoryTransport()
    await handler.handle(silent)
    assert silent.closed == (4008, "authentication_timeout")


@pytest.mark.asyncio
async def test_busy_replacement_cancellation_and_cleanup(setup):
    handler, _, controller = setup
    first, first_task, _ = await connect(handler)
    busy, busy_task, response = await connect(handler, {**AUTH, "device_id": "1" * 36})
    assert response["code"] == "controller_busy"
    await busy_task
    second, second_task, _ = await connect(handler)
    await first_task
    assert first.closed == (4010, "replaced")
    assert (await handler.sessions.snapshot()).transport is second
    await handler.close()
    await second_task
    assert await handler.sessions.snapshot() is None
    assert not handler.tasks
    assert controller.resets >= 3


@pytest.mark.asyncio
@pytest.mark.parametrize("revoke", [True, False])
async def test_monitor_releases_without_client_close(revoke, setup):
    handler, store, controller = setup
    transport, task, _ = await connect(handler)
    if revoke:
        store.authorized = False
    else:
        handler.sessions.idle_timeout = 0
    monitor = asyncio.create_task(handler.sessions.monitor(store, 0.001))
    try:
        await asyncio.wait_for(task, 1)
        assert transport.closed[0] == (4003 if revoke else 4004)
        assert await handler.sessions.snapshot() is None
        assert controller.resets >= 2
    finally:
        monitor.cancel()
        with suppress(asyncio.CancelledError):
            await monitor


@pytest.mark.asyncio
async def test_notifications_and_projection_reconnect(setup):
    handler, _, controller = setup
    payload = dict(action="type_text", request_id="projection_123", text="private text")
    first, task, _ = await connect(handler)
    first.incoming.put_nowait(payload)
    assert (await first.result())["status"] == "ok"
    await asyncio.gather(*(controller.notify({"type": "heartbeat_ack"}) for _ in range(5)))
    await first.close(4002, "client_background")
    await task
    second, task, _ = await connect(handler)
    second.incoming.put_nowait(payload)
    assert (await second.result())["status"] == "duplicate"
    assert len(controller.actions) == 1
    await handler.close()
    await task


def test_cache_is_bounded_and_expires_on_read():
    cache = IdempotencyCache(ttl_seconds=600, max_entries=1024)
    for i in range(1025):
        cache.record("device", str(i), now=0)
    assert len(cache.entries) == 1024
    assert not cache.contains("device", "0", now=1)
    assert cache.contains("device", "1024", now=599)
    assert not cache.contains("device", "1024", now=601)
    assert not cache.entries
