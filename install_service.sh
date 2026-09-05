#!/bin/bash

set -euo pipefail

SERVICE_NAME="com.airmac.remote"
MENUBAR_SERVICE_NAME="com.airmac.remote.menubar"
LEGACY_SERVICE_NAME="com.yourname.iphonemacremote"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLIST_DIR="${HOME}/Library/LaunchAgents"
PLIST_PATH="${PLIST_DIR}/${SERVICE_NAME}.plist"
MENUBAR_PLIST_PATH="${PLIST_DIR}/${MENUBAR_SERVICE_NAME}.plist"
LOG_DIR="${HOME}/Library/Logs/AirMac"
LOG_FILE="${LOG_DIR}/remote.log"
LAUNCHER_LOG="${LOG_DIR}/launcher.log"
MENUBAR_LOG="${LOG_DIR}/menubar.log"
DATA_DIR="${HOME}/Library/Application Support/AirMac"
RUNTIME_LOG_CONFIG="${DATA_DIR}/logging_config.json"
DEVICE_STORE="${DATA_DIR}/authorized_devices.json"
MENUBAR_SOURCE="${PROJECT_DIR}/menubar.m"
MENUBAR_BINARY="${PROJECT_DIR}/airmac-menubar"
AUDIO_SWITCHER_SOURCE="${PROJECT_DIR}/audio_switcher.m"
AUDIO_SWITCHER_BINARY="${PROJECT_DIR}/audio-switcher"
AIRMAC_PORT_VALUE="${AIRMAC_PORT:-8000}"
AIRMAC_LOG_LEVEL_VALUE="${AIRMAC_LOG_LEVEL:-INFO}"
AIRMAC_KEEP_REACHABLE_ON_AC_VALUE="${AIRMAC_KEEP_REACHABLE_ON_AC:-1}"

if ! [[ "${AIRMAC_PORT_VALUE}" =~ ^[0-9]+$ ]] \
    || [ "${AIRMAC_PORT_VALUE}" -lt 1 ] \
    || [ "${AIRMAC_PORT_VALUE}" -gt 65535 ]; then
    echo "❌ AIRMAC_PORT 必须是 1–65535 之间的整数。"
    exit 1
fi

case "${AIRMAC_LOG_LEVEL_VALUE}" in
    DEBUG|INFO|WARNING|ERROR|CRITICAL) ;;
    *)
        echo "❌ AIRMAC_LOG_LEVEL 必须是 DEBUG、INFO、WARNING、ERROR 或 CRITICAL。"
        exit 1
        ;;
esac

if [ "${AIRMAC_KEEP_REACHABLE_ON_AC_VALUE}" != "0" ] \
    && [ "${AIRMAC_KEEP_REACHABLE_ON_AC_VALUE}" != "1" ]; then
    echo "❌ AIRMAC_KEEP_REACHABLE_ON_AC 必须是 0 或 1。"
    exit 1
fi

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

if [ ! -x "${MENUBAR_BINARY}" ] || [ "${MENUBAR_SOURCE}" -nt "${MENUBAR_BINARY}" ]; then
    if command -v clang >/dev/null 2>&1; then
        echo "正在构建 AirMac 菜单栏应用..."
        if clang -fobjc-arc -framework Cocoa "${MENUBAR_SOURCE}" -o "${MENUBAR_BINARY}.new"; then
            mv "${MENUBAR_BINARY}.new" "${MENUBAR_BINARY}"
        else
            rm -f "${MENUBAR_BINARY}.new"
            echo "⚠️ 菜单栏应用构建失败，后台控制服务仍会正常安装。"
        fi
    else
        echo "⚠️ 未找到 clang，无法构建菜单栏应用。"
    fi
fi

if [ ! -x "${AUDIO_SWITCHER_BINARY}" ] || [ "${AUDIO_SWITCHER_SOURCE}" -nt "${AUDIO_SWITCHER_BINARY}" ]; then
    if command -v clang >/dev/null 2>&1; then
        echo "正在构建 AirMac 音频输出切换器..."
        if clang -fobjc-arc -framework Foundation -framework CoreAudio \
            "${AUDIO_SWITCHER_SOURCE}" -o "${AUDIO_SWITCHER_BINARY}.new"; then
            mv "${AUDIO_SWITCHER_BINARY}.new" "${AUDIO_SWITCHER_BINARY}"
        else
            rm -f "${AUDIO_SWITCHER_BINARY}.new"
            echo "⚠️ 音频输出切换器构建失败，其他远程控制功能仍可使用。"
        fi
    else
        echo "⚠️ 未找到 clang，无法构建音频输出切换器。"
    fi
fi

if [ -x "${MENUBAR_BINARY}" ]; then
    MENUBAR_AVAILABLE=true
else
    MENUBAR_AVAILABLE=false
fi

mkdir -p "${PLIST_DIR}" "${LOG_DIR}" "${DATA_DIR}"
chmod 700 "${LOG_DIR}" "${DATA_DIR}"
touch "${LOG_FILE}" "${LAUNCHER_LOG}" "${MENUBAR_LOG}"
chmod 600 "${LOG_FILE}" "${LAUNCHER_LOG}" "${MENUBAR_LOG}"

