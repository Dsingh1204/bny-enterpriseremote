"""
BNY EnterpriseRemote - Python Native Client Agent
Connects to the cloud relay server and enables real mouse/keyboard control via pyautogui
"""

import socketio
import pyautogui
import mss
import base64
import io
import time
import threading
import platform
import socket as sock
import sys
from PIL import Image

# ============== CONFIG ==============
SERVER_URL = "https://bny-enterpriseremote.onrender.com"
SCREENSHOT_FPS = 5        # frames per second to send
SCREENSHOT_QUALITY = 40   # JPEG quality (1-100)
SCREENSHOT_SCALE = 0.5    # scale factor for screenshots

# Disable pyautogui failsafe (move mouse to corner to stop)
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0

# ============== SOCKET ==============
sio = socketio.Client(ssl_verify=False)

session_id = None
access_code = None
control_enabled = False
capture_thread = None
stop_capture = threading.Event()


def get_system_info():
    hostname = sock.gethostname()
    try:
        local_ip = sock.gethostbyname(hostname)
    except Exception:
        local_ip = "Unknown"
    return {
        "hostname": hostname,
        "platform": platform.system(),
        "os": f"{platform.system()} {platform.release()}",
        "ip": local_ip,
        "arch": platform.machine(),
        "python": sys.version.split()[0]
    }


def capture_and_send():
    """Continuously capture screen and send frames to server."""
    with mss.mss() as sct:
        monitor = sct.monitors[0]  # Full screen (all monitors combined)
        while not stop_capture.is_set():
            try:
                if not sio.connected:
                    time.sleep(0.5)
                    continue

                # Capture screenshot
                screenshot = sct.grab(monitor)
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")

                # Scale down
                w = int(img.width * SCREENSHOT_SCALE)
                h = int(img.height * SCREENSHOT_SCALE)
                img = img.resize((w, h), Image.LANCZOS)

                # Encode as JPEG base64
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=SCREENSHOT_QUALITY)
                frame_b64 = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()

                sio.emit("screen:frame", {
                    "frame": frame_b64,
                    "width": w,
                    "height": h,
                    "originalWidth": screenshot.width,
                    "originalHeight": screenshot.height
                })

                time.sleep(1.0 / SCREENSHOT_FPS)

            except Exception as e:
                print(f"[Capture Error] {e}")
                time.sleep(1)


# ============== SOCKET EVENTS ==============

@sio.event
def connect():
    print(f"[+] Connected to server: {SERVER_URL}")
    system_info = get_system_info()
    print(f"[+] System: {system_info['hostname']} ({system_info['os']})")

    def on_register(response):
        global session_id, access_code
        if response.get("success"):
            session_id = response["sessionId"]
            access_code = response["accessCode"]
            print(f"\n{'='*50}")
            print(f"  BNY EnterpriseRemote - Client Agent")
            print(f"{'='*50}")
            print(f"  Access Code: {access_code}")
            print(f"  Session ID:  {session_id[:8]}...")
            print(f"  Share this code with your tech support admin")
            print(f"{'='*50}\n")
        else:
            print(f"[!] Registration failed: {response.get('error')}")

    sio.emit("client:register", {"systemInfo": system_info}, callback=on_register)


@sio.event
def disconnect():
    global control_enabled
    control_enabled = False
    stop_capture.set()
    print("[!] Disconnected from server")


@sio.on("admin:connected")
def on_admin_connected(data):
    global capture_thread
    admin_name = data.get("adminName", "Tech Support")
    print(f"\n[+] Admin connected: {admin_name}")
    print("[+] Starting screen capture...")

    # Start screen capture thread
    stop_capture.clear()
    capture_thread = threading.Thread(target=capture_and_send, daemon=True)
    capture_thread.start()


@sio.on("admin:disconnected")
def on_admin_disconnected():
    global control_enabled
    print("[!] Admin disconnected")
    control_enabled = False
    stop_capture.set()


@sio.on("control:request")
def on_control_request(data):
    admin_name = data.get("adminName", "Tech Support")
    print(f"\n[?] {admin_name} is requesting remote control.")
    answer = input("Allow remote control? (yes/no): ").strip().lower()
    granted = answer in ("yes", "y")
    sio.emit("control:response", {"granted": granted})
    global control_enabled
    control_enabled = granted
    print(f"[{'+'if granted else '!'}] Remote control {'GRANTED' if granted else 'DENIED'}")


