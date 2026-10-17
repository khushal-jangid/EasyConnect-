"""
EasyConnect - High-Performance Windows Mouse Control Engine
"""
import time
import sys
import ctypes
from ctypes import wintypes

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

# Windows User32 Constants
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000
WHEEL_DELTA = 120

class MouseController:
    """Low-latency native Windows mouse controller."""

    def __init__(self):
        self.is_windows = sys.platform == "win32"
        if self.is_windows:
            self.user32 = ctypes.windll.user32
        else:
            self.user32 = None

    def get_position(self) -> tuple[int, int]:
        """Get current cursor position (x, y)."""
        if self.is_windows:
            pt = POINT()
            self.user32.GetCursorPos(ctypes.byref(pt))
            return pt.x, pt.y
        else:
            import pyautogui
            pos = pyautogui.position()
            return pos.x, pos.y

    def move(self, dx: float, dy: float, sensitivity: float = 1.0):
        """Move cursor relative to current position with sensitivity multiplier."""
        actual_dx = int(round(dx * sensitivity))
        actual_dy = int(round(dy * sensitivity))
        
        if self.is_windows:
            self.user32.mouse_event(MOUSEEVENTF_MOVE, actual_dx, actual_dy, 0, 0)
        else:
            import pyautogui
            pyautogui.moveRel(actual_dx, actual_dy, _pause=False)

    def set_position(self, x: int, y: int):
        """Set absolute cursor position."""
        if self.is_windows:
            self.user32.SetCursorPos(int(x), int(y))
        else:
            import pyautogui
            pyautogui.moveTo(int(x), int(y), _pause=False)

    def click(self, button: str = "left", double: bool = False):
        """Perform a single or double click with specified button."""
        btn = button.lower()
        if self.is_windows:
            down_flag, up_flag = MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP
            if btn == "right":
                down_flag, up_flag = MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP
            elif btn == "middle":
                down_flag, up_flag = MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP

            self.user32.mouse_event(down_flag, 0, 0, 0, 0)
            time.sleep(0.01)
            self.user32.mouse_event(up_flag, 0, 0, 0, 0)

            if double:
                time.sleep(0.05)
                self.user32.mouse_event(down_flag, 0, 0, 0, 0)
                time.sleep(0.01)
                self.user32.mouse_event(up_flag, 0, 0, 0, 0)
        else:
            import pyautogui
            clicks = 2 if double else 1
            pyautogui.click(button=btn, clicks=clicks, _pause=False)

    def mouse_down(self, button: str = "left"):
        """Hold down mouse button for drag operations."""
        btn = button.lower()
        if self.is_windows:
            flag = MOUSEEVENTF_LEFTDOWN
            if btn == "right":
                flag = MOUSEEVENTF_RIGHTDOWN
            elif btn == "middle":
                flag = MOUSEEVENTF_MIDDLEDOWN
            self.user32.mouse_event(flag, 0, 0, 0, 0)
        else:
            import pyautogui
            pyautogui.mouseDown(button=btn, _pause=False)

    def mouse_up(self, button: str = "left"):
        """Release mouse button."""
        btn = button.lower()
        if self.is_windows:
            flag = MOUSEEVENTF_LEFTUP
            if btn == "right":
                flag = MOUSEEVENTF_RIGHTUP
            elif btn == "middle":
                flag = MOUSEEVENTF_MIDDLEUP
            self.user32.mouse_event(flag, 0, 0, 0, 0)
        else:
            import pyautogui
            pyautogui.mouseUp(button=btn, _pause=False)

    def scroll(self, dy: float, dx: float = 0):
        """Scroll vertical and horizontal wheel."""
        if self.is_windows:
            if dy != 0:
                # On Windows, positive delta scrolls up, negative scrolls down
                wheel_steps = int(dy * WHEEL_DELTA)
                self.user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, wheel_steps, 0)
            if dx != 0:
                hwheel_steps = int(dx * WHEEL_DELTA)
                self.user32.mouse_event(MOUSEEVENTF_HWHEEL, 0, 0, hwheel_steps, 0)
        else:
            import pyautogui
            if dy != 0:
                pyautogui.scroll(int(dy * 50), _pause=False)
            if dx != 0:
                pyautogui.hscroll(int(dx * 50), _pause=False)

    def zoom(self, delta: float):
        """
        Perform native Windows zoom (Ctrl + Mouse Wheel).
        Positive delta = Zoom In, Negative delta = Zoom Out.
        """
        if delta == 0:
            return
        if self.is_windows:
            VK_CONTROL = 0x11
            KEYEVENTF_KEYUP = 0x0002
            scan_code = self.user32.MapVirtualKeyW(VK_CONTROL, 0)
            steps = int(delta * WHEEL_DELTA)
            if steps == 0:
                steps = WHEEL_DELTA if delta > 0 else -WHEEL_DELTA
            # Hold Ctrl
            self.user32.keybd_event(VK_CONTROL, scan_code, 0, 0)
            time.sleep(0.015)
            # Scroll wheel
            self.user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, steps, 0)
            time.sleep(0.015)
            # Release Ctrl
            self.user32.keybd_event(VK_CONTROL, scan_code, KEYEVENTF_KEYUP, 0)
        else:
            import pyautogui
            steps = int(delta * 50) or (50 if delta > 0 else -50)
            pyautogui.keyDown('ctrl')
            pyautogui.scroll(steps, _pause=False)
            pyautogui.keyUp('ctrl')

# Global instance
mouse = MouseController()

