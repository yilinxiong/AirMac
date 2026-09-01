#!/usr/bin/env python3
from __future__ import annotations

import argparse

from auth import DeviceStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="管理 AirMac 已配对设备")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="列出已配对设备")

    revoke = subparsers.add_parser("revoke", help="撤销一台设备")
    revoke.add_argument("device_id")

    clear = subparsers.add_parser("clear", help="撤销全部设备")
    clear.add_argument("--yes", action="store_true", help="确认清空")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    store = DeviceStore()
    if args.command == "list":
        devices = store.list_devices()
        if not devices:
            print("没有已配对设备。")
            return 0
        for device in devices:
            print(
                f"{device['device_id']}  {device['name']}  "
                f"paired={device['created_at']}"
            )
        return 0

    if args.command == "revoke":
        if store.revoke(args.device_id):
            print(f"已撤销设备：{args.device_id}")
            return 0
        print(f"未找到设备：{args.device_id}")
        return 1

    if not args.yes:
        print("拒绝清空：请追加 --yes 明确确认。")
        return 2
    count = store.clear()
    print(f"已撤销 {count} 台设备。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
