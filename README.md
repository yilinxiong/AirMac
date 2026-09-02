# AirMac 📱💻

<p align="center">
  <img src="icon.png" width="150" alt="AirMac Icon">
</p>

[English](#english) | [中文说明](#中文说明)

AirMac turns an iPhone into a low-latency trackpad and keyboard for a Mac on the same trusted local network. It uses a FastAPI/WebSocket server and macOS Quartz input events.

> Security boundary: AirMac uses device pairing and bearer-token authentication, but the default zero-configuration setup is HTTP/WS, not encrypted HTTPS/WSS. Use it only on a trusted home or personal LAN. Do not expose port 8000 to the internet or use it on an untrusted/shared network.

## English

### Features

- One-finger cursor movement and tap-to-click
- Two-finger right-click and scrolling
- Three-finger Mission Control and desktop switching
- Four-finger upward swipe to open Launchpad or the macOS Apps interface
- Long-press dragging with disconnect-safe mouse release
- Keyboard input and long-text projection
- Confirmed long-text delivery with a dedicated clear button
- Automatic copy feedback with a native macOS HUD
- Media, fullscreen, display sleep, and wake controls
- Six-digit, short-lived pairing codes and revocable device tokens
- Native macOS menu-bar status and paired-device management
- Installable Home Screen web app with manifest and adaptive icons

### Install

```bash
cd iphone_mac_remote
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Grant Accessibility permission to the terminal/Python process in **System Settings → Privacy & Security → Accessibility**.

For a foreground run:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --ws-max-size 65536 --log-config logging_config.json
```

For login services that build and start both the native menu-bar manager and,
when the local Swift toolchain supports it, the copy HUD:

```bash
./install_service.sh
```

Open the URL printed by AirMac in iPhone Safari. On first use, name the phone, request a pairing code, and enter the six digits shown in the Mac dialog. The resulting device token is stored by Safari and is never placed in the WebSocket URL or access log.

Add the page to the iPhone Home Screen for the full-screen experience. AirMac now
includes a complete web app manifest, iPhone and maskable icons, and an in-app
installation hint. A cached offline explanation page is available when the browser
allows Service Workers. Browsers normally require HTTPS for Service Workers, so
plain LAN HTTP may skip that optional cache without affecting remote control.

The AirMac cursor icon in the macOS menu bar shows whether the background service
is reachable. Its menu can open or copy the phone URL, show and revoke paired
devices, reveal logs, and restart the service. Choosing **Quit Menu Bar Icon** hides
only the icon; the remote-control server continues running and the icon returns at
the next login or service installation.

Locking the iPhone or sending the page to the background intentionally pauses the
WebSocket. Returning to AirMac reconnects automatically. The server expires an
unresponsive foreground session after 16 seconds so a stale mobile connection
cannot hold the controller indefinitely.

The wake button holds a cancellable display-sleep assertion for 30 seconds. This
prevents the display from immediately sleeping again while leaving the normal
macOS password and lock-screen policy unchanged.

### Paired-device management

Run these commands locally on the Mac:

```bash
python manage_devices.py list
python manage_devices.py revoke DEVICE_ID
python manage_devices.py clear --yes
python manage_devices.py status
python manage_devices.py diagnose
```

Revoked active devices are disconnected within approximately one second. Device records are stored with user-only permissions at:

```text
~/Library/Application Support/AirMac/authorized_devices.json
```

Logs from the LaunchAgent are stored at:

```text
~/Library/Logs/AirMac/remote.log
```

Every log line includes local time with millisecond precision. Slow pointer events report queue and Quartz execution time separately, making network interruptions distinguishable from macOS input stalls. LaunchAgent logs rotate at 5 MiB with four backups, limiting the main log set to approximately 25 MiB.

The legacy `whitelist.json` format is intentionally not migrated because its client-generated IDs were not secure credentials. Existing devices must pair again after upgrading.

If the installed Swift compiler and macOS SDK do not match, installation continues and copy feedback falls back to a standard macOS notification.

### Development checks

```bash
pip install -r requirements-dev.txt
pytest
node --test tests/frontend_state.test.js
bash -n install_service.sh uninstall_service.sh tools/generate_pwa_icons.sh
clang -fobjc-arc -framework Cocoa menubar.m -o /tmp/airmac-menubar-check
```

## 中文说明

AirMac 可以把同一可信局域网中的 iPhone 变成 Mac 的低延迟触控板和键盘。后端使用 FastAPI、WebSocket 与 macOS Quartz 原生输入事件。

> 安全边界：AirMac 具有一次性验证码配对和设备令牌认证，但默认零配置模式使用未加密的 HTTP/WS。请只在可信家庭或个人局域网中使用，不要把 8000 端口暴露到互联网，也不要在不可信共享网络中使用。

### 功能

- 单指移动、轻点左键
- 双指右键和滚动
- 三指调度中心及桌面切换
- 四指上滑打开 Launchpad 或新版 macOS Apps 应用界面
- 长按拖拽，断线时自动释放鼠标
- 手机键盘输入和长文本投射
- 长文本执行确认以及独立的一键清空按钮
- 自动复制与 macOS 原生 HUD 提示
- 媒体、全屏、息屏与唤醒控制
- 6 位短时验证码配对、可撤销设备令牌
- 原生 macOS 菜单栏状态与配对设备管理
- 带 manifest 和自适应图标的主屏幕 Web App

### 安装与运行

```bash
cd iphone_mac_remote
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

进入 **系统设置 → 隐私与安全性 → 辅助功能**，为终端或实际运行 AirMac 的 Python 进程授权。

前台运行：

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --ws-max-size 65536 --log-config logging_config.json
```

安装为登录后自动运行的 LaunchAgent；安装脚本会构建并启动原生菜单栏管理器，
并在本机 Swift 工具链可用时自动编译复制 HUD：

```bash
./install_service.sh
```

在 iPhone Safari 中打开终端打印的网址。首次使用时输入设备名称，请求配对，然后把 Mac 弹窗显示的 6 位验证码填到手机。配对令牌保存在 Safari 中，不会出现在 WebSocket URL 或访问日志里。

推荐通过 Safari 分享菜单选择“添加到主屏幕”。AirMac 已包含完整 manifest、
iPhone/自适应图标和应用内安装提示。浏览器允许 Service Worker 时，还会缓存一个
断网说明页面；局域网 HTTP 通常不满足 Service Worker 的 HTTPS 要求，因此可能跳过
这项可选缓存，但不会影响远程控制功能。

Mac 菜单栏中的 AirMac 光标图标会显示后台服务是否可用。菜单内可以打开或复制
手机访问地址、查看和撤销配对设备、打开日志以及重启服务。“退出菜单栏图标”只会
隐藏图标，不会停止远程控制服务；下次登录或重新安装服务时图标会再次出现。

iPhone 锁屏或页面进入后台时会主动暂停 WebSocket；回到 AirMac 后自动恢复。
服务端会在前台连接连续 16 秒没有心跳时清理僵尸会话，避免旧连接长期占用控制器。

唤醒按钮会建立 30 秒、可取消的显示器保活断言，避免刚唤醒又立刻息屏；它不会绕过
macOS 的锁屏或密码策略。

如果 Swift 编译器与 macOS SDK 不匹配，安装仍会继续，复制反馈会自动退回 macOS 系统通知。

### 管理设备

以下命令只能在 Mac 本机执行：

```bash
python manage_devices.py list
python manage_devices.py revoke 设备ID
python manage_devices.py clear --yes
python manage_devices.py status
python manage_devices.py diagnose
```

撤销后，正在连接的设备会在约一秒内断开。旧版 `whitelist.json` 不会迁移或自动删除；升级后需要重新配对一次。

后台日志位于 `~/Library/Logs/AirMac/remote.log`。每行包含精确到毫秒的本地时间；若指针处理变慢，日志会分别记录排队时间和 Quartz 执行时间，方便区分网络中断与 Mac 输入层阻塞。日志每 5 MiB 轮转，保留 4 份备份，主日志集合约占 25 MiB。

卸载后台服务不会删除设备记录或日志：

```bash
./uninstall_service.sh
```
