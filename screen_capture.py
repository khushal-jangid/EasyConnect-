"""
EasyConnect v2.0 - High-Speed Multi-Monitor Screen Capture, Coordinate Mapper & 60 FPS WebRTC Engine
"""
import io
import time
import base64
import asyncio
import fractions
from typing import List, Dict, Any, Optional
import cv2
import numpy as np
from PIL import Image, ImageDraw

import config

try:
    import av
    from aiortc import VideoStreamTrack
    from aiortc.mediastreams import MediaStreamError
    HAS_WEBRTC = True
except ImportError:
    VideoStreamTrack = object
    MediaStreamError = Exception
    HAS_WEBRTC = False


class ScreenCapture:
    """Ultra-fast multi-monitor screen capture engine with dynamic coordinate mapping."""

    def __init__(self):
        self.selected_monitor_id = 1
        self.use_mss = True
        try:
            import mss
            self.sct = mss.mss()
        except Exception:
            self.use_mss = False
            self.sct = None

    def get_monitors_list(self) -> List[Dict[str, Any]]:
        """Detect and return all connected display monitors."""
        monitors = []
        if self.use_mss and self.sct:
            try:
                raw_monitors = self.sct.monitors[1:] if len(self.sct.monitors) > 1 else self.sct.monitors
                for idx, m in enumerate(raw_monitors, start=1):
                    is_primary = (m.get("left") == 0 and m.get("top") == 0) or idx == 1
                    monitors.append({
                        "id": idx,
                        "name": f"Monitor {idx}" + (" (Primary)" if is_primary else ""),
                        "width": m["width"],
                        "height": m["height"],
                        "left": m["left"],
                        "top": m["top"],
                        "is_primary": is_primary,
                        "is_active": idx == self.selected_monitor_id,
                    })
                return monitors
            except Exception:
                pass

        monitors.append({
            "id": 1,
            "name": "Primary Display",
            "width": 1920,
            "height": 1080,
            "left": 0,
            "top": 0,
            "is_primary": True,
            "is_active": True,
        })
        return monitors

    def get_screen_size(self) -> tuple[int, int]:
        """Get primary display dimensions (width, height)."""
        info = self.get_active_monitor_info()
        return info.get("width", 1920), info.get("height", 1080)

    def select_monitor(self, monitor_id: int) -> bool:
        """Select active monitor index for screen streaming."""
        monitors = self.get_monitors_list()
        for m in monitors:
            if m["id"] == monitor_id:
                self.selected_monitor_id = monitor_id
                return True
        return False

    def get_active_monitor_info(self) -> Dict[str, Any]:
        """Get geometry and details of currently selected monitor."""
        monitors = self.get_monitors_list()
        for m in monitors:
            if m["id"] == self.selected_monitor_id:
                return m
        return monitors[0] if monitors else {"width": 1920, "height": 1080, "left": 0, "top": 0}

    def map_relative_to_screen(self, rel_x: float, rel_y: float, monitor_id: Optional[int] = None) -> tuple[int, int]:
        """Map normalized [0..1] touch coordinates on selected monitor to absolute screen pixel coordinates."""
        m_id = monitor_id or self.selected_monitor_id
        monitors = self.get_monitors_list()
        target = next((m for m in monitors if m["id"] == m_id), monitors[0])

        abs_x = int(target["left"] + (rel_x * target["width"]))
        abs_y = int(target["top"] + (rel_y * target["height"]))
        return abs_x, abs_y

    def capture_frame_bytes(self, quality: int = config.SCREEN_JPEG_QUALITY, max_width: int = 1280, monitor_id: Optional[int] = None) -> bytes:
        """Capture selected monitor, downscale for low-latency streaming, and compress to JPEG."""
        target_id = monitor_id or self.selected_monitor_id
        frame_bgr = None

        if self.use_mss and self.sct:
            try:
                raw_monitors = self.sct.monitors[1:] if len(self.sct.monitors) > 1 else self.sct.monitors
                idx = min(max(0, target_id - 1), len(raw_monitors) - 1)
                mon = raw_monitors[idx]
                raw = self.sct.grab(mon)
                arr = np.frombuffer(raw.raw, dtype=np.uint8).reshape((raw.height, raw.width, 4))
                frame_bgr = cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)
            except Exception:
                frame_bgr = None

        if frame_bgr is not None:
            if frame_bgr.shape[1] > max_width:
                aspect = frame_bgr.shape[0] / frame_bgr.shape[1]
                new_h = int(max_width * aspect)
                frame_bgr = cv2.resize(frame_bgr, (max_width, new_h), interpolation=cv2.INTER_LINEAR)
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
            _, encimg = cv2.imencode(".jpg", frame_bgr, encode_param)
            return encimg.tobytes()

        # PIL Fallback
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab()
        except Exception:
            img = Image.new("RGB", (1280, 720), color=(15, 23, 42))
            draw = ImageDraw.Draw(img)
            draw.text((480, 340), f"Display {target_id} Locked or Idle", fill=(0, 242, 254))

        if img.width > max_width:
            aspect = img.height / img.width
            new_height = int(max_width * aspect)
            img = img.resize((max_width, new_height), Image.Resampling.BILINEAR)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=False)
        return buf.getvalue()

    def capture_frame_base64(self, quality: int = config.SCREEN_JPEG_QUALITY, max_width: int = 1280, monitor_id: Optional[int] = None) -> str:
        """Capture frame and return base64 encoded data URL."""
        jpeg_bytes = self.capture_frame_bytes(quality=quality, max_width=max_width, monitor_id=monitor_id)
        encoded = base64.b64encode(jpeg_bytes).decode("ascii")
        return f"data:image/jpeg;base64,{encoded}"


