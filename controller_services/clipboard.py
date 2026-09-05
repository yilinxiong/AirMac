"""Default macOS clipboard service used by MacController."""

from __future__ import annotations

import asyncio

from pynput.keyboard import Key


class ClipboardServiceMixin:
    async def _auto_copy(self, item: QueuedAction) -> None:
        old_clipboard = await self._clipboard_read()
        restored_or_copied = False
        await self._clipboard_write("")
        try:
            await self._run_process(
                "osascript",
                "-e",
                'tell application "System Events" to keystroke "c" using command down',
            )
            await asyncio.sleep(0.15)
            new_clipboard = await self._clipboard_read()
            if new_clipboard:
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
                await self._clipboard_write(old_clipboard)

    async def _type_text(self, text: str) -> None:
        loop = asyncio.get_running_loop()
        old_clipboard = await self._clipboard_read()
        await self._clipboard_write(text)
        try:
            await asyncio.sleep(0.15)
            await loop.run_in_executor(self.control_executor, self._paste)
            await asyncio.sleep(min(0.8, 0.15 + len(text) * 0.005))
            await loop.run_in_executor(
                self.control_executor, self._press_and_release, Key.enter
            )
        finally:
            current_clipboard = await self._clipboard_read()
            if current_clipboard == text:
                await self._clipboard_write(old_clipboard)

    async def _clipboard_read(self) -> str:
        process = await asyncio.create_subprocess_exec(
            "pbpaste",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=2.0)
        except asyncio.TimeoutError as exc:
            await self._terminate_process(process)
            raise RuntimeError("pbpaste timed out") from exc
        except asyncio.CancelledError:
            await self._terminate_process(process)
            raise
        if process.returncode != 0:
            raise RuntimeError(f"pbpaste failed with status {process.returncode}")
        return stdout.decode("utf-8", errors="replace")

    async def _clipboard_write(self, text: str) -> None:
        process = await asyncio.create_subprocess_exec(
            "pbcopy",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            await asyncio.wait_for(
                process.communicate(text.encode("utf-8")), timeout=2.0
            )
        except asyncio.TimeoutError as exc:
            await self._terminate_process(process)
            raise RuntimeError("pbcopy timed out") from exc
        except asyncio.CancelledError:
            await self._terminate_process(process)
            raise
        if process.returncode != 0:
            raise RuntimeError(f"pbcopy failed with status {process.returncode}")

    def _paste(self) -> None:
        self.keyboard.press(Key.cmd)
        self._press_and_release("v")
        self.keyboard.release(Key.cmd)
