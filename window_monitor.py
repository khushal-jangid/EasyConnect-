"""
EasyConnect v2.0 - Window Monitor & Per-App Screen Streaming Engine
Enumerates active taskbar application windows and captures individual app frames.
"""
import io
import sys
import time
import base64
import ctypes
from ctypes import wintypes
from typing import List, Dict, Any, Optional
from PIL import Image, ImageDraw
import psutil
import config
from activity_log import audit_log

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
dwmapi = ctypes.windll.dwmapi

# Constants
DWMWA_CLOAKED = 14
DWMWA_EXTENDED_FRAME_BOUNDS = 9
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
SW_RESTORE = 9
SW_MINIMIZE = 6
SW_MAXIMIZE = 3
WM_CLOSE = 0x0010

class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ('biSize', wintypes.DWORD),
        ('biWidth', wintypes.LONG),
        ('biHeight', wintypes.LONG),
        ('biPlanes', wintypes.WORD),
        ('biBitCount', wintypes.WORD),
        ('biCompression', wintypes.DWORD),
        ('biSizeImage', wintypes.DWORD),
        ('biXPelsPerMeter', wintypes.LONG),
        ('biYPelsPerMeter', wintypes.LONG),
        ('biClrUsed', wintypes.DWORD),
        ('biClrImportant', wintypes.DWORD)
    ]

