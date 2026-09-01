import socket
import json
import logging
import subprocess
import os
import pyperclip
import time
import Quartz
import ipaddress
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException, Response
from fastapi.responses import HTMLResponse, FileResponse
from pynput.keyboard import Controller as KeyboardController, Key

app = FastAPI()
keyboard = KeyboardController()



# Set up basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AirMac")

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
    try:
        loop = asyncio.get_running_loop()
        loop.set_debug(True)
        loop.slow_callback_duration = 0.1 # 100ms
        logger.info("Asyncio debug mode enabled. Slow callbacks (>100ms) will be logged.")
    except Exception as e:
        logger.error(f"Failed to enable asyncio debug mode: {e}")
        
    print("\n" + "="*50)
    print("🚀 AirMac Server Started!")
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

def load_whitelist() -> set:
    try:
        with open("whitelist.json", "r") as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()

def save_whitelist(whitelist_set: set):
    with open("whitelist.json", "w") as f:
        json.dump(list(whitelist_set), f)

# Global set and lock
device_whitelist = load_whitelist()
prompt_locks = {}

# Virtual Coordinates for Edge Momentum (Dock / Menu Bar triggering)
last_move_time = 0
virtual_x = 0
virtual_y = 0
displays_cache = None
displays_cache_time = 0

def get_displays():
    global displays_cache, displays_cache_time
    current_time = time.time()
    if displays_cache is None or current_time - displays_cache_time > 5.0:
        success, active_displays, count = Quartz.CGGetActiveDisplayList(10, None, None)
        if success == 0 and count > 0:
            displays_cache = []
            for i in range(count):
                bounds = Quartz.CGDisplayBounds(active_displays[i])
                displays_cache.append({
                    "min_x": bounds.origin.x,
                    "max_x": bounds.origin.x + bounds.size.width - 1,
                    "min_y": bounds.origin.y,
                    "max_y": bounds.origin.y + bounds.size.height - 1,
                })
        displays_cache_time = current_time
    return displays_cache

def clamp_to_displays(x, y):
    displays = get_displays()
    if not displays:
        return x, y
        
    for bounds in displays:
        if bounds["min_x"] <= x <= bounds["max_x"] and bounds["min_y"] <= y <= bounds["max_y"]:
            return x, y
            
    best_x, best_y = x, y
    min_dist = float('inf')
    for bounds in displays:
        cx = max(bounds["min_x"], min(x, bounds["max_x"]))
        cy = max(bounds["min_y"], min(y, bounds["max_y"]))
        dist = (cx - x)**2 + (cy - y)**2
        if dist < min_dist:
            min_dist = dist
            best_x, best_y = cx, cy
    return best_x, best_y

async def prompt_for_approval(device_id: str, device_name: str) -> bool:
    if device_id in prompt_locks:
        return False
        
    prompt_locks[device_id] = True
    try:
        script = f'''
        tell application "System Events"
            activate
            display dialog "新设备 [{device_name}] 请求连接 AirMac\\n\\n是否允许该设备控制本机？" buttons {{"拒绝", "允许"}} default button "拒绝" with title "安全拦截"
        end tell
        '''
        process = await asyncio.create_subprocess_exec(
            "osascript", "-e", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        return "允许" in stdout.decode()
    finally:
        del prompt_locks[device_id]


@app.get("/")
async def get_frontend(request: Request):
    if not is_allowed_ip(request.client.host):
        logger.warning(f"Rejected access from non-local IP: {request.client.host}")
        raise HTTPException(status_code=403, detail="Access denied: Only local network allowed")
        
    html_file = os.path.join(os.path.dirname(__file__), "index.html")
    with open(html_file, "r") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)

