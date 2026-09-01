#!/bin/bash

set -euo pipefail

SERVICE_NAME="com.airmac.remote"
LEGACY_SERVICE_NAME="com.yourname.iphonemacremote"
PLIST_PATH="${HOME}/Library/LaunchAgents/${SERVICE_NAME}.plist"
LEGACY_PLIST_PATH="${HOME}/Library/LaunchAgents/${LEGACY_SERVICE_NAME}.plist"

echo "正在停止 AirMac..."
launchctl bootout "gui/${UID}/${SERVICE_NAME}" 2>/dev/null || true
launchctl bootout "gui/${UID}/${LEGACY_SERVICE_NAME}" 2>/dev/null || true

if [ -f "${PLIST_PATH}" ]; then
    rm "${PLIST_PATH}"
    echo "✅ 已卸载 AirMac LaunchAgent。"
else
    echo "AirMac LaunchAgent 已不存在。"
fi

if [ -f "${LEGACY_PLIST_PATH}" ]; then
    rm "${LEGACY_PLIST_PATH}"
fi

echo "配对设备和日志仍保留在 Library 中，如需删除请手动处理。"
