#!/usr/bin/env python3
"""
Enterprise Remote Support - Client Agent
Runs on the remote machine to enable remote support.

Similar to BeyondTrust/Bomgar client agent.
"""

import asyncio
import json
import sys
import os
import platform
import socket
import io
import base64
from datetime import datetime

try:
    import socketio
    from PIL import Image
    import mss
    import pyautogui
except ImportError:
    print("Installing required packages...")
    os.system(f"{sys.executable} -m pip install python-socketio[client] Pillow mss pyautogui aiohttp")
    import socketio
    from PIL import Image
    import mss
    import pyautogui

# Configuration - Can be set via environment or command line
SERVER_URL = os.environ.get('SERVER_URL', 'http://localhost:3000')
SCREEN_QUALITY = int(os.environ.get('SCREEN_QUALITY', 40))
SCREEN_SCALE = float(os.environ.get('SCREEN_SCALE', 0.5))
FRAME_RATE = int(os.environ.get('FRAME_RATE', 10))

# For cross-network: Set SERVER_URL to your public server
# Example: SERVER_URL=https://your-server.com python3 client.py
# Or: python3 client.py https://your-server.com

class RemoteSupportClient:
    def __init__(self, server_url=SERVER_URL):
        self.server_url = server_url
        self.sio = socketio.AsyncClient()
        self.client_id = None
        self.session_id = None
        self.access_code = None
        self.admin_connected = False
        self.control_enabled = False
        self.streaming = False
        self.screen = mss.mss()
        
        self._setup_handlers()
    
    def _setup_handlers(self):
        @self.sio.event
        async def connect():
            print(f"✓ Connected to server: {self.server_url}")
            await self._register()
        
        @self.sio.event
        async def disconnect():
            print("✗ Disconnected from server")
            self.streaming = False
        
        @self.sio.on('admin:connected')
        async def on_admin_connected(data):
            admin_name = data.get('adminName', 'Admin')
            print(f"\n✓ Admin connected: {admin_name}")
            print("  Starting screen streaming...")
            self.admin_connected = True
            self.streaming = True
            asyncio.create_task(self._stream_screen())
        
        @self.sio.on('admin:disconnected')
        async def on_admin_disconnected():
            print("\n✗ Admin disconnected")
            self.admin_connected = False
            self.streaming = False
            self.control_enabled = False
        
        @self.sio.on('control:request')
        async def on_control_request(data):
            admin_name = data.get('adminName', 'Admin')
            print(f"\n⚡ Control requested by: {admin_name}")
            # Auto-grant for demo (in production, show UI prompt)
            self.control_enabled = True
            await self.sio.emit('control:response', {'granted': True})
            print("  Control GRANTED")
        
        @self.sio.on('mouse:event')
        async def on_mouse_event(data):
            if not self.control_enabled:
                return
            await self._handle_mouse(data)
        
        @self.sio.on('keyboard:event')
        async def on_keyboard_event(data):
            if not self.control_enabled:
                return
            await self._handle_keyboard(data)
        
        @self.sio.on('chat:message')
        async def on_chat_message(data):
            sender = data.get('senderName', 'Admin')
            text = data.get('text', '')
            print(f"\n💬 [{sender}]: {text}")
        
        @self.sio.on('session:ended')
        async def on_session_ended(data):
            reason = data.get('reason', 'Session ended')
            print(f"\n⏹️  Session ended: {reason}")
            self.streaming = False
            self.admin_connected = False
    
    async def _register(self):
        """Register client with server"""
        system_info = {
            'hostname': socket.gethostname(),
            'platform': platform.system(),
            'os': f"{platform.system()} {platform.release()}",
            'machine': platform.machine(),
            'python': platform.python_version()
        }
        
        def callback(response):
            if response.get('success'):
                self.client_id = response['clientId']
                self.session_id = response['sessionId']
                self.access_code = response['accessCode']
                
                print(f"\n{'='*50}")
                print(f"  CLIENT REGISTERED SUCCESSFULLY")
                print(f"{'='*50}")
                print(f"  Client ID:   {self.client_id}")
                print(f"  Session ID:  {self.session_id[:16]}...")
                print(f"\n  ╔═══════════════════════════════════╗")
                print(f"  ║  ACCESS CODE: {self.access_code:^8}         ║")
                print(f"  ╚═══════════════════════════════════╝")
                print(f"\n  Share this code with tech support")
                print(f"{'='*50}\n")
            else:
                print(f"✗ Registration failed: {response.get('error')}")
        
        await self.sio.emit('client:register', {'systemInfo': system_info}, callback=callback)
    
    async def _stream_screen(self):
        """Capture and stream screen frames"""
        monitor = self.screen.monitors[1]  # Primary monitor
        
        while self.streaming and self.admin_connected:
            try:
                # Capture screen
                screenshot = self.screen.grab(monitor)
                img = Image.frombytes('RGB', screenshot.size, screenshot.bgra, 'raw', 'BGRX')
                
                # Scale down
                new_size = (int(img.width * SCREEN_SCALE), int(img.height * SCREEN_SCALE))
                img = img.resize(new_size, Image.LANCZOS)
                
                # Compress to JPEG
                buffer = io.BytesIO()
                img.save(buffer, format='JPEG', quality=SCREEN_QUALITY)
                frame_data = base64.b64encode(buffer.getvalue()).decode('utf-8')
                
                # Send frame
                await self.sio.emit('screen:frame', {
                    'frame': f'data:image/jpeg;base64,{frame_data}',
                    'width': img.width,
                    'height': img.height,
                    'timestamp': datetime.now().isoformat()
                })
                
                await asyncio.sleep(1.0 / FRAME_RATE)
                
            except Exception as e:
                print(f"Stream error: {e}")
                await asyncio.sleep(1)
    
    async def _handle_mouse(self, data):
        """Handle remote mouse events"""
        try:
            event_type = data.get('type')
            x = data.get('x', 0)
            y = data.get('y', 0)
            
            # Scale coordinates back to actual screen size
            screen_width, screen_height = pyautogui.size()
            x = int(x / SCREEN_SCALE)
            y = int(y / SCREEN_SCALE)
            
            if event_type == 'move':
                pyautogui.moveTo(x, y, duration=0)
            elif event_type == 'click':
                button = data.get('button', 'left')
                pyautogui.click(x, y, button=button)
            elif event_type == 'doubleclick':
                pyautogui.doubleClick(x, y)
            elif event_type == 'rightclick':
                pyautogui.rightClick(x, y)
            elif event_type == 'scroll':
                amount = data.get('amount', 0)
                pyautogui.scroll(amount, x, y)
        except Exception as e:
            print(f"Mouse event error: {e}")
    
    async def _handle_keyboard(self, data):
        """Handle remote keyboard events"""
        try:
            event_type = data.get('type')
            key = data.get('key', '')
            
            if event_type == 'press':
                pyautogui.press(key)
            elif event_type == 'type':
                text = data.get('text', '')
                pyautogui.typewrite(text, interval=0.02)
            elif event_type == 'hotkey':
                keys = data.get('keys', [])
                pyautogui.hotkey(*keys)
        except Exception as e:
            print(f"Keyboard event error: {e}")
    
    async def send_chat(self, text):
        """Send chat message to admin"""
        await self.sio.emit('chat:message', {'text': text})
    
    async def run(self):
        """Main run loop"""
        print(f"""
╔═══════════════════════════════════════════════════════════╗
║     Enterprise Remote Support - Client Agent              ║
║     (Similar to BeyondTrust/Bomgar)                       ║
╠═══════════════════════════════════════════════════════════╣
║  Connecting to: {self.server_url:<41} ║
╚═══════════════════════════════════════════════════════════╝
        """)
        
        try:
            await self.sio.connect(self.server_url)
            
            # Keep running and handle user input
            while True:
                await asyncio.sleep(1)
                
        except KeyboardInterrupt:
            print("\n\nShutting down...")
        except Exception as e:
            print(f"Connection error: {e}")
        finally:
            if self.sio.connected:
                await self.sio.disconnect()


async def main():
    # Allow custom server URL via command line
    server_url = sys.argv[1] if len(sys.argv) > 1 else SERVER_URL
    
    client = RemoteSupportClient(server_url)
    await client.run()


if __name__ == '__main__':
    asyncio.run(main())
