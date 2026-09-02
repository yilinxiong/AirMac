#!/bin/bash

set -euo pipefail

SERVICE_NAME="com.airmac.remote"
LEGACY_SERVICE_NAME="com.yourname.iphonemacremote"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLIST_DIR="${HOME}/Library/LaunchAgents"
PLIST_PATH="${PLIST_DIR}/${SERVICE_NAME}.plist"
LOG_DIR="${HOME}/Library/Logs/AirMac"
LOG_FILE="${LOG_DIR}/remote.log"
LAUNCHER_LOG="${LOG_DIR}/launcher.log"
DATA_DIR="${HOME}/Library/Application Support/AirMac"
RUNTIME_LOG_CONFIG="${DATA_DIR}/logging_config.json"

if [ -x "${PROJECT_DIR}/venv/bin/python" ]; then
    PYTHON_PATH="${PROJECT_DIR}/venv/bin/python"
else
    PYTHON_PATH="$(command -v python3 || true)"
fi

if [ -z "${PYTHON_PATH}" ]; then
    echo "❌ 未找到 Python 3。请先安装 Python 3.12。"
    exit 1
fi

if ! "${PYTHON_PATH}" -c "import fastapi, uvicorn, Quartz, pynput" 2>/dev/null; then
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

mkdir -p "${PLIST_DIR}" "${LOG_DIR}" "${DATA_DIR}"
chmod 700 "${LOG_DIR}" "${DATA_DIR}"
touch "${LOG_FILE}" "${LAUNCHER_LOG}"
chmod 600 "${LOG_FILE}" "${LAUNCHER_LOG}"

"${PYTHON_PATH}" - "${PLIST_PATH}" "${SERVICE_NAME}" "${PROJECT_DIR}" "${PYTHON_PATH}" "${LOG_FILE}" "${LAUNCHER_LOG}" "${RUNTIME_LOG_CONFIG}" <<'PY'
import json
import os
import plistlib
import sys

(
    plist_path,
    label,
    project_dir,
    python_path,
    log_file,
    launcher_log,
    runtime_log_config,
) = sys.argv[1:]
log_configuration = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "timestamped": {
            "format": "%(asctime)s.%(msecs)03d %(levelname)s [%(name)s] %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        }
    },
    "handlers": {
        "default": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "timestamped",
            "filename": log_file,
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 4,
            "encoding": "utf-8",
        }
    },
    "loggers": {
        "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"level": "INFO"},
        "uvicorn.access": {"handlers": ["default"], "level": "INFO", "propagate": False},
        "AirMac": {"handlers": ["default"], "level": "INFO", "propagate": False},
    },
    "root": {"handlers": ["default"], "level": "INFO"},
}
with open(runtime_log_config, "w", encoding="utf-8") as handle:
    json.dump(log_configuration, handle, ensure_ascii=False, indent=2)
os.chmod(runtime_log_config, 0o600)

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
        runtime_log_config,
        "--no-access-log",
    ],
    "EnvironmentVariables": {"PYTHONUNBUFFERED": "1"},
    "RunAtLoad": True,
    "KeepAlive": True,
    "StandardOutPath": launcher_log,
    "StandardErrorPath": launcher_log,
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

HEALTHY=false
for ATTEMPT in 1 2 3 4 5 6 7 8 9 10; do
    if curl -fsS "http://127.0.0.1:8000/api/health" >/dev/null 2>&1; then
        HEALTHY=true
        break
    fi
    sleep 0.5
done
if [ "${HEALTHY}" != true ]; then
    echo "❌ AirMac 已注册，但健康检查失败。请查看：${LAUNCHER_LOG}"
    exit 1
fi

echo "====================================================="
echo "✅ AirMac 已安装并启动"
echo "服务：${SERVICE_NAME}"
echo "日志：${LOG_FILE}"
echo "设备管理：${PYTHON_PATH} ${PROJECT_DIR}/manage_devices.py list"
echo "====================================================="
