"""Default macOS pointer service used by MacController."""

from __future__ import annotations

import math
import time

import Quartz

from protocol import ActionMessage, MoveAction


class PointerServiceMixin:
    def _execute_pointer(self, message: ActionMessage) -> None:
        action = message.action
        if action == "mouse_down":
            current_pos = self._current_position()
            self._post_mouse(
                Quartz.kCGEventLeftMouseDown,
                current_pos,
                Quartz.kCGMouseButtonLeft,
            )
            self.mouse_is_down = True
        elif action == "mouse_up":
            current_pos = self._current_position()
            self._post_mouse(
                Quartz.kCGEventLeftMouseUp, current_pos, Quartz.kCGMouseButtonLeft
            )
            self.mouse_is_down = False
        elif action in {"move", "mouse_drag"}:
            assert isinstance(message, MoveAction)
            now = time.monotonic()
            if now - self.last_move_time > 0.2:
                self.virtual_x, self.virtual_y = self._current_position()
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
            current_pos = self._current_position()
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
            current_pos = self._current_position()
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
