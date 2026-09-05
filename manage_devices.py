#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from auth import DeviceStore, DeviceStoreError
from config import load_local_settings


SERVICE_NAME = "com.airmac.remote"
SETTINGS = load_local_settings()
HEALTH_URL = f"{SETTINGS.loopback_base_url}/api/health"
DIAGNOSTICS_URL = f"{SETTINGS.loopback_base_url}/api/diagnostics"
LOG_PATH = Path.home() / "Library" / "Logs" / "AirMac" / "remote.log"


def parse_launchctl_output(output: str) -> tuple[str, str]:
    state_match = re.search(r"^\s*state = (\S+)", output, re.MULTILINE)
    pid_match = re.search(r"^\s*pid = (\d+)", output, re.MULTILINE)
    return (
        state_match.group(1) if state_match else "unknown",
        pid_match.group(1) if pid_match else "-",
    )


def print_service_status() -> bool:
    label = f"gui/{os.getuid()}/{SERVICE_NAME}"
    try:
        result = subprocess.run(
            ["launchctl", "print", label],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"服务：无法查询（{exc}）")
        return False
    if result.returncode != 0:
        print("服务：未运行")
        return False
    state, pid = parse_launchctl_output(result.stdout)
    print(f"服务：{state}  pid={pid}")

    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=2) as response:
            health = json.load(response)
    except (OSError, ValueError, urllib.error.URLError) as exc:
        print(f"健康检查：失败（{exc}）")
        return False
    print(
        f"健康检查：{health.get('status', 'unknown')}  "
        f"controller={health.get('controller', 'unknown')}"
    )
    return state == "running" and health.get("status") == "ok"


def print_diagnostics(store: DeviceStore) -> bool:
    healthy = print_service_status()
    try:
        with urllib.request.urlopen(DIAGNOSTICS_URL, timeout=2) as response:
            runtime = json.load(response)
    except (OSError, ValueError, urllib.error.URLError) as exc:
        print(f"运行时诊断：失败（{exc}）")
        healthy = False
    else:
        print(
            f"运行时：AirMac {runtime.get('version', 'unknown')}  "
            f"protocol={runtime.get('protocol_version', 'unknown')}  "
            f"uptime={runtime.get('uptime_seconds', 'unknown')}s"
        )
        print(
            f"事件循环最大延迟：{runtime.get('event_loop_max_lag_ms', 'unknown')}ms  "
            f"最近断开：{runtime.get('last_disconnect_category') or '-'}"
        )
        print(
            "插电网络可达性断言："
            + ("active" if runtime.get("ac_reachability_assertion") else "inactive")
        )
        queue_metrics = runtime.get("queue_metrics", {})
        if isinstance(queue_metrics, dict):
            print(
                "队列："
                + " ".join(
                    f"{key}={value}" for key, value in sorted(queue_metrics.items())
                )
            )
    print(f"设备库：{store.path}")
    if store.path.exists():
        mode = stat.S_IMODE(store.path.stat().st_mode)
        try:
            device_count = len(store.list_devices())
        except DeviceStoreError as exc:
            print(f"设备库：读取失败（{exc}）")
            healthy = False
        else:
            print(f"设备库权限：{mode:o}  devices={device_count}")
            healthy = healthy and mode == 0o600
    else:
        print("设备库：尚未创建")
    if LOG_PATH.exists():
        print(f"日志：{LOG_PATH}  size={LOG_PATH.stat().st_size} bytes")
    else:
        print(f"日志：不存在（{LOG_PATH}）")
    return healthy


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="管理 AirMac 已配对设备")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="列出已配对设备")
    subparsers.add_parser("status", help="检查后台服务和 WebSocket 控制器状态")
    subparsers.add_parser("diagnose", help="输出不含凭据的本机诊断信息")

    revoke = subparsers.add_parser("revoke", help="撤销一台设备")
    revoke.add_argument("device_id")

    clear = subparsers.add_parser("clear", help="撤销全部设备")
    clear.add_argument("--yes", action="store_true", help="确认清空")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    store = DeviceStore()
    if args.command == "status":
        return 0 if print_service_status() else 1
    if args.command == "diagnose":
        return 0 if print_diagnostics(store) else 1
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
