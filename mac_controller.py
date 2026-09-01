from __future__ import annotations

import asyncio
import logging
import math
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable

import pyperclip
import Quartz
from pynput.keyboard import Controller as KeyboardController, Key

from protocol import ActionMessage, MoveAction


logger = logging.getLogger("AirMac.controller")
NotifyCallback = Callable[[dict[str, object]], Awaitable[None]]
POINTER_ACTIONS = {
    "mouse_down",
    "mouse_up",
    "mouse_drag",
    "move",
    "click",
    "triple_click",
    "scroll",
}


@dataclass
class QueuedAction:
    message: ActionMessage
    generation: int
    notify: NotifyCallback
    enqueued_at: float = field(default_factory=time.monotonic)


class PointerQueue:
    def __init__(self, maxsize: int = 128) -> None:
        self.maxsize = maxsize
        self._items: deque[QueuedAction] = deque()
        self._condition = asyncio.Condition()

    async def put(self, item: QueuedAction) -> bool:
        async with self._condition:
            if isinstance(item.message, MoveAction):
                if self._merge_last(item):
                    return True
                if len(self._items) >= self.maxsize:
                    return False
            else:
                while len(self._items) >= self.maxsize:
                    await self._condition.wait()
            self._items.append(item)
            self._condition.notify_all()
            return True

    async def get(self) -> QueuedAction:
        async with self._condition:
            while not self._items:
                await self._condition.wait()
            item = self._items.popleft()
            self._condition.notify_all()
            return item

    async def clear(self) -> None:
        async with self._condition:
            self._items.clear()
            self._condition.notify_all()

    def _merge_last(self, item: QueuedAction) -> bool:
        if not self._items:
            return False
        previous = self._items[-1]
        if (
            not isinstance(previous.message, MoveAction)
            or previous.message.action != item.message.action
            or previous.generation != item.generation
        ):
            return False
        dx = max(-2000.0, min(2000.0, previous.message.dx + item.message.dx))
        dy = max(-2000.0, min(2000.0, previous.message.dy + item.message.dy))
        previous.message = previous.message.model_copy(update={"dx": dx, "dy": dy})
        return True


