from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

import mac_controller
from mac_controller import MacController, PointerQueue, QueuedAction
from protocol import MoveAction, ScrollAction, parse_action_message


async def noop_notify(_: dict[str, object]) -> None:
    pass


class FakeProcess:
    def __init__(self) -> None:
        self.returncode: int | None = None
        self.finished = asyncio.Event()
        self.terminated = False

    async def wait(self) -> int:
        await self.finished.wait()
        assert self.returncode is not None
        return self.returncode

    async def communicate(self, _input: bytes | None = None) -> tuple[bytes, bytes]:
        await self.finished.wait()
        return b"", b""

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = -15
        self.finished.set()

    def kill(self) -> None:
        self.terminate()


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
async def test_pointer_queue_coalesces_scroll_bursts() -> None:
    queue = PointerQueue(maxsize=2)
    for dy in (3, 5, -2):
        scroll = parse_action_message(json.dumps({"action": "scroll", "dy": dy}))
        assert await queue.put(QueuedAction(scroll, 1, noop_notify))
    merged = await queue.get()
    assert isinstance(merged.message, ScrollAction)
    assert merged.message.dy == 6
    assert queue.merged_count == 2


@pytest.mark.asyncio
async def test_app_launcher_prefers_modern_macos_apps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    controller = MacController()
    apps_path = tmp_path / "Apps.app"
    apps_path.mkdir()
    calls: list[tuple[str, ...]] = []

    async def fake_run_process(*arguments: str, timeout: float = 5.0) -> None:
        calls.append(arguments)

    monkeypatch.setattr(mac_controller, "APPS_APPLICATION_PATH", apps_path)
    monkeypatch.setattr(controller, "_run_process", fake_run_process)
    message = parse_action_message(json.dumps({"action": "app_launcher"}))
    await controller._execute_control(QueuedAction(message, 1, noop_notify))

    assert calls == [("open", str(apps_path))]


def test_quick_action_uses_fixed_quartz_shortcuts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = MacController()
    calls: list[tuple[int, int]] = []
    monkeypatch.setattr(
        controller,
        "_post_key_code",
        lambda key_code, flags: calls.append((key_code, flags)),
    )

    controller._execute_quick_action("window_left")
    controller._execute_quick_action("window_fill")
    controller._execute_quick_action("open_control_center")

    assert calls == [
        (123, mac_controller.WINDOW_SHORTCUT_FLAGS),
        (3, mac_controller.WINDOW_SHORTCUT_FLAGS),
        (
            mac_controller.CONTROL_CENTER_KEY_CODE,
            mac_controller.CONTROL_CENTER_FLAGS,
        ),
    ]