class WindowMonitor:
    """Manages active taskbar window enumeration, focusing, and per-app live video capture."""

    def __init__(self):
        self._ensure_desktop_access()

    def _ensure_desktop_access(self):
        """Ensure current thread is attached to the interactive user desktop."""
        try:
            hwinsta = user32.OpenWindowStationW("WinSta0", False, 0x037F)
            if hwinsta:
                user32.SetProcessWindowStation(hwinsta)
            hdesk = user32.OpenDesktopW("Default", 0, False, 0x01FF)
            if hdesk:
                user32.SetThreadDesktop(hdesk)
        except Exception:
            pass

    def get_open_windows(self) -> List[Dict[str, Any]]:
        """List all active, visible taskbar application windows."""
        self._ensure_desktop_access()
        windows = []

        # Known icon emojis for popular applications
        icon_map = {
            "chrome.exe": "🌐",
            "msedge.exe": "🌐",
            "firefox.exe": "🦊",
            "code.exe": "💻",
            "notepad.exe": "📝",
            "explorer.exe": "📁",
            "taskmgr.exe": "⚡",
            "windowsterminal.exe": "⌨️",
            "powershell.exe": "⌨️",
            "cmd.exe": "⌨️",
            "spotify.exe": "🎵",
            "music.ui.exe": "🎵",
            "applemusic.exe": "🎵",
            "discord.exe": "💬",
            "slack.exe": "💬",
            "telegram.exe": "✈️",
            "vlc.exe": "🎬",
            "steam.exe": "🎮",
            "calc.exe": "🔢",
            "calculatorapp.exe": "🔢",
            "systemsettings.exe": "⚙️",
        }

        def enum_windows_proc(hwnd, lParam):
            is_visible = bool(user32.IsWindowVisible(hwnd))
            is_minimized = bool(user32.IsIconic(hwnd))
            
            # Must be either visible on desktop or minimized in taskbar
            if not is_visible and not is_minimized:
                return True

            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return True

            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value.strip()
            if not title:
                return True

            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_APPWINDOW = 0x00040000

            # Ignore tool windows (overlays, floating toolbars) unless explicitly app window
            if (ex_style & WS_EX_TOOLWINDOW) and not (ex_style & WS_EX_APPWINDOW):
                return True

            # Ignore child/owned dialogs unless explicitly app window
            owner = user32.GetWindow(hwnd, 4)  # GW_OWNER = 4
            if owner != 0 and not (ex_style & WS_EX_APPWINDOW):
                return True

            # Ignore cloaked windows (suspended UWP background apps / hidden virtual desktops)
            # But do NOT ignore if minimized, as Windows often marks minimized windows cloaked
            cloaked = ctypes.c_int(0)
            try:
                dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
                if cloaked.value != 0 and not is_minimized:
                    return True
            except Exception:
                pass

            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            w = rect.right - rect.left
            h = rect.bottom - rect.top

            # If not minimized, skip tiny non-app helper windows
            if not is_minimized and (w < 80 or h < 50):
                return True

            # Get process details
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            proc_name = "Application"
            try:
                proc = psutil.Process(pid.value)
                proc_name = proc.name()
            except Exception:
                pass

            # Ignore shell and background system components
            ignore_titles = (
                "Program Manager",
                "Taskbar",
                "Windows Input Experience",
                "DWM Notification Window",
                "Default IME",
                "MSCTFIME UI",
            )
            if title in ignore_titles:
                return True
            if proc_name.lower() == "explorer.exe" and title in ("Program Manager", "", "Taskbar"):
                return True

            icon = icon_map.get(proc_name.lower(), "🪟")

            windows.append({
                "hwnd": hwnd,
                "title": title,
                "process": proc_name,
                "process_name": proc_name,
                "pid": pid.value,
                "icon": icon,
                "is_minimized": is_minimized,
                "width": w,
                "height": h,
                "x": rect.left,
                "y": rect.top,
            })
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(WNDENUMPROC(enum_windows_proc), 0)
        return windows

    def capture_window_image(self, hwnd: int, max_width: int = 960) -> Optional[Image.Image]:
        """Capture the screen of a specific application window."""
        self._ensure_desktop_access()
        if not user32.IsWindow(hwnd):
            return None

        rect = wintypes.RECT()
        res = dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(rect), ctypes.sizeof(rect))
        if res != 0 or (rect.right - rect.left <= 0):
            user32.GetWindowRect(hwnd, ctypes.byref(rect))

        w = rect.right - rect.left
        h = rect.bottom - rect.top
        if w <= 10 or h <= 10:
            return None

        hwnd_dc = user32.GetWindowDC(hwnd)
        if not hwnd_dc:
            return None

        mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)
        bitmap = gdi32.CreateCompatibleBitmap(hwnd_dc, w, h)
        old_bmp = gdi32.SelectObject(mem_dc, bitmap)

        # PrintWindow PW_RENDERFULLCONTENT = 2 (Win 8.1+) with fallback to 0
        printed = user32.PrintWindow(hwnd, mem_dc, 2)
        if not printed:
            printed = user32.PrintWindow(hwnd, mem_dc, 0)

        header = BITMAPINFOHEADER()
        header.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        header.biWidth = w
        header.biHeight = -h  # top-down bitmap
        header.biPlanes = 1
        header.biBitCount = 32
        header.biCompression = 0

        buffer = ctypes.create_string_buffer(w * h * 4)
        gdi32.GetDIBits(mem_dc, bitmap, 0, h, buffer, ctypes.byref(header), 0)

        # Clean GDI objects
        gdi32.SelectObject(mem_dc, old_bmp)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(hwnd, hwnd_dc)

        try:
            img = Image.frombuffer("RGBA", (w, h), buffer, "raw", "BGRA", 0, 1)
            img = img.convert("RGB")
        except Exception:
            return None

        # Check if PrintWindow returned a fully black screen (some Direct3D/Hardware-accel windows)
        # If so, fall back to crop from desktop screen
        extrema = img.getextrema()
        if all(e == (0, 0) for e in extrema):
            try:
                from screen_capture import screen
                desktop_img = screen.capture_frame_bytes(quality=80, max_width=1920)
                # Crop region if window is on primary monitor
                desktop_pil = Image.open(io.BytesIO(desktop_img))
                crop_box = (
                    max(0, rect.left),
                    max(0, rect.top),
                    min(desktop_pil.width, rect.right),
                    min(desktop_pil.height, rect.bottom),
                )
                if crop_box[2] > crop_box[0] and crop_box[3] > crop_box[1]:
                    img = desktop_pil.crop(crop_box)
            except Exception:
                pass

        if img and img.width > max_width:
            aspect = img.height / img.width
            new_h = int(max_width * aspect)
            img = img.resize((max_width, new_h), Image.Resampling.BILINEAR)

        return img

    def capture_window_base64(self, hwnd: int, quality: int = 65, max_width: int = 960) -> str:
        """Capture window screen and return base64 data URL."""
        img = self.capture_window_image(hwnd, max_width=max_width)
        if not img:
            # Fallback placeholder card for minimized or protected windows
            img = Image.new("RGB", (640, 360), color=(15, 23, 42))
            draw = ImageDraw.Draw(img)
            title = ""
            try:
                length = user32.GetWindowTextLengthW(hwnd)
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value.strip()
            except Exception:
                pass

            is_min = bool(user32.IsIconic(hwnd))
            header_text = "💤 MINIMIZED IN TASKBAR" if is_min else "🪟 ACTIVE WINDOW"

            draw.rectangle([(15, 15), (625, 345)], outline=(59, 130, 246), width=2)
            draw.text((35, 50), header_text, fill=(56, 189, 248))
            if title:
                draw.text((35, 120), title[:45], fill=(255, 255, 255))
            draw.text((35, 250), "Tap '⚡ Focus' or '▶ Stream' to bring window to front", fill=(148, 163, 184))

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{b64}"

    def get_windows_with_thumbnails(self, max_thumb_width: int = 360) -> List[Dict[str, Any]]:
        """Fetch all taskbar windows with quick preview thumbnail snapshots."""
        windows = self.get_open_windows()
        result = []
        for w in windows:
            thumb_b64 = self.capture_window_base64(w["hwnd"], quality=50, max_width=max_thumb_width)
            w["thumbnail"] = thumb_b64
            result.append(w)
        return result

    def focus_window(self, hwnd: int, client_name: str = "Device") -> bool:
        """Bring window to front and activate focus on PC."""
        self._ensure_desktop_access()
        if not user32.IsWindow(hwnd):
            return False
        try:
            user32.ShowWindow(hwnd, SW_RESTORE)
            user32.SetForegroundWindow(hwnd)
            audit_log.log("WINDOW_FOCUS", f"Brought window HWND={hwnd} to foreground", client_name)
            return True
        except Exception:
            return False

    def minimize_window(self, hwnd: int, client_name: str = "Device") -> bool:
        """Minimize window to taskbar."""
        self._ensure_desktop_access()
        if not user32.IsWindow(hwnd):
            return False
        try:
            user32.ShowWindow(hwnd, SW_MINIMIZE)
            audit_log.log("WINDOW_MINIMIZE", f"Minimized window HWND={hwnd}", client_name)
            return True
        except Exception:
            return False

    def maximize_window(self, hwnd: int, client_name: str = "Device") -> bool:
        """Maximize or restore window."""
        self._ensure_desktop_access()
        if not user32.IsWindow(hwnd):
            return False
        try:
            user32.ShowWindow(hwnd, SW_MAXIMIZE)
            audit_log.log("WINDOW_MAXIMIZE", f"Maximized window HWND={hwnd}", client_name)
            return True
        except Exception:
            return False

    def close_window(self, hwnd: int, client_name: str = "Device") -> bool:
        """Safely send WM_CLOSE to terminate application window."""
        self._ensure_desktop_access()
        if not user32.IsWindow(hwnd):
            return False
        try:
            user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
            audit_log.log("WINDOW_CLOSE", f"Sent WM_CLOSE to window HWND={hwnd}", client_name)
            return True
        except Exception:
            return False

# Global instance
window_monitor = WindowMonitor()

# Module-level convenience functions
get_open_windows = window_monitor.get_open_windows
capture_window_image = window_monitor.capture_window_image
capture_window_base64 = window_monitor.capture_window_base64
get_windows_with_thumbnails = window_monitor.get_windows_with_thumbnails
focus_window = window_monitor.focus_window
minimize_window = window_monitor.minimize_window
maximize_window = window_monitor.maximize_window
close_window = window_monitor.close_window
