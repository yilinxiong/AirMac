import socket
import json
import logging
import subprocess
import os
import pyperclip
import time
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pynput.mouse import Controller as MouseController, Button
from pynput.keyboard import Controller as KeyboardController, Key

app = FastAPI()
mouse = MouseController()
keyboard = KeyboardController()

# Set up basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MacRemote")

def get_local_ip():
    try:
        # Create a dummy socket to determine local IP used for internet access
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

LOCAL_IP = get_local_ip()
PORT = 8000

@app.on_event("startup")
async def startup_event():
    print("\n" + "="*50)
    print("🚀 Mac Remote Controller Server Started!")
    print("📱 Please open Safari on your iPhone and access:")
    print(f"👉 http://{LOCAL_IP}:{PORT} 👈")
    print("="*50 + "\n")

@app.get("/")
async def get_index():
    with open("index.html", "r", encoding="utf-8") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("iPhone Client Connected.")
    try:
        while True:
            data = await websocket.receive_text()
            try:
                cmd = json.loads(data)
                action = cmd.get("action")
                
                if action == "move":
                    dx = cmd.get("dx", 0)
                    dy = cmd.get("dy", 0)
                    mouse.move(dx, dy)
                    
                elif action == "click":
                    button = cmd.get("button", "left")
                    if button == "left":
                        mouse.click(Button.left, 1)
                    elif button == "right":
                        mouse.click(Button.right, 1)
                        
                elif action == "scroll":
                    dy = cmd.get("dy", 0)
                    # pynput scroll dy: positive for up, negative for down.
                    mouse.scroll(0, -dy * 0.05) 
                    
                elif action == "type":
                    char = cmd.get("char", "")
                    if char:
                        keyboard.type(char)
                        
                elif action == "keydown":
                    key = cmd.get("key", "")
                    if key == "Backspace":
                        keyboard.press(Key.backspace)
                        keyboard.release(Key.backspace)
                    elif key == "Enter":
                        keyboard.press(Key.enter)
                        keyboard.release(Key.enter)
                        
                elif action == "media":
                    command = cmd.get("command", "")
                    if command == "playpause":
                        # Play/Pause media key
                        keyboard.press(Key.media_play_pause)
                        keyboard.release(Key.media_play_pause)
                    elif command == "fullscreen":
                        # Cmd + Ctrl + F for macOS fullscreen toggle
                        keyboard.press(Key.cmd)
                        keyboard.press(Key.ctrl)
                        keyboard.press('f')
                        keyboard.release('f')
                        keyboard.release(Key.ctrl)
                        keyboard.release(Key.cmd)

                # --- New Features: Multitasking & Desktop Management ---
                elif action == "mission_control":
                    # Use AppleScript for Mission Control (more reliable than pynput)
                    subprocess.run(["osascript", "-e", 'tell application "System Events" to key code 126 using control down'])

                elif action == "space_left":
                    # Use AppleScript to switch to left desktop
                    subprocess.run(["osascript", "-e", 'tell application "System Events" to key code 123 using control down'])

                elif action == "space_right":
                    # Use AppleScript to switch to right desktop
                    subprocess.run(["osascript", "-e", 'tell application "System Events" to key code 124 using control down'])

                elif action == "cmd_tab":
                    # Cmd + Tab to switch to previous app
                    keyboard.press(Key.cmd)
                    keyboard.press(Key.tab)
                    keyboard.release(Key.tab)
                    keyboard.release(Key.cmd)
                    
                # --- New Features: Sleep & Text Projection ---
                elif action == "display_sleep":
                    # Use displaysleepnow for light sleep (turns off display only), so wake_watch can still work
                    os.system("pmset displaysleepnow")
                    
                elif action == "wake_watch":
                    os.system("caffeinate -u -t 2")

                elif action == "type_text":
                    text = cmd.get("text", "")
                    if text:
                        pyperclip.copy(text)
                        # Slight delay to ensure clipboard is ready
                        time.sleep(0.1)
                        keyboard.press(Key.cmd)
                        keyboard.press('v')
                        keyboard.release('v')
                        keyboard.release(Key.cmd)
                        
            except json.JSONDecodeError:
                logger.error("Invalid JSON received.")
            except Exception as e:
                logger.error(f"Error executing command: {e}")
                
    except WebSocketDisconnect:
        logger.info("iPhone Client Disconnected.")
