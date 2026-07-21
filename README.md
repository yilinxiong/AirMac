# AirMac 📱💻

<p align="center">
  <img src="icon.png" width="150" alt="AirMac Icon">
</p>

[English](#english) | [中文说明](#chinese)

---

<a name="english"></a>
## 🚀 English

Turn your iPhone into a premium, low-latency Magic Trackpad and Keyboard for your Mac. Completely wireless, highly secure, and extremely responsive.

### ✨ Features
- **Immersive PWA Experience**: Add it to your iPhone's home screen for a full-screen, app-like experience with a custom signature icon.
- **Precision Trackpad**: Built on macOS native Quartz engine for pixel-perfect tracking and physical screen edge boundaries.
- **Smart Gestures**:
  - 1 Finger Move: Move Cursor
  - 1 Finger Tap: Left Click
  - 2 Fingers Tap: Right Click
  - 2 Fingers Scroll: Scroll up/down
  - 3 Fingers Swipe Left/Right: Switch Desktops
  - 3 Fingers Swipe Up: Mission Control
  - **Long Press (500ms)**: Drag windows or select text (with dual haptic feedback).
- **Smart Clipboard**: Automatically executes `Cmd + C` when you double-click or drag-select text. Features a blazing-fast clipboard sniffing mechanism: your phone vibrates *only* when text is successfully copied, and your Mac displays a sleek, native-like HUD confirmation.
- **Keyboard & Text Projection**: Use your phone's native keyboard to type, or project long paragraphs of text directly to your Mac in a single tap.
- **Media & Power Controls**: Play/Pause media, switch Full-screen, put Mac display to Sleep, or Wake it up remotely.
- **Enterprise-Grade Security**: 
  - **Local Network Only**: Strictly blocks external IP access.
  - **Device Authorization**: New devices must be physically approved via a pop-up dialog on your Mac screen before gaining control.

### 🛠 Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/airmac.git
   cd airmac
   ```
2. **Set up Python Environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
3. **Grant Accessibility Permissions:**
   - Go to `System Settings` > `Privacy & Security` > `Accessibility`
   - Add and enable your `Terminal` or `iTerm` (or `bash`/`python` if running as a background service).
4. **Run the Server:**
   - **Debug Mode:** `uvicorn main:app --host 0.0.0.0 --port 8000`
   - **Background Service (Recommended):** Run `./install_service.sh` to install it as a macOS LaunchAgent (auto-starts on boot).

### 📱 How to Use
1. Ensure your iPhone and Mac are on the same Wi-Fi network.
2. Open Safari on your iPhone and navigate to the IP address printed in the terminal (e.g., `http://192.168.x.x:8000`).
3. **Highly Recommended**: Tap the `Share` button in Safari and select `Add to Home Screen`. 
4. The first time you connect, your Mac will prompt an authorization dialog. Click "Allow" to grant your phone access.

---

<a name="chinese"></a>
## 🚀 中文说明

将你的 iPhone 变成一块极致流畅、低延迟的高级 Mac 触控板和键盘。完全无线，极其安全。

### ✨ 核心功能
- **沉浸式 PWA 体验**：将网页“添加到主屏幕”，即可获得全屏无边框的 App 级体验，以及极具艺术感的专属签名图标。
- **高精度触控板**：采用原生 Quartz 引擎，拥有完美的物理边缘拦截，光标绝不会飞出屏幕。
- **智能手势支持**：
  - 单指移动：移动光标
  - 单指轻点：左键单击
  - 双指轻点：右键单击
  - 双指滑动：页面上下滚动
  - 三指左右滑动：切换桌面
  - 三指上滑：调度中心 (Mission Control)
  - **长按 (500ms)**：伴随双震动反馈后即可拖拽窗口或框选文字，松手完成。
- **极速智能复制**：当你双击或者拖拽框选结束时，Mac 会自动执行 `Cmd + C`。内置剪贴板嗅探，只有当你真正成功抓取到新文字时，手机端才会给出震动反馈，且 Mac 会在光标处弹出优雅的原生悬浮窗 (HUD) 提示“已复制”。
- **键盘与长文本投射**：可以直接使用手机全键盘输入，或在文本框内粘贴大段长文本（中英文皆可），一键瞬间粘贴投射到 Mac 上。
- **媒体与系统控制**：快捷播放/暂停媒体、切换全屏、让 Mac 息屏，或是远程唤醒 Mac（已完美解决 macOS 唤醒秒睡机制）。
- **极客级安全防护**：
  - **内网物理隔离**：底层代码严格限制，拒绝任何非局域网 IP 访问。
  - **白名单设备授权**：首次连接的陌生手机，Mac 屏幕中央会弹出系统级确认框，只有你亲自点击“允许”，手机才能获得控制权。

### 🛠 安装指南

1. **克隆项目到本地：**
   ```bash
   git clone https://github.com/yourusername/airmac.git
   cd airmac
   ```
2. **配置 Python 环境：**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
3. **授予辅助功能权限：**
   - 进入 `系统设置` > `隐私与安全性` > `辅助功能`
   - 为你当前使用的 `Terminal` (终端) 或 `iTerm` 开启权限。
4. **启动服务：**
   - **临时运行 (调试用):** `uvicorn main:app --host 0.0.0.0 --port 8000`
   - **后台常驻服务 (推荐):** 运行 `./install_service.sh`，这会让脚本作为 Mac 的底层守护进程在后台静默运行，且开机自启。

### 📱 手机连接方法
1. 确保你的 iPhone 和 Mac 连在**同一个 Wi-Fi 局域网**。
2. 打开 iPhone 的 Safari 浏览器，输入终端打印出来的网址（例如 `http://192.168.x.x:8000`）。
3. **强烈建议**：点击 Safari 底部中间的分享按钮，选择“**添加到主屏幕**”。
4. 首次访问时，Mac 屏幕会弹出设备授权提示，点击“允许”即可开始尽情操控！
