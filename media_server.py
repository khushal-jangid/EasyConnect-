"""
EasyConnect v2.1 - High-Performance Local PC Media Server Engine
Provides media discovery, instant streaming with HTTP 206 range seeking,
automatic OpenCV video thumbnail generation, and dual 'Phone vs PC' playback.
"""
import os
import sys
import time
import json
import hashlib
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional
from PIL import Image

import config
from activity_log import audit_log

try:
    import cv2
    HAS_OPENCV = True
except ImportError:
    cv2 = None
    HAS_OPENCV = False

# Resolve Base and Cache directories
BASE_DIR = config.BASE_DIR if hasattr(config, "BASE_DIR") else Path(__file__).resolve().parent
THUMB_CACHE_DIR = BASE_DIR / ".media_thumbs"
THUMB_CACHE_DIR.mkdir(parents=True, exist_ok=True)
MEDIA_FOLDERS_FILE = BASE_DIR / ".media_folders.json"

VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".avi", ".mov", ".m4v", ".wmv", ".flv", ".ts"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".wma"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}


def format_file_size(size_bytes: int) -> str:
    """Format bytes into readable KB, MB, or GB."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


class MediaServer:
    """Local Wi-Fi PC Media Server Engine for EasyConnect."""

    def __init__(self):
        self._custom_folders: List[str] = self._load_custom_folders()

    def _load_custom_folders(self) -> List[str]:
        if MEDIA_FOLDERS_FILE.exists():
            try:
                data = json.loads(MEDIA_FOLDERS_FILE.read_text(encoding="utf-8"))
                return [d for d in data if os.path.isdir(d)]
            except Exception:
                pass
        return []

    def _save_custom_folders(self):
        try:
            MEDIA_FOLDERS_FILE.write_text(json.dumps(self._custom_folders, indent=2), encoding="utf-8")
        except Exception:
            pass

    def get_configured_folders(self) -> List[Dict[str, str]]:
        """Return all default and user-added media scan folders."""
        home = Path.home()
        standard = [
            {"name": "Videos", "path": str(home / "Videos"), "type": "video", "icon": "🎬"},
            {"name": "Music", "path": str(home / "Music"), "type": "audio", "icon": "🎵"},
            {"name": "Pictures", "path": str(home / "Pictures"), "type": "image", "icon": "🖼️"},
            {"name": "Downloads", "path": str(home / "Downloads"), "type": "all", "icon": "⬇️"},
            {"name": "Desktop", "path": str(home / "Desktop"), "type": "all", "icon": "🖥️"},
        ]
        
        valid_folders = [f for f in standard if os.path.isdir(f["path"])]
        
        for idx, cf in enumerate(self._custom_folders):
            if os.path.isdir(cf):
                valid_folders.append({
                    "name": Path(cf).name or f"Custom Folder {idx + 1}",
                    "path": cf,
                    "type": "custom",
                    "icon": "📁"
                })

        return valid_folders

    def add_custom_folder(self, folder_path: str) -> Dict[str, Any]:
        """Add a custom media folder to scan."""
        resolved = str(Path(folder_path).resolve())
        if not os.path.isdir(resolved):
            return {"success": False, "error": f"Folder not found: {folder_path}"}
        if resolved not in self._custom_folders:
            self._custom_folders.append(resolved)
            self._save_custom_folders()
        return {"success": True, "path": resolved, "name": Path(resolved).name}

    def remove_custom_folder(self, folder_path: str) -> Dict[str, Any]:
        """Remove a custom folder from media scans."""
        resolved = str(Path(folder_path).resolve())
        if resolved in self._custom_folders:
            self._custom_folders.remove(resolved)
            self._save_custom_folders()
            return {"success": True}
        return {"success": False, "error": "Folder not in configured list"}

    def scan_library(self, category: str = "all", target_path: Optional[str] = None) -> Dict[str, Any]:
        """Scan media folders and return metadata lists."""
        folders_to_scan = []
        if target_path and os.path.isdir(target_path):
            folders_to_scan = [target_path]
        else:
            folders_to_scan = [f["path"] for f in self.get_configured_folders()]

        items = []
        counts = {"video": 0, "audio": 0, "image": 0}

        for folder in folders_to_scan:
            try:
                # Scan immediate folder and 1-level subdirectories for performance
                for root, dirs, files in os.walk(folder):
                    # Prune hidden, system, and heavy development directories
                    dirs[:] = [d for d in dirs if not d.startswith((".", "$")) and d.lower() not in (
                        "node_modules", "appdata", "windows", "program files", "system volume information", "venv", ".venv", "__pycache__"
                    )]
                    rel = os.path.relpath(root, folder)
                    depth = 0 if rel == "." else rel.count(os.sep) + 1
                    if depth >= 2:
                        dirs[:] = []

                    for file in files:
                        ext = os.path.splitext(file)[1].lower()
                        media_type = None

                        if ext in VIDEO_EXTS:
                            media_type = "video"
                        elif ext in AUDIO_EXTS:
                            media_type = "audio"
                        elif ext in IMAGE_EXTS:
                            media_type = "image"

                        if not media_type:
                            continue

                        counts[media_type] += 1

                        if category != "all" and category != media_type:
                            continue

                        full_path = os.path.join(root, file)
                        try:
                            st = os.stat(full_path)
                            size_bytes = st.st_size
                            mtime = int(st.st_mtime)
                            file_id = hashlib.md5(full_path.encode("utf-8")).hexdigest()[:16]

                            items.append({
                                "id": file_id,
                                "name": file,
                                "title": os.path.splitext(file)[0],
                                "path": full_path,
                                "type": media_type,
                                "ext": ext.replace(".", "").upper(),
                                "size": size_bytes,
                                "size_formatted": format_file_size(size_bytes),
                                "mtime": mtime,
                                "folder": Path(root).name or folder,
                            })
                        except (PermissionError, OSError):
                            continue
            except (PermissionError, OSError):
                continue

        # Sort newest files first
        items.sort(key=lambda x: x["mtime"], reverse=True)

        return {
            "success": True,
            "counts": counts,
            "total": len(items),
            "items": items[:300],  # Return up to 300 items per scan for high speed
            "folders": self.get_configured_folders(),
        }

    def get_or_create_thumbnail(self, file_path: str) -> Optional[Path]:
        """Generate and cache video/image poster thumbnail on demand."""
        if not os.path.isfile(file_path):
            return None

        file_id = hashlib.md5(file_path.encode("utf-8")).hexdigest()[:16]
        thumb_path = THUMB_CACHE_DIR / f"thumb_{file_id}.jpg"

        if thumb_path.exists():
            return thumb_path

        ext = os.path.splitext(file_path)[1].lower()

        # Video Thumbnail extraction via OpenCV (Fast Frame Capture)
        if ext in VIDEO_EXTS and HAS_OPENCV:
            try:
                cap = cv2.VideoCapture(file_path)
                if cap.isOpened():
                    # Fast seek to 1.5 seconds or first frame
                    cap.set(cv2.CAP_PROP_POS_MSEC, 1500)
                    ret, frame = cap.read()
                    if not ret or frame is None:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        ret, frame = cap.read()

                    cap.release()

                    if ret and frame is not None:
                        h, w = frame.shape[:2]
                        target_w = 400
                        target_h = int((h / w) * target_w)
                        resized = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_AREA)
                        cv2.imwrite(str(thumb_path), resized, [cv2.IMWRITE_JPEG_QUALITY, 75])
                        return thumb_path
            except Exception as e:
                print(f"[MediaServer] Video thumbnail extraction error: {e}")

        # Image thumbnail via Pillow
        elif ext in IMAGE_EXTS:
            try:
                with Image.open(file_path) as im:
                    im.thumbnail((480, 480))
                    im = im.convert("RGB")
                    im.save(str(thumb_path), "JPEG", quality=80)
                    return thumb_path
            except Exception:
                pass

        return None

    def play_on_pc(self, file_path: str, client_name: str = "Smartphone") -> Dict[str, Any]:
        """Launch media file on the PC using the system's default media player."""
        if not os.path.isfile(file_path):
            return {"success": False, "error": f"File does not exist: {file_path}"}

        filename = os.path.basename(file_path)
        try:
            if sys.platform == "win32":
                os.startfile(file_path)
            else:
                opener = "open" if sys.platform == "darwin" else "xdg-open"
                subprocess.Popen([opener, file_path])

            audit_log.log("MEDIA_PLAY_PC", f"Launched '{filename}' on PC screen", client_name)
            return {"success": True, "message": f"Playing '{filename}' on PC screen", "filename": filename}
        except Exception as e:
            return {"success": False, "error": str(e)}


# Global instance
media_server = MediaServer()
