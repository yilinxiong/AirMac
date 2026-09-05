from __future__ import annotations

import asyncio
import logging
import math
import os
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable

import ApplicationServices as AX
import AppKit
import Quartz
from pynput.keyboard import Controller as KeyboardController, Key

from protocol import ActionMessage, MoveAction, QuickAction, ScrollAction, TypeTextAction
from controller_services.clipboard import ClipboardServiceMixin
from controller_services.pointer import PointerServiceMixin
from controller_services.system import SystemServiceMixin
from controller_services.wake import WakeServiceMixin


logger = logging.getLogger("AirMac.controller")
NotifyCallback = Callable[[dict[str, object]], Awaitable[None]]
APPS_APPLICATION_PATH = Path("/System/Applications/Apps.app")
CONTROL_CENTER_KEY_CODE = 8
CONTROL_CENTER_FLAGS = Quartz.kCGEventFlagMaskSecondaryFn
AX_FULLSCREEN_ATTRIBUTE = "AXFullScreen"
WINDOW_SHORTCUT_FLAGS = (
    Quartz.kCGEventFlagMaskSecondaryFn | Quartz.kCGEventFlagMaskControl
)
WINDOW_SHORTCUT_KEY_CODES = {
    "window_left": 123,
    "window_right": 124,
    "window_fill": 3,
    "window_center": 8,
}
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
        self.merged_count = 0
        self.dropped_count = 0
        self.high_water = 0

    @property
    def depth(self) -> int:
        return len(self._items)

    async def put(self, item: QueuedAction) -> bool:
        async with self._condition:
            if isinstance(item.message, (MoveAction, ScrollAction)):
                if self._merge_last(item):
                    self.merged_count += 1
                    return True
                if len(self._items) >= self.maxsize:
                    self.dropped_count += 1
                    return False
            else:
                while len(self._items) >= self.maxsize:
                    await self._condition.wait()
            self._items.append(item)
            self.high_water = max(self.high_water, len(self._items))
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
        if previous.message.action != item.message.action or previous.generation != item.generation:
            return False
        if isinstance(previous.message, MoveAction) and isinstance(
            item.message, MoveAction
        ):
            dx = max(-2000.0, min(2000.0, previous.message.dx + item.message.dx))
            dy = max(-2000.0, min(2000.0, previous.message.dy + item.message.dy))
            previous.message = previous.message.model_copy(update={"dx": dx, "dy": dy})
            return True
        if isinstance(previous.message, ScrollAction) and isinstance(
            item.message, ScrollAction
        ):
            dy = max(-4000.0, min(4000.0, previous.message.dy + item.message.dy))
            previous.message = previous.message.model_copy(update={"dy": dy})
            return True
        return False


