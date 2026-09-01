#!/usr/bin/env python3
from __future__ import annotations

import sys

from AppKit import (
    NSAlert,
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSRunningApplication,
    NSApplicationActivateIgnoringOtherApps,
)


def main() -> int:
    if len(sys.argv) != 3:
        return 2

    device_name, pairing_code = sys.argv[1:]
    application = NSApplication.sharedApplication()
    application.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

    alert = NSAlert.alloc().init()
    alert.setMessageText_("AirMac 安全配对")
    alert.setInformativeText_(
        f"设备 [{device_name}] 正在配对 AirMac\n\n"
        f"请在手机上输入验证码：{pairing_code}"
    )
    alert.addButtonWithTitle_("关闭")

    NSRunningApplication.currentApplication().activateWithOptions_(
        NSApplicationActivateIgnoringOtherApps
    )
    alert.runModal()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
