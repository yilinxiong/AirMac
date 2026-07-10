import socket
import json
import logging
import subprocess
import os
import pyperclip
import time
import Quartz
import ipaddress
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.responses import HTMLResponse
from pynput.keyboard import Controller as KeyboardController, Key

app = FastAPI()
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

def is_allowed_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
        # 允许私有局域网 IP (192.168.x.x, 10.x.x.x, 172.16.x.x) 和本机回环 IP (127.0.0.1)
        return ip.is_private or ip.is_loopback
    except ValueError:
        return False

@app.get("/")
async def get_index(request: Request):
    if not is_allowed_ip(request.client.host):
        raise HTTPException(status_code=403, detail="Access Forbidden: Local network only.")
        
    with open("index.html", "r", encoding="utf-8") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    if not is_allowed_ip(websocket.client.host):
        logger.warning(f"Rejected connection from non-local IP: {websocket.client.host}")
        await websocket.close(code=1008)
        return
        
    await websocket.accept()
    logger.info("iPhone Client Connected.")
    try:
        while True:
            data = await websocket.receive_text()
            try:
                cmd = json.loads(data)
                action = cmd.get("action")
                
                if action == "auto_copy":
                    os.system("osascript -e 'tell application \"System Events\" to keystroke \"c\" using command down'")
                    os.system("./hud '✅ 自动复制成功' &")
                    
                elif action == "mouse_down":
                    current_event = Quartz.CGEventCreate(None)
                    current_pos = Quartz.CGEventGetLocation(current_event)
                    event = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseDown, (current_pos.x, current_pos.y), Quartz.kCGMouseButtonLeft)
                    Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
                    
                elif action == "mouse_up":
                    current_event = Quartz.CGEventCreate(None)
                    current_pos = Quartz.CGEventGetLocation(current_event)
                    event = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseUp, (current_pos.x, current_pos.y), Quartz.kCGMouseButtonLeft)
                    Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
                    
                elif action == "mouse_drag":
                    dx = cmd.get("dx", 0)
                    dy = cmd.get("dy", 0)
                    
                    current_event = Quartz.CGEventCreate(None)
                    current_pos = Quartz.CGEventGetLocation(current_event)
                    new_x = current_pos.x + dx
                    new_y = current_pos.y + dy
                    
                    event = Quartz.CGEventCreateMouseEvent(
                        None, 
                        Quartz.kCGEventLeftMouseDragged, 
                        (new_x, new_y), 
                        Quartz.kCGMouseButtonLeft
                    )
                    Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
                    
                elif action == "move":
                    dx = cmd.get("dx", 0)
                    dy = cmd.get("dy", 0)
                    
                    current_event = Quartz.CGEventCreate(None)
                    current_pos = Quartz.CGEventGetLocation(current_event)
                    new_x = current_pos.x + dx
                    new_y = current_pos.y + dy
                    
                    event = Quartz.CGEventCreateMouseEvent(
                        None, 
                        Quartz.kCGEventMouseMoved, 
                        (new_x, new_y), 
                        Quartz.kCGMouseButtonLeft
                    )
                    Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
                    
                elif action == "click":
                    button = cmd.get("button", "left")
                    current_event = Quartz.CGEventCreate(None)
                    current_pos = Quartz.CGEventGetLocation(current_event)
                    
                    if button == "left":
                        mouse_down = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseDown, (current_pos.x, current_pos.y), Quartz.kCGMouseButtonLeft)
                        mouse_up = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseUp, (current_pos.x, current_pos.y), Quartz.kCGMouseButtonLeft)
                        Quartz.CGEventPost(Quartz.kCGHIDEventTap, mouse_down)
                        Quartz.CGEventPost(Quartz.kCGHIDEventTap, mouse_up)
                    elif button == "right":
                        mouse_down = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventRightMouseDown, (current_pos.x, current_pos.y), Quartz.kCGMouseButtonRight)
                        mouse_up = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventRightMouseUp, (current_pos.x, current_pos.y), Quartz.kCGMouseButtonRight)
                        Quartz.CGEventPost(Quartz.kCGHIDEventTap, mouse_down)
                        Quartz.CGEventPost(Quartz.kCGHIDEventTap, mouse_up)
                        
                elif action == "triple_click":
                    current_event = Quartz.CGEventCreate(None)
                    current_pos = Quartz.CGEventGetLocation(current_event)
                    
                    # Quartz needs sequential click states. 
                    # The first click was already sent by the first tap. 
                    # Here we send state 2 and then state 3 quickly.
                    
                    # Double click state
                    md2 = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseDown, (current_pos.x, current_pos.y), Quartz.kCGMouseButtonLeft)
                    Quartz.CGEventSetIntegerValueField(md2, Quartz.kCGMouseEventClickState, 2)
                    mu2 = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseUp, (current_pos.x, current_pos.y), Quartz.kCGMouseButtonLeft)
                    Quartz.CGEventSetIntegerValueField(mu2, Quartz.kCGMouseEventClickState, 2)
                    Quartz.CGEventPost(Quartz.kCGHIDEventTap, md2)
                    Quartz.CGEventPost(Quartz.kCGHIDEventTap, mu2)
                    
                    # Triple click state
                    md3 = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseDown, (current_pos.x, current_pos.y), Quartz.kCGMouseButtonLeft)
                    Quartz.CGEventSetIntegerValueField(md3, Quartz.kCGMouseEventClickState, 3)
                    mu3 = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseUp, (current_pos.x, current_pos.y), Quartz.kCGMouseButtonLeft)
                    Quartz.CGEventSetIntegerValueField(mu3, Quartz.kCGMouseEventClickState, 3)
                    Quartz.CGEventPost(Quartz.kCGHIDEventTap, md3)
                    Quartz.CGEventPost(Quartz.kCGHIDEventTap, mu3)
                        
                elif action == "scroll":
                    dy = cmd.get("dy", 0)
                    # Quartz scroll event takes units and values
                    scroll_event = Quartz.CGEventCreateScrollWheelEvent(None, Quartz.kCGScrollEventUnitPixel, 1, int(-dy))
                    Quartz.CGEventPost(Quartz.kCGHIDEventTap, scroll_event)
                                        
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
                        
                        # Auto Enter
                        time.sleep(0.1)
                        keyboard.press(Key.enter)
                        keyboard.release(Key.enter)
                        
            except json.JSONDecodeError:
                logger.error("Invalid JSON received.")
            except Exception as e:
                logger.error(f"Error executing command: {e}")
                
    except WebSocketDisconnect:
        logger.info("iPhone Client Disconnected.")
