from __future__ import annotations

import json
import asyncio

import pytest

from mac_controller import MacController, PointerQueue, QueuedAction
from protocol import MoveAction, parse_action_message


async def noop_notify(_: dict[str, object]) -> None:
    pass


@pytest.mark.asyncio
async def test_pointer_queue_coalesces_consecutive_motion() -> None:
    queue = PointerQueue(maxsize=2)
    first = parse_action_message(json.dumps({"action": "move", "dx": 3, "dy": 4}))
    second = parse_action_message(json.dumps({"action": "move", "dx": 5, "dy": -2}))
    await queue.put(QueuedAction(first, 1, noop_notify))
    await queue.put(QueuedAction(second, 1, noop_notify))

    merged = await queue.get()
    assert isinstance(merged.message, MoveAction)
    assert merged.message.dx == 8
    assert merged.message.dy == 2


@pytest.mark.asyncio
async def test_pointer_queue_does_not_merge_across_state_event() -> None:
    queue = PointerQueue(maxsize=4)
    move = parse_action_message(json.dumps({"action": "move", "dx": 1, "dy": 1}))
    down = parse_action_message(json.dumps({"action": "mouse_down"}))
    await queue.put(QueuedAction(move, 1, noop_notify))
    await queue.put(QueuedAction(down, 1, noop_notify))
    await queue.put(QueuedAction(move, 1, noop_notify))

    assert (await queue.get()).message.action == "move"
    assert (await queue.get()).message.action == "mouse_down"
    assert (await queue.get()).message.action == "move"


@pytest.mark.asyncio
async def test_control_worker_serializes_clipboard_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = MacController()
    first_started = asyncio.Event()
    allow_first_to_finish = asyncio.Event()
    execution_order: list[str] = []

    async def fake_execute_control(item: QueuedAction) -> None:
        execution_order.append(item.message.action)
        if item.message.action == "auto_copy":
            first_started.set()
            await allow_first_to_finish.wait()

    monkeypatch.setattr(controller, "_execute_control", fake_execute_control)
    monkeypatch.setattr(controller, "_release_pointer", lambda: None)
    monkeypatch.setattr(controller, "_release_modifiers", lambda: None)
    await controller.start()
    try:
        assert await controller.dispatch(
            parse_action_message(json.dumps({"action": "auto_copy"})), noop_notify
        )
        assert await controller.dispatch(
            parse_action_message(
                json.dumps({"action": "type_text", "text": "second"})
            ),
            noop_notify,
        )
        await asyncio.wait_for(first_started.wait(), timeout=1)
        await asyncio.sleep(0)
        assert execution_order == ["auto_copy"]
        allow_first_to_finish.set()
        await asyncio.wait_for(controller.control_queue.join(), timeout=1)
        assert execution_order == ["auto_copy", "type_text"]
    finally:
        await controller.stop()


@pytest.mark.asyncio
async def test_reset_cancels_active_control_and_releases_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = MacController()
    started = asyncio.Event()
    cancelled = asyncio.Event()
    releases: list[str] = []

    async def blocked_control(_: QueuedAction) -> None:
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    monkeypatch.setattr(controller, "_execute_control", blocked_control)
    monkeypatch.setattr(
        controller, "_release_pointer", lambda: releases.append("pointer")
    )
    monkeypatch.setattr(
        controller, "_release_modifiers", lambda: releases.append("modifiers")
    )
    await controller.start()
    try:
        assert await controller.dispatch(
            parse_action_message(json.dumps({"action": "auto_copy"})), noop_notify
        )
        await asyncio.wait_for(started.wait(), timeout=1)
        await controller.reset()
        assert cancelled.is_set()
        assert releases == ["pointer", "modifiers"]
    finally:
        await controller.stop()