@sio.on("mouse:event")
def on_mouse_event(data):
    if not control_enabled:
        return
    try:
        event_type = data.get("type")
        x = data.get("x", 0)
        y = data.get("y", 0)
        button = data.get("button", "left")

        # Map button name
        btn_map = {"left": "left", "right": "right", "middle": "middle"}
        btn = btn_map.get(button, "left")

        if event_type == "move":
            pyautogui.moveTo(x, y, duration=0)
        elif event_type == "click":
            pyautogui.click(x, y, button=btn)
        elif event_type == "dblclick":
            pyautogui.doubleClick(x, y, button=btn)
        elif event_type == "mousedown":
            pyautogui.mouseDown(x, y, button=btn)
        elif event_type == "mouseup":
            pyautogui.mouseUp(x, y, button=btn)
        elif event_type == "scroll":
            delta = data.get("deltaY", 0)
            clicks = -int(delta / 100)
            pyautogui.scroll(clicks, x=x, y=y)
    except Exception as e:
        print(f"[Mouse Error] {e}")


@sio.on("keyboard:event")
def on_keyboard_event(data):
    if not control_enabled:
        return
    try:
        event_type = data.get("type")
        key = data.get("key", "")
        text = data.get("text", "")

        if event_type == "keydown":
            mapped = map_key(key)
            if mapped:
                pyautogui.keyDown(mapped)
        elif event_type == "keyup":
            mapped = map_key(key)
            if mapped:
                pyautogui.keyUp(mapped)
        elif event_type == "type":
            if text:
                pyautogui.write(text, interval=0.02)
    except Exception as e:
        print(f"[Keyboard Error] {e}")


def map_key(key):
    """Map browser KeyboardEvent.key values to pyautogui key names."""
    key_map = {
        "Enter": "enter", "Tab": "tab", "Backspace": "backspace",
        "Delete": "delete", "Escape": "escape", "Space": "space",
        "ArrowUp": "up", "ArrowDown": "down", "ArrowLeft": "left", "ArrowRight": "right",
        "Home": "home", "End": "end", "PageUp": "pageup", "PageDown": "pagedown",
        "F1": "f1", "F2": "f2", "F3": "f3", "F4": "f4", "F5": "f5",
        "F6": "f6", "F7": "f7", "F8": "f8", "F9": "f9", "F10": "f10",
        "F11": "f11", "F12": "f12",
        "Control": "ctrl", "Alt": "alt", "Shift": "shift", "Meta": "win",
        "CapsLock": "capslock", "Insert": "insert",
        "a": "a", "b": "b", "c": "c", "d": "d", "e": "e", "f": "f",
        "g": "g", "h": "h", "i": "i", "j": "j", "k": "k", "l": "l",
        "m": "m", "n": "n", "o": "o", "p": "p", "q": "q", "r": "r",
        "s": "s", "t": "t", "u": "u", "v": "v", "w": "w", "x": "x",
        "y": "y", "z": "z",
    }
    return key_map.get(key, key.lower() if len(key) == 1 else None)


@sio.on("chat:message")
def on_chat(data):
    sender = data.get("senderName", "Admin")
    text = data.get("text", "")
    print(f"\n[Chat] {sender}: {text}")


@sio.on("session:ended")
def on_session_ended(data):
    reason = data.get("reason", "Session ended by admin")
    print(f"\n[!] Session ended: {reason}")
    stop_capture.set()
    sio.disconnect()


# ============== MAIN ==============

def main():
    print(f"[*] BNY EnterpriseRemote - Native Client Agent")
    print(f"[*] Connecting to: {SERVER_URL}")
    print(f"[*] Press Ctrl+C to stop\n")

    try:
        sio.connect(SERVER_URL, transports=["websocket", "polling"])
        sio.wait()
    except KeyboardInterrupt:
        print("\n[*] Stopping agent...")
        stop_capture.set()
        if sio.connected:
            sio.disconnect()
    except Exception as e:
        print(f"[!] Connection error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
