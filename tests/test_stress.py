from __future__ import annotations

import json

import pytest

from mac_controller import PointerQueue, QueuedAction
from protocol import MoveAction, parse_action_message


async def noop_notify(_: dict[str, object]) -> None:
    pass


@pytest.mark.asyncio
async def test_large_pointer_burst_stays_bounded() -> None:
    queue = PointerQueue(maxsize=128)
    for _ in range(10_000):
        move = parse_action_message(
            json.dumps({"action": "move", "dx": 0.25, "dy": -0.25})
        )
        assert await queue.put(QueuedAction(move, 1, noop_notify))

    assert queue.depth == 1
    assert queue.high_water == 1
    assert queue.merged_count == 9_999
    merged = await queue.get()
    assert isinstance(merged.message, MoveAction)
    assert merged.message.dx == 2000
    assert merged.message.dy == -2000


@pytest.mark.asyncio
async def test_large_scroll_burst_stays_bounded() -> None:
    queue = PointerQueue(maxsize=128)
    for _ in range(10_000):
        scroll = parse_action_message(json.dumps({"action": "scroll", "dy": 1}))
        assert await queue.put(QueuedAction(scroll, 1, noop_notify))

    assert queue.depth == 1
    assert queue.high_water == 1
    assert queue.merged_count == 9_999
    assert (await queue.get()).message.dy == 4000
