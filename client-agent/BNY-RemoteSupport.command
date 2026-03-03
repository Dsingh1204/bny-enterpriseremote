#!/bin/bash
# BNY EnterpriseRemote - Double-click to start remote support session
# This script auto-installs dependencies and runs the support agent

SERVER_URL="https://bny-enterpriseremote.onrender.com"

# Keep terminal open on error
trap 'echo ""; echo "An error occurred. Press Enter to exit."; read' ERR

clear
echo "╔══════════════════════════════════════════╗"
echo "║     BNY EnterpriseRemote - Client Agent   ║"
echo "║         Connecting to support...           ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# --- Check Python ---
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        VER=$("$cmd" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)
        MAJOR=$(echo "$VER" | cut -d. -f1)
        MINOR=$(echo "$VER" | cut -d. -f2)
        if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 7 ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    osascript -e 'display dialog "Python 3.7+ is required.\n\nPlease download it from:\nhttps://www.python.org/downloads/\n\nThen double-click this file again." with title "BNY EnterpriseRemote" buttons {"OK"} default button "OK" with icon stop' 2>/dev/null
    echo "ERROR: Python 3.7+ not found. Please install from https://www.python.org/downloads/"
    read
    exit 1
fi

echo "✓ Python found: $PYTHON ($("$PYTHON" --version 2>&1))"

# --- Install dependencies silently ---
echo "Installing dependencies (first run only)..."
"$PYTHON" -m pip install --quiet --user \
    "python-socketio[client]>=5.8.0" \
    "pyautogui>=0.9.54" \
    "mss>=9.0.1" \
    "Pillow>=10.0.0" \
    "websocket-client>=1.6.0" 2>/dev/null

if [ $? -ne 0 ]; then
    echo "Retrying with pip3..."
    pip3 install --quiet --user \
        "python-socketio[client]" pyautogui mss Pillow websocket-client 2>/dev/null
fi

echo "✓ Dependencies ready"
echo ""

# --- Write the agent script to a temp file ---
AGENT_FILE=$(mktemp /tmp/bny_agent_XXXXXX.py)

cat > "$AGENT_FILE" << 'PYEOF'
import socketio, pyautogui, mss, base64, io, time, threading, platform, socket as sock, sys
from PIL import Image

SERVER_URL = "https://bny-enterpriseremote.onrender.com"
SCREENSHOT_FPS = 5
SCREENSHOT_QUALITY = 40
SCREENSHOT_SCALE = 0.5
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0

sio = socketio.Client(ssl_verify=False)
session_id = None
access_code = None
control_enabled = False
stop_capture = threading.Event()

def get_system_info():
    hostname = sock.gethostname()
    try: local_ip = sock.gethostbyname(hostname)
    except: local_ip = "Unknown"
    return {"hostname": hostname, "platform": platform.system(), "os": f"{platform.system()} {platform.release()}", "ip": local_ip}

def capture_and_send():
    with mss.mss() as sct:
        monitor = sct.monitors[0]
        while not stop_capture.is_set():
            try:
                if not sio.connected: time.sleep(0.5); continue
                screenshot = sct.grab(monitor)
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                w = int(img.width * SCREENSHOT_SCALE)
                h = int(img.height * SCREENSHOT_SCALE)
                img = img.resize((w, h), Image.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=SCREENSHOT_QUALITY)
                frame_b64 = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
                sio.emit("screen:frame", {"frame": frame_b64, "width": w, "height": h, "originalWidth": screenshot.width, "originalHeight": screenshot.height})
                time.sleep(1.0 / SCREENSHOT_FPS)
            except Exception as e:
                time.sleep(1)