class MacController(PointerServiceMixin, ClipboardServiceMixin, WakeServiceMixin, SystemServiceMixin):
    """Serializes macOS input without blocking the ASGI event loop."""

    def __init__(
        self,
        hud_path: Path | None = None,
        audio_switcher_path: Path | None = None,
        *,
        pointer_service: object | None = None,
        clipboard_service: object | None = None,
        wake_service: object | None = None,
        system_service: object | None = None,
        keep_reachable_on_ac: bool = False,
    ) -> None:
        self._keyboard: KeyboardController | None = None
        self.pointer_service = pointer_service
        self.clipboard_service = clipboard_service
        self.wake_service = wake_service
        self.system_service = system_service
        self.keep_reachable_on_ac = keep_reachable_on_ac
        self.hud_path = hud_path or Path(__file__).with_name("hud")
        self.audio_switcher_path = audio_switcher_path or Path(__file__).with_name(
            "audio-switcher"
        )
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
        self.wake_process: asyncio.subprocess.Process | None = None
        self.wake_task: asyncio.Task[None] | None = None
        self.reachability_process: asyncio.subprocess.Process | None = None
        self.reachability_task: asyncio.Task[None] | None = None
        self.generation = 0
        self.virtual_x = 0.0
        self.virtual_y = 0.0
        self.last_move_time = 0.0
        self.displays_cache: list[dict[str, float]] | None = None
        self.displays_cache_time = 0.0
        self.mouse_is_down = False
        self.control_high_water = 0
        self.control_dropped = 0
        self.expired_pointer_actions = 0

    @property
    def keyboard(self) -> KeyboardController:
        if self._keyboard is None:
            self._keyboard = KeyboardController()
        return self._keyboard

    async def wake_if_display_asleep(self) -> bool:
        if self.wake_service is not None:
            return await self.wake_service.wake_if_display_asleep()
        return await super().wake_if_display_asleep()

    async def start(self) -> None:
        if self.pointer_task is not None:
            return
        if self.keep_reachable_on_ac and self.wake_service is None:
            await self._start_reachability_assertion(os.getpid())
        elif self.wake_service is not None:
            start = getattr(self.wake_service, "start", None)
            if start is not None:
                await start()
        self.pointer_task = asyncio.create_task(
            self._pointer_worker(), name="airmac-pointer-worker"
        )
        self.control_task = asyncio.create_task(
            self._control_worker(), name="airmac-control-worker"
        )

    async def stop(self) -> None:
        await self.reset()
        if self.wake_service is not None:
            await self.wake_service.stop()
        else:
            await self._stop_wake_assertion()
            await self._stop_reachability_assertion()
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
            self.control_high_water = max(
                self.control_high_water, self.control_queue.qsize()
            )
            return True
        except asyncio.QueueFull:
            self.control_dropped += 1
            return False

    def snapshot_metrics(self) -> dict[str, int]:
        return {
            "pointer_depth": self.pointer_queue.depth,
            "pointer_high_water": self.pointer_queue.high_water,
            "pointer_merged": self.pointer_queue.merged_count,
            "pointer_dropped": self.pointer_queue.dropped_count,
            "pointer_expired": self.expired_pointer_actions,
            "control_depth": self.control_queue.qsize(),
            "control_high_water": self.control_high_water,
            "control_dropped": self.control_dropped,
        }

    @property
    def reachability_assertion_active(self) -> bool:
        return (
            self.reachability_process is not None
            and self.reachability_process.returncode is None
        )

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
        release_pointer = (
            self.pointer_service.release
            if self.pointer_service is not None
            else self._release_pointer
        )
        release_modifiers = (
            self.system_service.release_modifiers
            if self.system_service is not None
            else self._release_modifiers
        )
        await loop.run_in_executor(self.pointer_executor, release_pointer)
        await loop.run_in_executor(self.control_executor, release_modifiers)
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
            queue_age = time.monotonic() - item.enqueued_at
            if (
                item.message.action in {"move", "mouse_drag", "scroll"}
                and queue_age > 0.25
            ):
                self.expired_pointer_actions += 1
                continue
            try:
                execution_started = time.monotonic()
                await loop.run_in_executor(
                    self.pointer_executor,
                    (
                        self.pointer_service.execute
                        if self.pointer_service is not None
                        else self._execute_pointer
                    ),
                    item.message,
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
                if isinstance(item.message, TypeTextAction):
                    try:
                        await item.notify(
                            {
                                "type": "action_result",
                                "action": "type_text",
                                "request_id": item.message.request_id,
                                "status": "error",
                            }
                        )
                    except Exception:
                        logger.debug("Unable to report text projection failure")
                elif isinstance(item.message, QuickAction):
                    try:
                        await item.notify(
                            {
                                "type": "action_result",
                                "action": "quick_action",
                                "command": item.message.command,
                                "status": "error",
                            }
                        )
                    except Exception:
                        logger.debug("Unable to report quick action failure")
            finally:
                self.current_control_task = None
                self.control_queue.task_done()

    async def _execute_control(self, item: QueuedAction) -> None:
        message = item.message
        action = message.action
        loop = asyncio.get_running_loop()
        if action == "auto_copy":
            if self.clipboard_service is not None:
                await self.clipboard_service.auto_copy(item)
            else:
                await self._auto_copy(item)
        elif action == "type_text":
            assert isinstance(message, TypeTextAction)
            if self.clipboard_service is not None:
                await self.clipboard_service.type_text(message.text)
            else:
                await self._type_text(message.text)
            await item.notify(
                {
                    "type": "action_result",
                    "action": "type_text",
                    "request_id": message.request_id,
                    "status": "ok",
                }
            )
        elif action in {"type", "keydown", "media", "cmd_tab"}:
            await loop.run_in_executor(
                self.control_executor,
                (
                    self.system_service.execute_keyboard
                    if self.system_service is not None
                    else self._execute_keyboard
                ),
                message,
            )
        elif action == "quick_action":
            assert isinstance(message, QuickAction)
            if message.command == "screenshot":
                await self._run_process("screencapture", "-c", "-x")
            elif message.command == "close_fullscreen":
                result = await loop.run_in_executor(
                    self.control_executor,
                    (
                        self.system_service.close_fullscreen
                        if self.system_service is not None
                        else self._close_fullscreen_window
                    ),
                )
                await item.notify(
                    {
                        "type": "action_result",
                        "action": "quick_action",
                        "command": "close_fullscreen",
                        "status": result,
                    }
                )
            elif message.command == "cycle_audio_output":
                if not self.audio_switcher_path.is_file():
                    raise RuntimeError("Audio switcher is not installed")
                output_name = await self._run_process_output(
                    str(self.audio_switcher_path), "cycle"
                )
                await item.notify(
                    {
                        "type": "action_result",
                        "action": "quick_action",
                        "command": "cycle_audio_output",
                        "status": "ok",
                        "output_name": output_name[:80],
                    }
                )
            else:
                await loop.run_in_executor(
                    self.control_executor,
                    (
                        self.system_service.execute_quick_action
                        if self.system_service is not None
                        else self._execute_quick_action
                    ),
                    message.command,
                )
        elif action == "mission_control":
            await self._run_process(
                "osascript",
                "-e",
                'tell application "System Events" to key code 126 using control down',
            )
        elif action == "app_launcher":
            if APPS_APPLICATION_PATH.exists():
                await self._run_process("open", str(APPS_APPLICATION_PATH))
            else:
                await self._run_process("open", "-a", "Launchpad")
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
            if self.wake_service is not None:
                await self.wake_service.wake()
            else:
                await self._wake_display()

    async def _run_process(self, *arguments: str, timeout: float = 5.0) -> None:
        process = await asyncio.create_subprocess_exec(
            *arguments,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            await asyncio.wait_for(process.wait(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            await self._terminate_process(process)
            raise RuntimeError(
                f"Process timed out after {timeout:.1f}s: {arguments[0]}"
            ) from exc
        except asyncio.CancelledError:
            await self._terminate_process(process)
            raise
        if process.returncode != 0:
            raise RuntimeError(f"Process failed with status {process.returncode}")

    async def _run_process_output(
        self, *arguments: str, timeout: float = 5.0
    ) -> str:
        process = await asyncio.create_subprocess_exec(
            *arguments,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            await self._terminate_process(process)
            raise RuntimeError(
                f"Process timed out after {timeout:.1f}s: {arguments[0]}"
            ) from exc
        except asyncio.CancelledError:
            await self._terminate_process(process)
            raise
        if process.returncode != 0:
            raise RuntimeError(f"Process failed with status {process.returncode}")
        output = stdout.decode("utf-8", errors="replace").strip()
        if not output:
            raise RuntimeError("Process returned no output")
        return output

    async def _wait_for_background_process(
        self, process: asyncio.subprocess.Process
    ) -> None:
        try:
            await process.wait()
        except asyncio.CancelledError:
            await self._terminate_process(process)
            raise

    async def _terminate_process(self, process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        try:
            process.terminate()
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(process.wait(), timeout=1.0)
        except asyncio.TimeoutError:
            try:
                process.kill()
            except ProcessLookupError:
                return
            await process.wait()
