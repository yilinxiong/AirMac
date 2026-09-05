"""Default macOS wake service used by MacController."""

from __future__ import annotations

import asyncio
import logging

import Quartz
from pynput.keyboard import Key

logger = logging.getLogger("AirMac.controller")


class WakeServiceMixin:
    async def _start_reachability_assertion(self, owner_pid: int) -> None:
        if self.reachability_assertion_active:
            return
        try:
            process = await asyncio.create_subprocess_exec(
                "caffeinate",
                "-s",
                "-w",
                str(owner_pid),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except OSError:
            logger.exception("Unable to start AC reachability assertion")
            return
        self.reachability_process = process
        self.reachability_task = asyncio.create_task(
            self._wait_for_reachability_process(process),
            name="airmac-ac-reachability-assertion",
        )
        logger.info("AC-only network reachability assertion started")

    async def _stop_reachability_assertion(self) -> None:
        task = self.reachability_task
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self.reachability_task = None
        self.reachability_process = None

    async def _wait_for_reachability_process(
        self, process: asyncio.subprocess.Process
    ) -> None:
        try:
            await self._wait_for_background_process(process)
        finally:
            if self.reachability_process is process:
                self.reachability_process = None
                self.reachability_task = None
                logger.info("AC-only network reachability assertion ended")

    async def _wake_display(self) -> None:
        await self._stop_wake_assertion()
        process = await asyncio.create_subprocess_exec(
            "caffeinate",
            "-d",
            "-u",
            "-t",
            "30",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        self.wake_process = process
        self.wake_task = asyncio.create_task(
            self._wait_for_wake_process(process), name="airmac-wake-assertion"
        )
        logger.info("Wake assertion started duration_seconds=30")
        await asyncio.sleep(0.35)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            self.control_executor, self._press_and_release, Key.shift
        )

    async def wake_if_display_asleep(self) -> bool:
        loop = asyncio.get_running_loop()
        is_asleep = await loop.run_in_executor(
            self.control_executor, self._main_display_is_asleep
        )
        if not is_asleep:
            return False
        logger.info("Sleeping display detected after authentication; waking")
        await self._wake_display()
        return True

    def _main_display_is_asleep(self) -> bool:
        return bool(Quartz.CGDisplayIsAsleep(Quartz.CGMainDisplayID()))

    async def _stop_wake_assertion(self) -> None:
        task = self.wake_task
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self.wake_task = None
        self.wake_process = None

    async def _wait_for_wake_process(
        self, process: asyncio.subprocess.Process
    ) -> None:
        try:
            await self._wait_for_background_process(process)
        finally:
            if self.wake_process is process:
                self.wake_process = None
                self.wake_task = None
                logger.info("Wake assertion ended")
