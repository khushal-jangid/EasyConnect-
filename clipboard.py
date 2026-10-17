"""
EasyConnect v2.0 - Universal Native Windows Clipboard Sync & History
"""
import sys
import time
import ctypes
from ctypes import wintypes
from typing import List
from activity_log import audit_log

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

class ClipboardManager:
    """Native Windows clipboard engine with history tracking and sync."""

    def __init__(self, max_history: int = 20):
        self.is_windows = sys.platform == "win32"
        self._history: List[str] = []
        self._max_history = max_history

        if self.is_windows:
            self.user32 = ctypes.windll.user32
            self.kernel32 = ctypes.windll.kernel32
            
            self.user32.OpenClipboard.argtypes = [wintypes.HWND]
            self.user32.OpenClipboard.restype = wintypes.BOOL
            self.user32.CloseClipboard.restype = wintypes.BOOL
            self.user32.EmptyClipboard.restype = wintypes.BOOL
            self.user32.GetClipboardData.argtypes = [wintypes.UINT]
            self.user32.GetClipboardData.restype = wintypes.HANDLE
            self.user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
            self.user32.SetClipboardData.restype = wintypes.HANDLE

            self.kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
            self.kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
            self.kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
            self.kernel32.GlobalLock.restype = ctypes.c_void_p
            self.kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
            self.kernel32.GlobalUnlock.restype = wintypes.BOOL

    def get_text(self) -> str:
        """Read plain/unicode text from the Windows clipboard and append to history."""
        if not self.is_windows:
            return ""
        
        if not self.user32.OpenClipboard(None):
            return ""
        
        text = ""
        try:
            handle = self.user32.GetClipboardData(CF_UNICODETEXT)
            if handle:
                p_data = self.kernel32.GlobalLock(handle)
                if p_data:
                    text = ctypes.c_wchar_p(p_data).value or ""
                    self.kernel32.GlobalUnlock(handle)
        finally:
            self.user32.CloseClipboard()

        if text and (not self._history or self._history[0] != text):
            self._history.insert(0, text)
            if len(self._history) > self._max_history:
                self._history.pop()

        return text

    def set_text(self, text: str, client_name: str = "Device") -> bool:
        """Write unicode text to the Windows clipboard and add to history."""
        if not self.is_windows:
            return False
        
        if not self.user32.OpenClipboard(None):
            return False
        
        success = False
        try:
            self.user32.EmptyClipboard()
            encoded = (text + "\0").encode("utf-16le")
            h_mem = self.kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))
            if h_mem:
                p_mem = self.kernel32.GlobalLock(h_mem)
                if p_mem:
                    ctypes.memmove(p_mem, encoded, len(encoded))
                    self.kernel32.GlobalUnlock(h_mem)
                    if self.user32.SetClipboardData(CF_UNICODETEXT, h_mem):
                        success = True
        finally:
            self.user32.CloseClipboard()

        if success and text:
            if not self._history or self._history[0] != text:
                self._history.insert(0, text)
                if len(self._history) > self._max_history:
                    self._history.pop()
            audit_log.log("CLIPBOARD_SYNC", f"Pasted text into PC clipboard ({len(text)} chars)", client_name)

        return success

    def get_history(self) -> List[str]:
        """Get recent clipboard history items."""
        return self._history

    def clear_clipboard(self) -> bool:
        """Empty Windows clipboard content."""
        if not self.is_windows:
            return False
        if not self.user32.OpenClipboard(None):
            return False
        try:
            self.user32.EmptyClipboard()
            return True
        finally:
            self.user32.CloseClipboard()

# Global instance
clip = ClipboardManager()
