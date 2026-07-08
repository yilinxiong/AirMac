# iPhone Mac Remote Controller

这是一套完整的局域网远程控制方案，允许您通过 iPhone Safari 浏览器控制 Mac 的鼠标和键盘。

## 1. 环境配置

打开 macOS 的 Terminal (终端)，执行以下命令初始化项目环境：

```bash
# 1. 进入项目目录
cd "/Users/yilinxiong/Desktop/Mac Remote Controller/iphone_mac_remote"

# 2. 创建 Python 虚拟环境
python3 -m venv venv

# 3. 激活虚拟环境
source venv/bin/activate

# 4. 安装所需的依赖库
pip install -r requirements.txt
```

## 2. ⚠️ 最重要的授权步骤 (必做)

由于本脚本使用 `pynput` 模拟鼠标和键盘，macOS 的安全机制会默认拦截。**如果不授权，鼠标和键盘将无法移动和点击。**

1. 打开 macOS 的 **系统设置** (System Settings)。
2. 导航到 **隐私与安全性** (Privacy & Security)。
3. 点击 **辅助功能** (Accessibility)。
4. 如果你在 Terminal (终端) 中运行此脚本，请打开 **Terminal** 或 **iTerm** 前面的开关。
5. 如果你在 VS Code 中运行，请打开 **Visual Studio Code** 前面的开关。
   *(如果列表中没有你需要授权的应用，请点击底部的 `+` 号，手动添加该应用并开启)*。

## 3. 运行服务器

确保你已经在终端中激活了虚拟环境 (`source venv/bin/activate`)，然后运行以下命令启动服务：

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

服务器启动后，会在终端中打印出一个带 IP 的网址，例如 `http://192.168.x.x:8000`。

## 4. 手机连接与操作

1. 确保您的 iPhone 和 Mac 连接在 **同一个局域网 (Wi-Fi)**。
2. 打开 iPhone 的 Safari 浏览器，输入刚才终端中显示的 URL。
3. **建议**：点击 Safari 底部中间的分享按钮，选择“**添加到主屏幕**”，这样可以获得完全无边框的全屏 App 体验！

### 触控板操作指南：
- **移动光标**：单指滑动。
- **左键单击**：单指轻点。
- **右键单击**：双指轻点，或单指长按。
- **页面滚动**：双指上下滑动。
- **键盘输入**：点击“⌨️ 键盘”按钮，调出手机键盘输入。
- **快捷键**：顶部提供了媒体播放/暂停、以及 Mac 窗口全屏 (Cmd+Ctrl+F) 的快捷按钮。
