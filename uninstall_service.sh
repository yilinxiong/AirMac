#!/bin/bash

SERVICE_NAME="com.yourname.iphonemacremote"
PLIST_PATH="$HOME/Library/LaunchAgents/${SERVICE_NAME}.plist"

echo "正在停止并卸载后台服务..."
# 尝试卸载服务
launchctl unload -w "$PLIST_PATH" 2>/dev/null

if [ -f "$PLIST_PATH" ]; then
    echo "正在删除配置文件: $PLIST_PATH"
    rm "$PLIST_PATH"
    echo "✅ 卸载成功！后台服务已停止且不会再开机自启。"
else
    echo "⚠️ 未找到配置文件，服务可能已经被卸载。"
fi