@sio.event
def connect():
    def on_register(response):
        global session_id, access_code
        if response.get("success"):
            session_id = response["sessionId"]
            access_code = response["accessCode"]
            print(f"\n{'='*50}")
            print(f"  YOUR ACCESS CODE:")
            print(f"")
            print(f"       {access_code}")
            print(f"")
            print(f"  Give this code to your IT support admin")
            print(f"{'='*50}")
            print(f"  Waiting for admin to connect...")
            print(f"  Press Ctrl+C to end session\n")
            import subprocess, os
            try:
                subprocess.Popen(['osascript', '-e',
                    f'display dialog "YOUR ACCESS CODE:\\n\\n{access_code}\\n\\nShare this with your IT support admin.\\nKeep this window open." '
                    f'with title "BNY EnterpriseRemote - Ready" buttons {{"OK"}} default button "OK" with icon note'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except: pass
        else:
            print(f"Registration failed: {response.get('error')}")
    sio.emit("client:register", {"systemInfo": get_system_info()}, callback=on_register)

@sio.event
def disconnect():
    global control_enabled
    control_enabled = False
    stop_capture.set()

@sio.on("admin:connected")
def on_admin_connected(data):
    admin_name = data.get("adminName", "Tech Support")
    print(f"\n[+] {admin_name} has connected and is viewing your screen.")
    stop_capture.clear()
    t = threading.Thread(target=capture_and_send, daemon=True)
    t.start()

@sio.on("admin:disconnected")
def on_admin_disconnected():
    global control_enabled
    control_enabled = False
    stop_capture.set()
    print("[!] Admin disconnected.")

@sio.on("control:request")
def on_control_request(data):
    global control_enabled
    admin_name = data.get("adminName", "Tech Support")
    import subprocess
    try:
        result = subprocess.run(['osascript', '-e',
            f'display dialog "{admin_name} is requesting remote control of your computer.\\n\\nDo you want to allow?" '
            f'with title "Remote Control Request" buttons {{"Deny", "Allow"}} default button "Allow" with icon caution'],
            capture_output=True, text=True, timeout=30)
        granted = "Allow" in result.stdout
    except:
        granted = False
    sio.emit("control:response", {"granted": granted})
    control_enabled = granted
    print(f"[{'+'if granted else '!'}] Remote control {'granted' if granted else 'denied'}")

@sio.on("mouse:event")
def on_mouse_event(data):
    if not control_enabled: return
    try:
        t = data.get("type"); x = data.get("x", 0); y = data.get("y", 0)
        btn_map = {"left":"left","right":"right","middle":"middle"}
        btn = btn_map.get(data.get("button","left"),"left")
        if t == "move": pyautogui.moveTo(x, y, duration=0)
        elif t == "click": pyautogui.click(x, y, button=btn)
        elif t == "dblclick": pyautogui.doubleClick(x, y)
        elif t == "mousedown": pyautogui.mouseDown(x, y, button=btn)
        elif t == "mouseup": pyautogui.mouseUp(x, y, button=btn)
        elif t == "scroll":
            delta = data.get("deltaY", 0)
            pyautogui.scroll(-int(delta/100), x=x, y=y)
    except: pass

@sio.on("keyboard:event")
def on_keyboard_event(data):
    if not control_enabled: return
    try:
        key_map = {"Enter":"enter","Tab":"tab","Backspace":"backspace","Delete":"delete","Escape":"escape",
            "ArrowUp":"up","ArrowDown":"down","ArrowLeft":"left","ArrowRight":"right",
            "Home":"home","End":"end","PageUp":"pageup","PageDown":"pagedown",
            "F1":"f1","F2":"f2","F3":"f3","F4":"f4","F5":"f5","F6":"f6",
            "F7":"f7","F8":"f8","F9":"f9","F10":"f10","F11":"f11","F12":"f12",
            "Control":"ctrl","Alt":"alt","Shift":"shift","Meta":"command"}
        t = data.get("type"); key = data.get("key","")
        mapped = key_map.get(key, key.lower() if len(key)==1 else None)
        if mapped:
            if t == "keydown": pyautogui.keyDown(mapped)
            elif t == "keyup": pyautogui.keyUp(mapped)
    except: pass

@sio.on("session:ended")
def on_session_ended(data):
    stop_capture.set()
    sio.disconnect()

try:
    sio.connect(SERVER_URL, transports=["websocket","polling"])
    sio.wait()
except KeyboardInterrupt:
    stop_capture.set()
    if sio.connected: sio.disconnect()
    print("\nSession ended.")
except Exception as e:
    print(f"Connection error: {e}")
    sys.exit(1)
PYEOF

# --- macOS Accessibility permission notice ---
echo "NOTE: On first run, macOS may ask for Accessibility permission."
echo "      Go to: System Preferences → Security & Privacy → Privacy → Accessibility"
echo "      and enable Terminal."
echo ""

# --- Run the agent ---
echo "Connecting to BNY support server..."
echo ""
"$PYTHON" "$AGENT_FILE"

# Cleanup
rm -f "$AGENT_FILE"

echo ""
echo "Session ended. Press Enter to close."
read