def test_close_fullscreen_window_uses_accessibility_close_button(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = MacController()
    values = {
        ("system", mac_controller.AX.kAXFocusedApplicationAttribute): "application",
        ("application", mac_controller.AX.kAXFocusedWindowAttribute): "window",
        ("window", mac_controller.AX_FULLSCREEN_ATTRIBUTE): True,
        ("window", mac_controller.AX.kAXCloseButtonAttribute): "close-button",
    }
    pressed: list[tuple[str, str]] = []

    monkeypatch.setattr(
        mac_controller.AX, "AXUIElementCreateSystemWide", lambda: "system"
    )
    monkeypatch.setattr(
        mac_controller.AX,
        "AXUIElementCopyAttributeValue",
        lambda element, attribute, _: (
            mac_controller.AX.kAXErrorSuccess,
            values[(element, attribute)],
        ),
    )
    monkeypatch.setattr(
        mac_controller.AX,
        "AXUIElementPerformAction",
        lambda element, action: (
            pressed.append((element, action)) or mac_controller.AX.kAXErrorSuccess
        ),
    )

    assert controller._close_fullscreen_window() == "closed"
    assert pressed == [("close-button", mac_controller.AX.kAXPressAction)]


def test_close_fullscreen_window_ignores_regular_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = MacController()
    values = {
        ("system", mac_controller.AX.kAXFocusedApplicationAttribute): "application",
        ("application", mac_controller.AX.kAXFocusedWindowAttribute): "window",
        ("window", mac_controller.AX_FULLSCREEN_ATTRIBUTE): False,
    }
    pressed: list[tuple[object, object]] = []

    monkeypatch.setattr(
        mac_controller.AX, "AXUIElementCreateSystemWide", lambda: "system"
    )
    monkeypatch.setattr(
        mac_controller.AX,
        "AXUIElementCopyAttributeValue",
        lambda element, attribute, _: (
            mac_controller.AX.kAXErrorSuccess,
            values[(element, attribute)],
        ),
    )
    monkeypatch.setattr(
        mac_controller.AX,
        "AXUIElementPerformAction",
        lambda element, action: pressed.append((element, action)),
    )

    assert controller._close_fullscreen_window() == "ignored"
    assert pressed == []


@pytest.mark.asyncio
@pytest.mark.parametrize("result", ["closed", "ignored", "error"])
async def test_close_fullscreen_reports_result(
    result: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    controller = MacController()
    notifications: list[dict[str, object]] = []

    async def notify(payload: dict[str, object]) -> None:
        notifications.append(payload)

    monkeypatch.setattr(controller, "_close_fullscreen_window", lambda: result)
    message = parse_action_message(
        json.dumps({"action": "quick_action", "command": "close_fullscreen"})
    )
    await controller._execute_control(QueuedAction(message, 1, notify))

    assert notifications == [
        {
            "type": "action_result",
            "action": "quick_action",
            "command": "close_fullscreen",
            "status": result,
        }
    ]


@pytest.mark.asyncio
async def test_screenshot_quick_action_uses_parameterized_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = MacController()
    calls: list[tuple[str, ...]] = []

    async def fake_run_process(*arguments: str, timeout: float = 5.0) -> None:
        calls.append(arguments)

    monkeypatch.setattr(controller, "_run_process", fake_run_process)
    message = parse_action_message(
        json.dumps({"action": "quick_action", "command": "screenshot"})
    )
    await controller._execute_control(QueuedAction(message, 1, noop_notify))

    assert calls == [("screencapture", "-c", "-x")]


@pytest.mark.asyncio
async def test_audio_output_shortcut_reports_selected_device(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audio_switcher = tmp_path / "audio-switcher"
    audio_switcher.touch()
    controller = MacController(audio_switcher_path=audio_switcher)
    calls: list[tuple[str, ...]] = []
    notifications: list[dict[str, object]] = []

    async def fake_run_process_output(
        *arguments: str, timeout: float = 5.0
    ) -> str:
        calls.append(arguments)
        return "Living Room Speakers"

    async def notify(payload: dict[str, object]) -> None:
        notifications.append(payload)

    monkeypatch.setattr(controller, "_run_process_output", fake_run_process_output)
    message = parse_action_message(
        json.dumps({"action": "quick_action", "command": "cycle_audio_output"})
    )
    await controller._execute_control(QueuedAction(message, 1, notify))

    assert calls == [(str(audio_switcher), "cycle")]
    assert notifications == [
        {
            "type": "action_result",
            "action": "quick_action",
            "command": "cycle_audio_output",
            "status": "ok",
            "output_name": "Living Room Speakers",
        }
    ]


@pytest.mark.asyncio
async def test_missing_audio_switcher_reports_quick_action_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = MacController(audio_switcher_path=tmp_path / "missing")
    notifications: list[dict[str, object]] = []

    async def notify(payload: dict[str, object]) -> None:
        notifications.append(payload)

    monkeypatch.setattr(controller, "_release_pointer", lambda: None)
    monkeypatch.setattr(controller, "_release_modifiers", lambda: None)
    await controller.start()
    try:
        message = parse_action_message(
            json.dumps({"action": "quick_action", "command": "cycle_audio_output"})
        )
        assert await controller.dispatch(message, notify)
        await asyncio.wait_for(controller.control_queue.join(), timeout=1)
    finally:
        await controller.stop()

    assert notifications == [
        {
            "type": "action_result",
            "action": "quick_action",
            "command": "cycle_audio_output",
            "status": "error",
        }
    ]


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
                json.dumps(
                    {
                        "action": "type_text",
                        "request_id": "request_second",
                        "text": "second",
                    }
                )
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


@pytest.mark.asyncio
async def test_stale_pointer_motion_is_discarded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = MacController()
    executed: list[str] = []
    move = parse_action_message(json.dumps({"action": "move", "dx": 1, "dy": 1}))
    item = QueuedAction(move, controller.generation, noop_notify)
    item.enqueued_at -= 1
    await controller.pointer_queue.put(item)
    monkeypatch.setattr(
        controller, "_execute_pointer", lambda message: executed.append(message.action)
    )
    monkeypatch.setattr(controller, "_release_pointer", lambda: None)
    monkeypatch.setattr(controller, "_release_modifiers", lambda: None)
    await controller.start()
    try:
        await asyncio.sleep(0.02)
        assert executed == []
        assert controller.expired_pointer_actions == 1
    finally:
        await controller.stop()


@pytest.mark.asyncio
async def test_text_projection_reports_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = MacController()
    notifications: list[dict[str, object]] = []

    async def notify(payload: dict[str, object]) -> None:
        notifications.append(payload)

    async def fake_type_text(_: str) -> None:
        pass

    monkeypatch.setattr(controller, "_type_text", fake_type_text)
    monkeypatch.setattr(controller, "_release_pointer", lambda: None)
    monkeypatch.setattr(controller, "_release_modifiers", lambda: None)
    await controller.start()
    try:
        message = parse_action_message(
            json.dumps(
                {
                    "action": "type_text",
                    "request_id": "projection_ack_1",
                    "text": "hello",
                }
            )
        )
        assert await controller.dispatch(message, notify)
        await asyncio.wait_for(controller.control_queue.join(), timeout=1)
        assert notifications == [
            {
                "type": "action_result",
                "action": "type_text",
                "request_id": "projection_ack_1",
                "status": "ok",
            }
        ]
    finally:
        await controller.stop()


@pytest.mark.asyncio
async def test_wake_uses_nonblocking_display_assertion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = MacController()
    process = FakeProcess()
    calls: list[tuple[object, ...]] = []

    async def fake_create_subprocess_exec(*args: object, **_: object) -> FakeProcess:
        calls.append(args)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(controller, "_press_and_release", lambda _: None)
    monkeypatch.setattr(controller, "_release_pointer", lambda: None)
    monkeypatch.setattr(controller, "_release_modifiers", lambda: None)

    started = asyncio.get_running_loop().time()
    await controller._wake_display()
    elapsed = asyncio.get_running_loop().time() - started
    assert calls == [("caffeinate", "-d", "-u", "-t", "30")]
    assert elapsed < 1
    assert process.returncode is None
    await controller.reset()
    assert not process.terminated
    await controller._stop_wake_assertion()
    assert process.terminated


@pytest.mark.asyncio
async def test_subprocess_timeout_terminates_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = MacController()
    process = FakeProcess()

    async def fake_create_subprocess_exec(*_: object, **__: object) -> FakeProcess:
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    with pytest.raises(RuntimeError, match="timed out"):
        await controller._run_process("osascript", timeout=0.01)
    assert process.terminated


@pytest.mark.asyncio
async def test_subprocess_nonzero_status_is_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = MacController()
    process = FakeProcess()
    process.returncode = 1
    process.finished.set()

    async def fake_create_subprocess_exec(*_: object, **__: object) -> FakeProcess:
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    with pytest.raises(RuntimeError, match="status 1"):
        await controller._run_process("osascript")


@pytest.mark.asyncio
async def test_text_projection_restores_unchanged_clipboard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = MacController()
    clipboard_reads = iter(["original clipboard", "projected text"])
    clipboard_writes: list[str] = []

    async def clipboard_read() -> str:
        return next(clipboard_reads)

    async def clipboard_write(value: str) -> None:
        clipboard_writes.append(value)

    monkeypatch.setattr(controller, "_clipboard_read", clipboard_read)
    monkeypatch.setattr(controller, "_clipboard_write", clipboard_write)
    monkeypatch.setattr(controller, "_paste", lambda: None)
    monkeypatch.setattr(controller, "_press_and_release", lambda _: None)

    await controller._type_text("projected text")
    assert clipboard_writes == ["projected text", "original clipboard"]


@pytest.mark.asyncio
async def test_cancelled_clipboard_process_is_terminated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = MacController()
    process = FakeProcess()

    async def fake_create_subprocess_exec(*_: object, **__: object) -> FakeProcess:
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    task = asyncio.create_task(controller._clipboard_read())
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert process.terminated