@app.get("/icon.png")
async def get_icon():
    icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
    if os.path.exists(icon_path):
        return FileResponse(icon_path)
    return Response(status_code=404)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, device_id: str = None, device_name: str = "未知设备"):
    global last_move_time, virtual_x, virtual_y
    if not is_allowed_ip(websocket.client.host):
        logger.warning(f"Rejected connection from non-local IP: {websocket.client.host}")
        await websocket.close(code=1008)
        return
        
    if not device_id:
        logger.warning("Rejected connection: No device_id provided")
        await websocket.close(code=1008)
        return
        
    if device_id not in device_whitelist:
        if device_id in prompt_locks:
            # Tell client to wait
            await websocket.close(code=4001)
            return
            
        logger.info(f"Prompting approval for new device: {device_name}")
        approved = await prompt_for_approval(device_id, device_name)
        if approved:
            device_whitelist.add(device_id)
            save_whitelist(device_whitelist)
            logger.info(f"Device {device_name} approved and whitelisted.")
        else:
            logger.warning(f"Device {device_name} rejected by user.")
            await websocket.close(code=4003)
            return

    await websocket.accept()
    logger.info(f"Client {device_name} Connected.")
    try:
        while True:
            data = await websocket.receive_text()
            start_time = time.time()
            try:
                cmd = json.loads(data)
                action = cmd.get("action")
                
                if action == "auto_copy":
                    async def do_auto_copy():
                        try:
                            # 1. 备份当前剪贴板
                            old_clipboard = pyperclip.paste()
                        
                            # 2. 清空剪贴板 (写入空字符串)
                            pyperclip.copy('')
                        
                            # 3. 模拟 Cmd + C
                            process = await asyncio.create_subprocess_exec(
                                "osascript", "-e", 'tell application "System Events" to keystroke "c" using command down',
                                stdout=asyncio.subprocess.DEVNULL,
                                stderr=asyncio.subprocess.DEVNULL
                            )
                            await process.wait()
                        
                            # 4. 等待 0.15 秒让系统完成复制
                            await asyncio.sleep(0.15)
                        
                            # 5. 嗅探剪贴板
                            new_clipboard = pyperclip.paste()
                        
                            if not new_clipboard or new_clipboard == '':
                                # 挥空了 (没有选中任何文字)：恢复旧的剪贴板内容
                                if old_clipboard:
                                    pyperclip.copy(old_clipboard)
                            else:
                                # 成功抓取到新文字：发送成功信号给前端
                                success_msg = {
                                    "type": "copy_success", 
                                    "preview": new_clipboard[:20] + "..." if len(new_clipboard) > 20 else new_clipboard
                                }
                                await websocket.send_text(json.dumps(success_msg))
                                os.system("./hud '✅ 自动复制成功' &")
                        except Exception as e:
                            logger.error(f"Auto copy error: {e}")
                    
                    asyncio.create_task(do_auto_copy())
                    
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
                    
                    current_time = time.time()
                    
                    if current_time - last_move_time > 0.2:
                        current_event = Quartz.CGEventCreate(None)
                        current_pos = Quartz.CGEventGetLocation(current_event)
                        virtual_x = current_pos.x
                        virtual_y = current_pos.y
                        
                    virtual_x += dx
                    virtual_y += dy
                    
                    virtual_x, virtual_y = clamp_to_displays(virtual_x, virtual_y)
                    
                    last_move_time = current_time
                    
                    event = Quartz.CGEventCreateMouseEvent(
                        None, 
                        Quartz.kCGEventLeftMouseDragged, 
                        (virtual_x, virtual_y), 
                        Quartz.kCGMouseButtonLeft
                    )
                    Quartz.CGEventSetIntegerValueField(event, Quartz.kCGMouseEventDeltaX, int(dx))
                    Quartz.CGEventSetIntegerValueField(event, Quartz.kCGMouseEventDeltaY, int(dy))
                    Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
                    
                elif action == "move":
                    dx = cmd.get("dx", 0)
                    dy = cmd.get("dy", 0)
                    
                    current_time = time.time()
                    
                    if current_time - last_move_time > 0.2:
                        current_event = Quartz.CGEventCreate(None)
                        current_pos = Quartz.CGEventGetLocation(current_event)
                        virtual_x = current_pos.x
                        virtual_y = current_pos.y
                        
                    virtual_x += dx
                    virtual_y += dy
                    
                    virtual_x, virtual_y = clamp_to_displays(virtual_x, virtual_y)
                    
                    last_move_time = current_time
                    
                    event = Quartz.CGEventCreateMouseEvent(
                        None, 
                        Quartz.kCGEventMouseMoved, 
                        (virtual_x, virtual_y), 
                        Quartz.kCGMouseButtonLeft
                    )
                    Quartz.CGEventSetIntegerValueField(event, Quartz.kCGMouseEventDeltaX, int(dx))
                    Quartz.CGEventSetIntegerValueField(event, Quartz.kCGMouseEventDeltaY, int(dy))
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
                    async def do_mission_control():
                        process = await asyncio.create_subprocess_exec("osascript", "-e", 'tell application "System Events" to key code 126 using control down', stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                        await process.wait()
                    asyncio.create_task(do_mission_control())

                elif action == "space_left":
                    async def do_space_left():
                        process = await asyncio.create_subprocess_exec("osascript", "-e", 'tell application "System Events" to key code 123 using control down', stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                        await process.wait()
                    asyncio.create_task(do_space_left())

                elif action == "space_right":
                    async def do_space_right():
                        process = await asyncio.create_subprocess_exec("osascript", "-e", 'tell application "System Events" to key code 124 using control down', stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                        await process.wait()
                    asyncio.create_task(do_space_right())

                elif action == "cmd_tab":
                    # Cmd + Tab to switch to previous app
                    keyboard.press(Key.cmd)
                    keyboard.press(Key.tab)
                    keyboard.release(Key.tab)
                    keyboard.release(Key.cmd)
                    
                # --- New Features: Sleep & Text Projection ---
                elif action == "display_sleep":
                    async def do_display_sleep():
                        process = await asyncio.create_subprocess_exec("pmset", "displaysleepnow", stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                        await process.wait()
                    asyncio.create_task(do_display_sleep())
                    
                elif action == "wake_watch":
                    # 在后台运行 caffeinate 以免阻塞 WebSocket
                    # 延时多次发送 shift 按键，彻底打破 macOS 休眠防误触机制 (Dark Wake)
                    async def perform_wake():
                        os.system("caffeinate -u -t 3 &")
                        await asyncio.sleep(0.5)
                        keyboard.press(Key.shift)
                        keyboard.release(Key.shift)
                        await asyncio.sleep(1.5)
                        keyboard.press(Key.shift)
                        keyboard.release(Key.shift)
                        
                    asyncio.create_task(perform_wake())

                elif action == "type_text":
                    text = cmd.get("text", "")
                    if text:
                        async def do_type_text(t):
                            pyperclip.copy(t)
                            # Slight delay to ensure clipboard is ready
                            await asyncio.sleep(0.15)
                            keyboard.press(Key.cmd)
                            keyboard.press('v')
                            keyboard.release('v')
                            keyboard.release(Key.cmd)
                            
                            # Auto Enter: Wait longer for long texts so Mac has time to render/paste
                            paste_delay = min(0.8, 0.15 + (len(t) * 0.005))
                            await asyncio.sleep(paste_delay)
                            
                            keyboard.press(Key.enter)
                            keyboard.release(Key.enter)
                        asyncio.create_task(do_type_text(text))
                        
                process_duration = time.time() - start_time
                if process_duration > 0.05:
                    logger.warning(f"SLOW PROCESSING: Action '{action}' took {process_duration*1000:.2f}ms to process. This may cause cursor lag!")
                        
            except json.JSONDecodeError:
                logger.error("Invalid JSON received.")
            except Exception as e:
                logger.error(f"Error executing command: {e}")
                
    except WebSocketDisconnect:
        logger.info("iPhone Client Disconnected.")
