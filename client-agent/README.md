# BNY EnterpriseRemote - Native Client Agent

This Python agent runs on the **client machine** and enables real mouse/keyboard remote control.

## Why use this instead of the browser client?

The browser client (`client.html`) can only **share the screen** — it cannot receive mouse/keyboard control because browsers have no access to OS-level input.

This Python agent uses `pyautogui` to actually move the mouse and simulate keystrokes on the client machine.

## Installation

```bash
cd client-agent
pip3 install -r requirements.txt
```

### macOS additional steps:
1. Go to **System Preferences → Security & Privacy → Privacy**
2. Enable **Accessibility** for Terminal (or your Python app)
3. Enable **Screen Recording** for Terminal

## Running

```bash
python3 agent.py
```

The agent will print an **Access Code** — give this to your admin.

## Requirements

- Python 3.8+
- Internet access (connects to `https://bny-enterpriseremote.onrender.com`)
