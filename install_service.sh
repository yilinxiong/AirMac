#!/bin/bash

# 1. 定义服务名称和 plist 存放路径
SERVICE_NAME="com.yourname.iphonemacremote"
PLIST_PATH="$HOME/Library/LaunchAgents/${SERVICE_NAME}.plist"

# 2. 获取当前项目的绝对路径
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="${PROJECT_DIR}/remote.log"

# 3. 寻找 Python 解释器
if [ -f "${PROJECT_DIR}/venv/bin/python" ]; then
    PYTHON_PATH="${PROJECT_DIR}/venv/bin/python"
    echo "✅ 找到虚拟环境 Python: $PYTHON_PATH"
else
    PYTHON_PATH=$(which python3)
    echo "⚠️ 未找到虚拟环境，使用系统 Python: $PYTHON_PATH"
fi

# 4. 生成 .plist 文件
echo "正在生成 Launch Agent 配置文件..."
cat <<EOF > "$PLIST_PATH"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${SERVICE_NAME}</string>
    
    <key>WorkingDirectory</key>
    <string>${PROJECT_DIR}</string>
    
    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON_PATH}</string>
        <string>-m</string>
        <string>uvicorn</string>
        <string>main:app</string>
        <string>--host</string>
        <string>0.0.0.0</string>
        <string>--port</string>
        <string>8000</string>
    </array>
    
    <key>RunAtLoad</key>
    <true/>
    
    <key>KeepAlive</key>
    <true/>
    
    <key>StandardOutPath</key>
    <string>${LOG_FILE}</string>
    
    <key>StandardErrorPath</key>
    <string>${LOG_FILE}</string>
</dict>
</plist>
EOF

echo "✅ plist 文件已保存至: $PLIST_PATH"

# 确保日志文件存在
touch "$LOG_FILE"

# 5. 加载服务
echo "正在加载后台服务..."
# 尝试先卸载可能存在的旧服务
launchctl unload -w "$PLIST_PATH" 2>/dev/null
# 加载新服务
launchctl load -w "$PLIST_PATH"

# 6. 输出结果
echo "====================================================="
echo "🎉 安装完成！你的 Mac Remote Controller 已在后台静默运行。"
echo "由于设置了 KeepAlive，即使服务崩溃也会自动重启，开机自动生效。"
echo ""
echo "📝 查看实时日志，请运行："
echo "tail -f remote.log"
echo "====================================================="
