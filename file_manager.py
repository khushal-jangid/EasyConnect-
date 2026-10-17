"""
EasyConnect - Secure File Explorer, Download & Upload
"""
import os
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
import config

class FileManager:
    """Safe file system operations for remote browsing and transfers."""

    def get_quick_folders(self) -> List[Dict[str, str]]:
        """Get standard Windows user directories."""
        home = Path.home()
        folders = [
            {"name": "Desktop", "path": str(home / "Desktop")},
            {"name": "Downloads", "path": str(home / "Downloads")},
            {"name": "Documents", "path": str(home / "Documents")},
            {"name": "Pictures", "path": str(home / "Pictures")},
            {"name": "Videos", "path": str(home / "Videos")},
            {"name": "Home Directory", "path": str(home)},
        ]
        return [f for f in folders if os.path.exists(f["path"])]

    def list_directory(self, target_path: Optional[str] = None) -> Dict[str, Any]:
        """List files and folders within a given directory."""
        if not target_path or not os.path.exists(target_path):
            target_path = str(Path.home() / "Desktop")
            if not os.path.exists(target_path):
                target_path = str(Path.home())

        target = Path(target_path).resolve()
        
        items: List[Dict[str, Any]] = []
        try:
            with os.scandir(target) as it:
                for entry in it:
                    try:
                        stat = entry.stat()
                        is_dir = entry.is_dir()
                        ext = os.path.splitext(entry.name)[1].lower().replace(".", "") if not is_dir else ""
                        
                        items.append({
                            "name": entry.name,
                            "path": entry.path,
                            "is_dir": is_dir,
                            "size": stat.st_size if not is_dir else 0,
                            "modified": int(stat.st_mtime),
                            "ext": ext,
                        })
                    except (PermissionError, OSError):
                        continue
        except PermissionError:
            return {"error": "Permission denied", "path": str(target), "items": []}
        except Exception as e:
            return {"error": str(e), "path": str(target), "items": []}

        # Sort: directories first, then alphabetically
        items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))

        parent_path = str(target.parent) if target.parent != target else None

        return {
            "current_path": str(target),
            "parent_path": parent_path,
            "items": items,
            "quick_folders": self.get_quick_folders(),
        }

    def save_uploaded_file(self, destination_dir: str, filename: str, file_data: bytes) -> Dict[str, Any]:
        """Save an uploaded file from mobile to the destination directory."""
        dest = Path(destination_dir).resolve()
        if not dest.exists():
            dest = Path.home() / "Downloads"
            dest.mkdir(parents=True, exist_ok=True)

        safe_filename = os.path.basename(filename)
        target_file = dest / safe_filename

        # Prevent overwriting by appending timestamp if file exists
        if target_file.exists():
            stem = target_file.stem
            suffix = target_file.suffix
            target_file = dest / f"{stem}_{int(time.time())}{suffix}"

        with open(target_file, "wb") as f:
            f.write(file_data)

        return {
            "success": True,
            "filename": target_file.name,
            "path": str(target_file),
            "size": len(file_data),
        }

# Global instance
files = FileManager()