class MacController:
    """Serializes macOS input without blocking the ASGI event loop."""

    def __init__(self, hud_path: Path | None = None) -> None:
        self._keyboard: KeyboardController | None = None
        self.hud_path = hud_path or Path(__file__).with_name("hud")
        self.pointer_queue = PointerQueue()
        self.control_queue: asyncio.Queue[QueuedAction] = asyncio.Queue(maxsize=128)
        self.pointer_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="airmac-pointer"
        )
        self.control_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="airmac-control"
        )
        self.pointer_task: asyncio.Task[None] | None = None
        self.control_task: asyncio.Task[None] | None = None
        self.current_control_task: asyncio.Task[None] | None = None
        self.background_tasks: set[asyncio.Task[None]] = set()
        self.generation = 0
        self.virtual_x = 0.0
        self.virtual_y = 0.0
        self.last_move_time = 0.0
        self.displays_cache: list[dict[str, float]] | None = None
        self.displays_cache_time = 0.0
        self.mouse_is_down = False

    @property
    def keyboard(self) -> KeyboardController:
        if self._keyboard is None:
            self._keyboard = KeyboardController()
        return self._keyboard

    async def start(self) -> None:
        if self.pointer_task is not None:
            return
        self.pointer_task = asyncio.create_task(
            self._pointer_worker(), name="airmac-pointer-worker"
        )
        self.control_task = asyncio.create_task(
            self._control_worker(), name="airmac-control-worker"
        )

    async def stop(self) -> None:
        await self.reset()
        tasks = [task for task in (self.pointer_task, self.control_task) if task]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.pointer_task = None
        self.control_task = None
        self.pointer_executor.shutdown(wait=True, cancel_futures=True)
        self.control_executor.shutdown(wait=True, cancel_futures=True)

    async def dispatch(
        self, message: ActionMessage, notify: NotifyCallback
    ) -> bool:
        item = QueuedAction(message, self.generation, notify)
        if message.action in POINTER_ACTIONS:
            return await self.pointer_queue.put(item)
        try:
            self.control_queue.put_nowait(item)
            return True
        except asyncio.QueueFull:
            return False

    async def reset(self) -> None:
        reset_started = time.monotonic()
        self.generation += 1
        await self.pointer_queue.clear()
        while True:
            try:
                self.control_queue.get_nowait()
                self.control_queue.task_done()
            except asyncio.QueueEmpty:
                break
        if self.current_control_task:
            self.current_control_task.cancel()
            await asyncio.gather(self.current_control_task, return_exceptions=True)
            self.current_control_task = None
        if self.background_tasks:
            tasks = tuple(self.background_tasks)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self.pointer_executor, self._release_pointer)
        await loop.run_in_executor(self.control_executor, self._release_modifiers)
        self.last_move_time = 0.0
        reset_ms = (time.monotonic() - reset_started) * 1000
        if reset_ms > 200:
            logger.warning("Slow input reset duration_ms=%.1f", reset_ms)

    async def _pointer_worker(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            item = await self.pointer_queue.get()
            if item.generation != self.generation:
                continue
            try:
                execution_started = time.monotonic()
                await loop.run_in_executor(
                    self.pointer_executor, self._execute_pointer, item.message
                )
                finished = time.monotonic()
                queue_ms = (execution_started - item.enqueued_at) * 1000
                execution_ms = (finished - execution_started) * 1000
                if queue_ms > 100 or execution_ms > 100:
                    logger.warning(
                        "Slow pointer action=%s queue_ms=%.1f quartz_ms=%.1f",
                        item.message.action,
                        queue_ms,
                        execution_ms,
                    )
            except Exception:
                logger.exception("Pointer action failed: %s", item.message.action)

    async def _control_worker(self) -> None:
        while True:
            item = await self.control_queue.get()
            try:
                if item.generation != self.generation:
                    continue
                self.current_control_task = asyncio.create_task(
                    self._execute_control(item),
                    name=f"airmac-control-{item.message.action}",
                )
                await self.current_control_task
                duration_ms = (time.monotonic() - item.enqueued_at) * 1000
                slow_threshold = (
                    2000 if item.message.action in {"auto_copy", "type_text", "wake_watch"}
                    else 500
                )
                if duration_ms > slow_threshold:
                    logger.warning(
                        "Slow control action=%s total_ms=%.1f",
                        item.message.action,
                        duration_ms,
                    )
            except asyncio.CancelledError:
                if asyncio.current_task() and asyncio.current_task().cancelling():
                    raise
            except Exception:
                logger.exception("Control action failed: %s", item.message.action)
            finally:
                self.current_control_task = None
                self.control_queue.task_done()

    def _execute_pointer(self, message: ActionMessage) -> None:
        action = message.action
        current_pos = self._current_position()
        if action == "mouse_down":
            self._post_mouse(
                Quartz.kCGEventLeftMouseDown,
                current_pos,
                Quartz.kCGMouseButtonLeft,
            )
            self.mouse_is_down = True
        elif action == "mouse_up":
            self._post_mouse(
                Quartz.kCGEventLeftMouseUp, current_pos, Quartz.kCGMouseButtonLeft
            )
            self.mouse_is_down = False
        elif action in {"move", "mouse_drag"}:
            assert isinstance(message, MoveAction)
            now = time.monotonic()
            if now - self.last_move_time > 0.2:
                self.virtual_x, self.virtual_y = current_pos
            self.virtual_x += message.dx
            self.virtual_y += message.dy
            self.virtual_x, self.virtual_y = self._clamp_to_displays(
                self.virtual_x, self.virtual_y
            )
            self.last_move_time = now
            event_type = (
                Quartz.kCGEventLeftMouseDragged
                if action == "mouse_drag"
                else Quartz.kCGEventMouseMoved
            )
            event = Quartz.CGEventCreateMouseEvent(
                None,
                event_type,
                (self.virtual_x, self.virtual_y),
                Quartz.kCGMouseButtonLeft,
            )
            Quartz.CGEventSetIntegerValueField(
                event, Quartz.kCGMouseEventDeltaX, int(message.dx)
            )
            Quartz.CGEventSetIntegerValueField(
                event, Quartz.kCGMouseEventDeltaY, int(message.dy)
            )
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
        elif action == "click":
            button = message.button
            if button == "right":
                down_type = Quartz.kCGEventRightMouseDown
                up_type = Quartz.kCGEventRightMouseUp
                quartz_button = Quartz.kCGMouseButtonRight
            else:
                down_type = Quartz.kCGEventLeftMouseDown
                up_type = Quartz.kCGEventLeftMouseUp
                quartz_button = Quartz.kCGMouseButtonLeft
            self._post_mouse(down_type, current_pos, quartz_button)
            self._post_mouse(up_type, current_pos, quartz_button)
        elif action == "triple_click":
            for click_state in (2, 3):
                for event_type in (
                    Quartz.kCGEventLeftMouseDown,
                    Quartz.kCGEventLeftMouseUp,
                ):
                    event = Quartz.CGEventCreateMouseEvent(
                        None,
                        event_type,
                        current_pos,
                        Quartz.kCGMouseButtonLeft,
                    )
                    Quartz.CGEventSetIntegerValueField(
                        event, Quartz.kCGMouseEventClickState, click_state
                    )
                    Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
        elif action == "scroll":
            event = Quartz.CGEventCreateScrollWheelEvent(
                None, Quartz.kCGScrollEventUnitPixel, 1, int(-message.dy)
            )
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)

    async def _execute_control(self, item: QueuedAction) -> None:
        message = item.message
        action = message.action
        loop = asyncio.get_running_loop()
        if action == "auto_copy":
            await self._auto_copy(item)
        elif action == "type_text":
            await self._type_text(message.text)
        elif action in {"type", "keydown", "media", "cmd_tab"}:
            await loop.run_in_executor(
                self.control_executor, self._execute_keyboard, message
            )
        elif action == "mission_control":
            await self._run_process(
                "osascript",
                "-e",
                'tell application "System Events" to key code 126 using control down',
            )
        elif action == "space_left":
            await self._run_process(
                "osascript",
                "-e",
                'tell application "System Events" to key code 123 using control down',
            )
        elif action == "space_right":
            await self._run_process(
                "osascript",
                "-e",
                'tell application "System Events" to key code 124 using control down',
            )
        elif action == "display_sleep":
            await self._run_process("pmset", "displaysleepnow")
        elif action == "wake_watch":
            await self._wake_display()

    async def _auto_copy(self, item: QueuedAction) -> None:
        loop = asyncio.get_running_loop()
        old_clipboard = await loop.run_in_executor(
            self.control_executor, pyperclip.paste
        )
        restored_or_copied = False
        await loop.run_in_executor(self.control_executor, pyperclip.copy, "")
        try:
            await self._run_process(
                "osascript",
                "-e",
                'tell application "System Events" to keystroke "c" using command down',
            )
            await asyncio.sleep(0.15)
            new_clipboard = await loop.run_in_executor(
                self.control_executor, pyperclip.paste
            )
            if not new_clipboard:
                await loop.run_in_executor(
                    self.control_executor, pyperclip.copy, old_clipboard
                )
            else:
                restored_or_copied = True
                preview = (
                    new_clipboard[:20] + "..."
                    if len(new_clipboard) > 20
                    else new_clipboard
                )
                await item.notify({"type": "copy_success", "preview": preview})
                if self.hud_path.exists():
                    process = await asyncio.create_subprocess_exec(
                        str(self.hud_path), "✅ 自动复制成功"
                    )
                    task = asyncio.create_task(
                        self._wait_for_background_process(process),
                        name="airmac-hud-process",
                    )
                    self.background_tasks.add(task)
                    task.add_done_callback(self.background_tasks.discard)
                else:
                    await self._run_process(
                        "osascript",
                        "-e",
                        'display notification "已复制所选文本" with title "AirMac"',
                    )
        finally:
            if not restored_or_copied and old_clipboard:
                await loop.run_in_executor(
                    self.control_executor, pyperclip.copy, old_clipboard
                )

    async def _type_text(self, text: str) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self.control_executor, pyperclip.copy, text)
        await asyncio.sleep(0.15)
        await loop.run_in_executor(self.control_executor, self._paste)
        await asyncio.sleep(min(0.8, 0.15 + len(text) * 0.005))
        await loop.run_in_executor(self.control_executor, self._press_and_release, Key.enter)

    async def _wake_display(self) -> None:
        process = await asyncio.create_subprocess_exec(
            "caffeinate",
            "-u",
            "-t",
            "3",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.sleep(0.5)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            self.control_executor, self._press_and_release, Key.shift
        )
        await asyncio.sleep(1.5)
        await loop.run_in_executor(
            self.control_executor, self._press_and_release, Key.shift
        )
        await process.wait()

    async def _run_process(self, *arguments: str) -> None:
        process = await asyncio.create_subprocess_exec(
            *arguments,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            await process.wait()
        except asyncio.CancelledError:
            if process.returncode is None:
                try:
                    process.terminate()
                except ProcessLookupError:
                    pass
                await process.wait()
            raise

    async def _wait_for_background_process(
        self, process: asyncio.subprocess.Process
    ) -> None:
        try:
            await process.wait()
        except asyncio.CancelledError:
            if process.returncode is None:
                try:
                    process.terminate()
                except ProcessLookupError:
                    pass
                await process.wait()
            raise

    def _execute_keyboard(self, message: ActionMessage) -> None:
        if message.action == "type":
            self.keyboard.type(message.char)
        elif message.action == "keydown":
            key = Key.backspace if message.key == "Backspace" else Key.enter
            self._press_and_release(key)
        elif message.action == "cmd_tab":
            self.keyboard.press(Key.cmd)
            self._press_and_release(Key.tab)
            self.keyboard.release(Key.cmd)
        elif message.action == "media":
            if message.command == "playpause":
                self._press_and_release(Key.media_play_pause)
            else:
                self.keyboard.press(Key.cmd)
                self.keyboard.press(Key.ctrl)
                self._press_and_release("f")
                self.keyboard.release(Key.ctrl)
                self.keyboard.release(Key.cmd)

    def _paste(self) -> None:
        self.keyboard.press(Key.cmd)
        self._press_and_release("v")
        self.keyboard.release(Key.cmd)

    def _press_and_release(self, key: object) -> None:
        self.keyboard.press(key)
        self.keyboard.release(key)

    def _release_modifiers(self) -> None:
        for key in (Key.cmd, Key.ctrl, Key.shift, Key.alt):
            try:
                self.keyboard.release(key)
            except Exception:
                logger.debug("Modifier was not held: %s", key)

    def _release_pointer(self) -> None:
        try:
            self._post_mouse(
                Quartz.kCGEventLeftMouseUp,
                self._current_position(),
                Quartz.kCGMouseButtonLeft,
            )
        finally:
            self.mouse_is_down = False

    def _post_mouse(self, event_type: int, position: tuple[float, float], button: int) -> None:
        event = Quartz.CGEventCreateMouseEvent(None, event_type, position, button)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)

    def _current_position(self) -> tuple[float, float]:
        event = Quartz.CGEventCreate(None)
        point = Quartz.CGEventGetLocation(event)
        return point.x, point.y

    def _get_displays(self) -> list[dict[str, float]] | None:
        now = time.monotonic()
        if self.displays_cache is None or now - self.displays_cache_time > 5.0:
            success, active_displays, count = Quartz.CGGetActiveDisplayList(
                10, None, None
            )
            if success == 0 and count > 0:
                self.displays_cache = []
                for index in range(count):
                    bounds = Quartz.CGDisplayBounds(active_displays[index])
                    self.displays_cache.append(
                        {
                            "min_x": bounds.origin.x,
                            "max_x": bounds.origin.x + bounds.size.width - 1,
                            "min_y": bounds.origin.y,
                            "max_y": bounds.origin.y + bounds.size.height - 1,
                        }
                    )
            self.displays_cache_time = now
        return self.displays_cache

    def _clamp_to_displays(self, x: float, y: float) -> tuple[float, float]:
        displays = self._get_displays()
        if not displays or not math.isfinite(x) or not math.isfinite(y):
            return x, y
        for bounds in displays:
            if (
                bounds["min_x"] <= x <= bounds["max_x"]
                and bounds["min_y"] <= y <= bounds["max_y"]
            ):
                return x, y
        best_x, best_y = x, y
        min_distance = math.inf
        for bounds in displays:
            candidate_x = max(bounds["min_x"], min(x, bounds["max_x"]))
            candidate_y = max(bounds["min_y"], min(y, bounds["max_y"]))
            distance = (candidate_x - x) ** 2 + (candidate_y - y) ** 2
            if distance < min_distance:
                min_distance = distance
                best_x, best_y = candidate_x, candidate_y
        return best_x, best_y
