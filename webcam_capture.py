"""
EasyConnect v2.0 - PC Webcam Video Streaming & Snapshot Engine
Includes auto-release watchdog to guarantee camera hardware LED turns OFF when not actively in use.
"""
import io
import time
import base64
import threading
from typing import List, Dict, Any, Optional
from PIL import Image, ImageDraw
import config

class WebcamCapture:
    """Live video streaming & snapshot capture from PC webcam with auto-release protection."""

    def __init__(self):
        self._lock = threading.Lock()
        self._cap = None
        self._current_cam_id = 0
        self._last_access_time = 0

        # Start auto-release watchdog thread (releases camera if idle > 2.5s)
        self._watchdog_thread = threading.Thread(target=self._idle_watchdog, daemon=True)
        self._watchdog_thread.start()

    def _idle_watchdog(self):
        """Background thread that automatically turns off webcam when no frames are requested."""
        while True:
            time.sleep(1.0)
            with self._lock:
                if self._cap is not None and (time.time() - self._last_access_time > 2.5):
                    try:
                        self._cap.release()
                    except Exception:
                        pass
                    self._cap = None

    def _get_capture(self, cam_id: int = 0):
        """Open or reuse OpenCV VideoCapture."""
        import cv2
        if self._cap is None or not self._cap.isOpened() or self._current_cam_id != cam_id:
            if self._cap is not None:
                try:
                    self._cap.release()
                except Exception:
                    pass
            self._cap = cv2.VideoCapture(cam_id, cv2.CAP_DSHOW)
            if not self._cap.isOpened():
                self._cap = cv2.VideoCapture(cam_id)
            self._current_cam_id = cam_id
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self._last_access_time = time.time()
        return self._cap

    def get_available_cameras(self) -> List[Dict[str, Any]]:
        """Probe and return list of available webcam devices."""
        cams = []
        try:
            import cv2
            for i in range(2):
                temp = cv2.VideoCapture(i, cv2.CAP_DSHOW)
                if temp.isOpened():
                    cams.append({
                        "id": i,
                        "name": f"PC Camera {i + 1}" + (" (Default)" if i == 0 else ""),
                    })
                    temp.release()
        except Exception:
            pass

        if not cams:
            cams.append({"id": 0, "name": "PC Built-in Webcam"})
        return cams

    def capture_frame_base64(self, cam_id: int = 0, quality: int = config.WEBCAM_JPEG_QUALITY) -> str:
        """Capture live frame from PC webcam for real-time video streaming."""
        with self._lock:
            self._last_access_time = time.time()
            try:
                import cv2
                cap = self._get_capture(cam_id)
                ret, frame = cap.read()
                if ret and frame is not None:
                    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
                    result, encimg = cv2.imencode(".jpg", frame, encode_param)
                    if result:
                        b64 = base64.b64encode(encimg).decode("ascii")
                        return f"data:image/jpeg;base64,{b64}"
            except Exception as e:
                print(f"[Webcam] Error: {e}")

            # Fallback if camera is disconnected or in use by another app
            img = Image.new("RGB", (640, 480), color=(15, 23, 42))
            draw = ImageDraw.Draw(img)
            draw.text((220, 230), "PC Camera Unavailable / In Use", fill=(0, 242, 254))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=50)
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            return f"data:image/jpeg;base64,{b64}"

    def capture_snapshot_base64(self, cam_id: int = 0, quality: int = 65) -> str:
        """Capture a single photo and IMMEDIATELY release camera so hardware LED turns OFF."""
        with self._lock:
            b64_res = None
            try:
                import cv2
                cap = self._get_capture(cam_id)
                # Read 2 frames so sensor auto-exposure adjusts
                for _ in range(2):
                    ret, frame = cap.read()
                if ret and frame is not None:
                    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
                    result, encimg = cv2.imencode(".jpg", frame, encode_param)
                    if result:
                        b64 = base64.b64encode(encimg).decode("ascii")
                        b64_res = f"data:image/jpeg;base64,{b64}"
            except Exception as e:
                print(f"[Webcam Snapshot Error]: {e}")
            finally:
                # Release camera immediately so camera LED never stays on
                if self._cap is not None:
                    try:
                        self._cap.release()
                    except Exception:
                        pass
                    self._cap = None

            if b64_res:
                return b64_res

            # Fallback placeholder
            img = Image.new("RGB", (640, 480), color=(15, 23, 42))
            draw = ImageDraw.Draw(img)
            draw.text((220, 230), "Intruder Detected (Camera Busy)", fill=(0, 242, 254))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=50)
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            return f"data:image/jpeg;base64,{b64}"

    def release(self):
        """Release camera resource to turn off camera LED immediately."""
        with self._lock:
            if self._cap is not None:
                try:
                    self._cap.release()
                except Exception:
                    pass
                self._cap = None

# Global instance
webcam = WebcamCapture()
