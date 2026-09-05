"""Default macOS system service used by MacController."""

from __future__ import annotations

import logging
import math

import ApplicationServices as AX
import AppKit
import Quartz
from pynput.keyboard import Key

from protocol import ActionMessage

logger = logging.getLogger("AirMac.controller")
CONTROL_CENTER_KEY_CODE = 8
CONTROL_CENTER_FLAGS = Quartz.kCGEventFlagMaskSecondaryFn
AX_FULLSCREEN_ATTRIBUTE = "AXFullScreen"
WINDOW_SHORTCUT_FLAGS = Quartz.kCGEventFlagMaskSecondaryFn | Quartz.kCGEventFlagMaskControl
WINDOW_SHORTCUT_KEY_CODES = {
    "window_left": 123, "window_right": 124, "window_fill": 3, "window_center": 8,
}


class SystemServiceMixin:
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

    def _execute_quick_action(self, command: str) -> None:
        if command in WINDOW_SHORTCUT_KEY_CODES:
            self._post_key_code(
                WINDOW_SHORTCUT_KEY_CODES[command], WINDOW_SHORTCUT_FLAGS
            )
        elif command == "volume_down":
            self._press_and_release(Key.media_volume_down)
        elif command == "volume_mute":
            self._press_and_release(Key.media_volume_mute)
        elif command == "volume_up":
            self._press_and_release(Key.media_volume_up)
        elif command == "brightness_down":
            self._post_key_code(144, 0)
        elif command == "brightness_up":
            self._post_key_code(145, 0)
        elif command == "lock_screen":
            self._post_key_code(
                12,
                Quartz.kCGEventFlagMaskControl | Quartz.kCGEventFlagMaskCommand,
            )
        elif command == "open_control_center":
            self._post_key_code(CONTROL_CENTER_KEY_CODE, CONTROL_CENTER_FLAGS)

    def _close_fullscreen_window(self) -> str:
        accessibility_fullscreen = False
        accessibility_bounds_fullscreen = False
        try:
            system = AX.AXUIElementCreateSystemWide()
            error, application = AX.AXUIElementCopyAttributeValue(
                system, AX.kAXFocusedApplicationAttribute, None
            )
            if error == AX.kAXErrorSuccess and application is not None:
                error, window = AX.AXUIElementCopyAttributeValue(
                    application, AX.kAXFocusedWindowAttribute, None
                )
                if error == AX.kAXErrorSuccess and window is not None:
                    error, is_fullscreen = AX.AXUIElementCopyAttributeValue(
                        window, AX_FULLSCREEN_ATTRIBUTE, None
                    )
                    accessibility_fullscreen = (
                        error == AX.kAXErrorSuccess and bool(is_fullscreen)
                    )
                    position = self._read_ax_value(
                        window,
                        AX.kAXPositionAttribute,
                        AX.kAXValueCGPointType,
                    )
                    size = self._read_ax_value(
                        window,
                        AX.kAXSizeAttribute,
                        AX.kAXValueCGSizeType,
                    )
                    if position is not None and size is not None:
                        accessibility_bounds_fullscreen = (
                            self._rectangle_fills_active_display(
                                position.x,
                                position.y,
                                size.width,
                                size.height,
                            )
                        )
        except Exception:
            logger.debug("Unable to read accessibility fullscreen state", exc_info=True)

        bounds_fullscreen = self._frontmost_window_fills_display()
        if not (
            accessibility_fullscreen
            or accessibility_bounds_fullscreen
            or bounds_fullscreen
        ):
            logger.info(
                "Ignored close-fullscreen request: focused window is not fullscreen"
            )
            return "ignored"

        self._post_key_code(12, Quartz.kCGEventFlagMaskCommand)
        logger.info(
            "Requested graceful quit for focused fullscreen app accessibility=%s "
            "accessibility_bounds=%s window_server_bounds=%s",
            accessibility_fullscreen,
            accessibility_bounds_fullscreen,
            bounds_fullscreen,
        )
        return "closed"

    def _read_ax_value(
        self, element: object, attribute: str, value_type: int
    ) -> object | None:
        error, value = AX.AXUIElementCopyAttributeValue(element, attribute, None)
        if error != AX.kAXErrorSuccess or value is None:
            return None
        try:
            success, extracted = AX.AXValueGetValue(value, value_type, None)
            return extracted if success else None
        except (TypeError, ValueError):
            return None

    def _frontmost_window_fills_display(self) -> bool:
        application = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
        if application is None:
            return False
        process_id = int(application.processIdentifier())
        options = (
            Quartz.kCGWindowListOptionOnScreenOnly
            | Quartz.kCGWindowListExcludeDesktopElements
        )
        window_infos = Quartz.CGWindowListCopyWindowInfo(
            options, Quartz.kCGNullWindowID
        ) or []
        for info in window_infos:
            if int(info.get(Quartz.kCGWindowOwnerPID, -1)) != process_id:
                continue
            if int(info.get(Quartz.kCGWindowLayer, -1)) != 0:
                continue
            bounds = info.get(Quartz.kCGWindowBounds)
            if not hasattr(bounds, "get"):
                continue
            if self._rectangle_fills_active_display(
                float(bounds.get("X", math.inf)),
                float(bounds.get("Y", math.inf)),
                float(bounds.get("Width", -1)),
                float(bounds.get("Height", -1)),
            ):
                return True
        return False

    def _rectangle_fills_active_display(
        self, x: float, y: float, width: float, height: float
    ) -> bool:
        success, display_ids, count = Quartz.CGGetActiveDisplayList(16, None, None)
        if success != 0 or count == 0:
            return False
        for index in range(count):
            display = Quartz.CGDisplayBounds(display_ids[index])
            if (
                abs(x - display.origin.x) <= 3
                and abs(y - display.origin.y) <= 3
                and abs(width - display.size.width) <= 3
                and abs(height - display.size.height) <= 3
            ):
                return True
        return False

    def _post_key_code(self, key_code: int, flags: int) -> None:
        for is_down in (True, False):
            event = Quartz.CGEventCreateKeyboardEvent(None, key_code, is_down)
            Quartz.CGEventSetFlags(event, flags)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)

    def _press_and_release(self, key: object) -> None:
        self.keyboard.press(key)
        self.keyboard.release(key)

    def _release_modifiers(self) -> None:
        for key in (Key.cmd, Key.ctrl, Key.shift, Key.alt):
            try:
                self.keyboard.release(key)
            except Exception:
                logger.debug("Modifier was not held: %s", key)