"${PYTHON_PATH}" - "${PLIST_PATH}" "${SERVICE_NAME}" "${PROJECT_DIR}" "${PYTHON_PATH}" "${LOG_FILE}" "${LAUNCHER_LOG}" "${RUNTIME_LOG_CONFIG}" "${MENUBAR_PLIST_PATH}" "${MENUBAR_SERVICE_NAME}" "${MENUBAR_BINARY}" "${DEVICE_STORE}" "${MENUBAR_LOG}" "${MENUBAR_AVAILABLE}" "${AIRMAC_PORT_VALUE}" "${AIRMAC_LOG_LEVEL_VALUE}" "${AIRMAC_KEEP_REACHABLE_ON_AC_VALUE}" <<'PY'
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
    menubar_plist_path,
    menubar_label,
    menubar_binary,
    device_store,
    menubar_log,
    menubar_available,
    port,
    log_level,
    keep_reachable_on_ac,
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
        "uvicorn": {"handlers": ["default"], "level": log_level, "propagate": False},
        "uvicorn.error": {"level": log_level},
        "uvicorn.access": {"handlers": ["default"], "level": log_level, "propagate": False},
        "AirMac": {"handlers": ["default"], "level": log_level, "propagate": False},
    },
    "root": {"handlers": ["default"], "level": log_level},
}
with open(runtime_log_config, "w", encoding="utf-8") as handle:
    json.dump(log_configuration, handle, ensure_ascii=False, indent=2)
os.chmod(runtime_log_config, 0o600)
runtime_settings_path = os.path.join(os.path.dirname(runtime_log_config), "runtime.json")
temporary_settings_path = runtime_settings_path + ".new"
with open(temporary_settings_path, "w", encoding="utf-8") as handle:
    json.dump(
        {
            "port": int(port),
            "log_level": log_level,
            "keep_reachable_on_ac": keep_reachable_on_ac == "1",
        },
        handle,
        indent=2,
    )
os.chmod(temporary_settings_path, 0o600)
os.replace(temporary_settings_path, runtime_settings_path)

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
        port,
        "--ws-max-size",
        "65536",
        "--log-config",
        runtime_log_config,
        "--no-access-log",
    ],
    "EnvironmentVariables": {
        "PYTHONUNBUFFERED": "1",
        "AIRMAC_PORT": port,
        "AIRMAC_LOG_LEVEL": log_level,
        "AIRMAC_KEEP_REACHABLE_ON_AC": keep_reachable_on_ac,
    },
    "RunAtLoad": True,
    "KeepAlive": True,
    "StandardOutPath": launcher_log,
    "StandardErrorPath": launcher_log,
}
with open(plist_path, "wb") as handle:
    plistlib.dump(configuration, handle)

if menubar_available == "true":
    menubar_configuration = {
        "Label": menubar_label,
        "ProgramArguments": [
            menubar_binary,
            project_dir,
            python_path,
            device_store,
            log_file,
            port,
        ],
        "EnvironmentVariables": {"AIRMAC_PORT": port},
        "RunAtLoad": True,
        "ProcessType": "Interactive",
        "StandardOutPath": menubar_log,
        "StandardErrorPath": menubar_log,
    }
    with open(menubar_plist_path, "wb") as handle:
        plistlib.dump(menubar_configuration, handle)
else:
    try:
        os.unlink(menubar_plist_path)
    except FileNotFoundError:
        pass
PY

launchctl bootout "gui/${UID}/${SERVICE_NAME}" 2>/dev/null || true
launchctl bootout "gui/${UID}/${MENUBAR_SERVICE_NAME}" 2>/dev/null || true
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

if [ "${MENUBAR_AVAILABLE}" = true ]; then
    MENUBAR_LOADED=false
    for ATTEMPT in 1 2 3; do
        if launchctl bootstrap "gui/${UID}" "${MENUBAR_PLIST_PATH}"; then
            MENUBAR_LOADED=true
            break
        fi
        if [ "${ATTEMPT}" -lt 3 ]; then
            echo "菜单栏进程尚未完成注销，1 秒后重试 (${ATTEMPT}/3)..."
            sleep 1
        fi
    done
    if [ "${MENUBAR_LOADED}" = true ]; then
        launchctl enable "gui/${UID}/${MENUBAR_SERVICE_NAME}"
    else
        echo "⚠️ 菜单栏应用未能启动，后台控制服务仍在运行。"
    fi
fi

HEALTHY=false
for ATTEMPT in 1 2 3 4 5 6 7 8 9 10; do
    if curl -fsS "http://127.0.0.1:${AIRMAC_PORT_VALUE}/api/health" >/dev/null 2>&1; then
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
if [ "${MENUBAR_AVAILABLE}" = true ]; then
    echo "菜单栏：${MENUBAR_SERVICE_NAME}"
fi
echo "日志：${LOG_FILE}"
echo "端口：${AIRMAC_PORT_VALUE}"
if [ "${AIRMAC_KEEP_REACHABLE_ON_AC_VALUE}" = "1" ]; then
    echo "插电网络可达：开启"
else
    echo "插电网络可达：关闭"
fi
echo "设备管理：${PYTHON_PATH} ${PROJECT_DIR}/manage_devices.py list"
echo "====================================================="
