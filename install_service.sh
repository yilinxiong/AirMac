#!/bin/bash

set -euo pipefail

SERVICE_NAME="com.airmac.remote"
LEGACY_SERVICE_NAME="com.yourname.iphonemacremote"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLIST_DIR="${HOME}/Library/LaunchAgents"
PLIST_PATH="${PLIST_DIR}/${SERVICE_NAME}.plist"
LOG_DIR="${HOME}/Library/Logs/AirMac"
LOG_FILE="${LOG_DIR}/remote.log"

if [ -x "${PROJECT_DIR}/venv/bin/python" ]; then
    PYTHON_PATH="${PROJECT_DIR}/venv/bin/python"
else
    PYTHON_PATH="$(command -v python3 || true)"
fi

if [ -z "${PYTHON_PATH}" ]; then
    echo "❌ 未找到 Python 3。请先安装 Python 3.12。"
    exit 1
fi

if ! "${PYTHON_PATH}" -c "import fastapi, uvicorn, Quartz, pynput, pyperclip" 2>/dev/null; then
    echo "❌ Python 依赖不完整。请先运行："
    echo "${PYTHON_PATH} -m pip install -r \"${PROJECT_DIR}/requirements.txt\""
    exit 1
fi

if [ ! -x "${PROJECT_DIR}/hud" ] || [ "${PROJECT_DIR}/hud.swift" -nt "${PROJECT_DIR}/hud" ]; then
    if command -v swiftc >/dev/null 2>&1; then
        echo "正在构建 AirMac HUD..."
        if swiftc "${PROJECT_DIR}/hud.swift" -o "${PROJECT_DIR}/hud.new"; then
            mv "${PROJECT_DIR}/hud.new" "${PROJECT_DIR}/hud"
        else
            rm -f "${PROJECT_DIR}/hud.new"
            echo "⚠️ Swift HUD 构建失败，将使用 macOS 系统通知作为复制反馈。"
        fi
    else
        echo "⚠️ 未找到 swiftc，将使用 macOS 系统通知作为复制反馈。"
    fi
fi

mkdir -p "${PLIST_DIR}" "${LOG_DIR}"
touch "${LOG_FILE}"

"${PYTHON_PATH}" - "${PLIST_PATH}" "${SERVICE_NAME}" "${PROJECT_DIR}" "${PYTHON_PATH}" "${LOG_FILE}" <<'PY'
import plistlib
import sys

plist_path, label, project_dir, python_path, log_file = sys.argv[1:]
configuration = {
    "Label": label,
    "WorkingDirectory": project_dir,
    "ProgramArguments": [
        python_path,
        "-m",
        "uvicorn",
        "main:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
        "--ws-max-size",
        "65536",
        "--log-config",
        f"{project_dir}/logging_config.json",
        "--no-access-log",
    ],
    "EnvironmentVariables": {"PYTHONUNBUFFERED": "1"},
    "RunAtLoad": True,
    "KeepAlive": True,
    "StandardOutPath": log_file,
    "StandardErrorPath": log_file,
}
with open(plist_path, "wb") as handle:
    plistlib.dump(configuration, handle)
PY

launchctl bootout "gui/${UID}/${SERVICE_NAME}" 2>/dev/null || true
launchctl bootout "gui/${UID}/${LEGACY_SERVICE_NAME}" 2>/dev/null || true
rm -f "${PLIST_DIR}/${LEGACY_SERVICE_NAME}.plist"
SERVICE_LOADED=false
for ATTEMPT in 1 2 3; do
    if launchctl bootstrap "gui/${UID}" "${PLIST_PATH}"; then
        SERVICE_LOADED=true
        break
    fi
    if [ "${ATTEMPT}" -lt 3 ]; then
        echo "launchd 尚未完成注销，1 秒后重试 (${ATTEMPT}/3)..."
        sleep 1
    fi
done
if [ "${SERVICE_LOADED}" != true ]; then
    echo "❌ 无法注册 AirMac LaunchAgent。"
    exit 1
fi
launchctl enable "gui/${UID}/${SERVICE_NAME}"

echo "====================================================="
echo "✅ AirMac 已安装并启动"
echo "服务：${SERVICE_NAME}"
echo "日志：${LOG_FILE}"
echo "设备管理：${PYTHON_PATH} ${PROJECT_DIR}/manage_devices.py list"
echo "====================================================="
