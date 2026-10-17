"""
EasyConnect v2.0 - Configuration & Security Policies
"""
import sys
import os
import uuid
import platform
from pathlib import Path

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent

DEVICE_ID_FILE = BASE_DIR / ".device_id"
PAIRED_DEVICES_FILE = BASE_DIR / ".paired_devices.json"
CUSTOM_REMOTES_FILE = BASE_DIR / ".custom_remotes.json"

def get_or_create_device_id() -> str:
    """Retrieve existing unique device ID or generate and persist a new one."""
    if DEVICE_ID_FILE.exists():
        try:
            device_id = DEVICE_ID_FILE.read_text(encoding="utf-8").strip()
            if device_id:
                return device_id
        except Exception:
            pass
    
    device_id = f"pc-{uuid.uuid4().hex[:12]}"
    try:
        DEVICE_ID_FILE.write_text(device_id, encoding="utf-8")
    except Exception:
        pass
    return device_id

# Server Settings
HOST = "0.0.0.0"
PORT = 8000
SERVER_NAME = "EasyConnect Agent v2.1"
APP_VERSION = "2.1.0"
GITHUB_REPO = "khushal-jangid/pulse-remote-pc"

# Device Information
DEVICE_ID = get_or_create_device_id()
DEVICE_NAME = platform.node() or "Windows-PC"
DEVICE_OS = f"{platform.system()} {platform.release()}"

# Security & Pairing Settings
PAIRING_TOKEN_LIFESPAN = 300  # 5 minutes in seconds
SESSION_TIMEOUT = 86400 * 30  # 30 days for persistent paired devices
MAX_ACTIVE_SESSIONS = 10

# Granular Permission Policy Defaults
DEFAULT_PERMISSIONS = {
    "mouse": True,
    "keyboard": True,
    "screen": True,
    "webcam": True,
    "files": True,
    "clipboard": True,
    "media": True,
    "app_launcher": True,
    "power_lock": True,
    "power_restart": False,
    "power_shutdown": False,
}

# Allowlisted Applications for Quick Actions (Security Hardened - No Arbitrary Execution)
ALLOWLISTED_APPS = {
    "chrome": {
        "name": "Google Chrome",
        "icon": "🌐",
        "command": ["cmd.exe", "/c", "start", "chrome"],
    },
    "vscode": {
        "name": "VS Code",
        "icon": "💻",
        "command": ["cmd.exe", "/c", "code"],
    },
    "explorer": {
        "name": "File Explorer",
        "icon": "📁",
        "command": ["explorer.exe"],
    },
    "notepad": {
        "name": "Notepad",
        "icon": "📝",
        "command": ["notepad.exe"],
    },
    "downloads": {
        "name": "Downloads Folder",
        "icon": "⬇️",
        "command": ["explorer.exe", "shell:Downloads"],
    },
    "taskmgr": {
        "name": "Task Manager",
        "icon": "📊",
        "command": ["taskmgr.exe"],
    },
    "terminal": {
        "name": "Windows Terminal / PowerShell",
        "icon": "⌨️",
        "command": ["powershell.exe"],
    },
    "calc": {
        "name": "Calculator",
        "icon": "🔢",
        "command": ["calc.exe"],
    },
    "settings": {
        "name": "Windows Settings",
        "icon": "⚙️",
        "command": ["cmd.exe", "/c", "start", "ms-settings:"],
    },
}

# Screen & Camera Capture Settings
SCREEN_JPEG_QUALITY = 55      # 1-100 quality for screen streaming
SCREEN_MAX_FPS = 30           # Target FPS for screen mirroring
WEBCAM_JPEG_QUALITY = 50      # Webcam stream JPEG quality

# File Manager Settings
MAX_UPLOAD_SIZE = 500 * 1024 * 1024  # 500 MB max file transfer
ALLOWED_ROOTS = [
    str(Path.home() / "Desktop"),
    str(Path.home() / "Downloads"),
    str(Path.home() / "Documents"),
    str(Path.home() / "Pictures"),
    str(Path.home() / "Videos"),
    str(Path.home() / "Music"),
    str(Path.home()),
    "C:\\",
]
