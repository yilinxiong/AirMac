from __future__ import annotations

import sys
import types


if sys.platform != "darwin":
    quartz = types.ModuleType("Quartz")

    def quartz_attribute(name: str):
        if name.startswith("kCG"):
            return 0
        return lambda *_args, **_kwargs: None

    quartz.__getattr__ = quartz_attribute  # type: ignore[attr-defined]
    sys.modules["Quartz"] = quartz

    class DummyKeyboardController:
        def press(self, _key: object) -> None:
            pass

        def release(self, _key: object) -> None:
            pass

        def type(self, _text: str) -> None:
            pass

    dummy_key = types.SimpleNamespace(
        alt="alt",
        backspace="backspace",
        cmd="cmd",
        ctrl="ctrl",
        enter="enter",
        media_play_pause="media_play_pause",
        shift="shift",
        tab="tab",
    )
    pynput = types.ModuleType("pynput")
    pynput.__path__ = []  # type: ignore[attr-defined]
    keyboard = types.ModuleType("pynput.keyboard")
    keyboard.Controller = DummyKeyboardController  # type: ignore[attr-defined]
    keyboard.Key = dummy_key  # type: ignore[attr-defined]
    sys.modules["pynput"] = pynput
    sys.modules["pynput.keyboard"] = keyboard