# Global screen instance
screen = ScreenCapture()


class ScreenStreamTrack(VideoStreamTrack):
    """Real-time 60 FPS hardware-accelerated screen stream track for WebRTC."""
    kind = "video"

    def __init__(self, fps: int = 60, max_width: int = 1280):
        super().__init__()
        self.fps = fps
        self.max_width = max_width
        self._step = int((1.0 / fps) * 90000)
        self._timestamp = 0
        self._start_time = None
        self._last_frame_bgr = None

    async def recv(self):
        if self.readyState != "live":
            raise MediaStreamError

        if self._start_time is None:
            self._start_time = time.time()
            self._timestamp = 0
        else:
            self._timestamp += self._step
            target_time = self._start_time + (self._timestamp / 90000)
            wait = target_time - time.time()
            if wait > 0:
                await asyncio.sleep(wait)

        frame_bgr = None
        target_id = screen.selected_monitor_id
        if screen.use_mss and screen.sct:
            try:
                raw_monitors = screen.sct.monitors[1:] if len(screen.sct.monitors) > 1 else screen.sct.monitors
                idx = min(max(0, target_id - 1), len(raw_monitors) - 1)
                mon = raw_monitors[idx]
                raw = screen.sct.grab(mon)
                arr = np.frombuffer(raw.raw, dtype=np.uint8).reshape((raw.height, raw.width, 4))
                frame_bgr = cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)
                if frame_bgr.shape[1] > self.max_width:
                    aspect = frame_bgr.shape[0] / frame_bgr.shape[1]
                    new_h = int(self.max_width * aspect)
                    frame_bgr = cv2.resize(frame_bgr, (self.max_width, new_h), interpolation=cv2.INTER_LINEAR)
            except Exception:
                frame_bgr = None

        if frame_bgr is None:
            if self._last_frame_bgr is not None:
                frame_bgr = self._last_frame_bgr
            else:
                frame_bgr = np.zeros((720, 1280, 3), dtype=np.uint8)
        else:
            self._last_frame_bgr = frame_bgr

        frame = av.VideoFrame.from_ndarray(frame_bgr, format="bgr24")
        frame.pts = self._timestamp
        frame.time_base = fractions.Fraction(1, 90000)
        return frame
