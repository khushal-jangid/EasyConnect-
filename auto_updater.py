"""
EasyConnect v2.0 - Non-Blocking Auto-Update Notification & 1-Click Updater Engine
"""
import os
import sys
import re
import json
import time
import urllib.request
import threading
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

import config
from activity_log import audit_log


def parse_version(v_str: str) -> tuple:
    """Extract integer version components from version strings like 'v2.1.0' -> (2, 1, 0)."""
    nums = re.findall(r"\d+", str(v_str))
    return tuple(map(int, nums)) if nums else (0, 0, 0)


class AutoUpdater:
    """Background update checker and 1-click executable updater."""

    def __init__(self):
        self.current_version = getattr(config, "APP_VERSION", "2.0.0")
        self.github_repo = getattr(config, "GITHUB_REPO", "khushal-jangid/pulse-remote-pc")
        self.api_url = f"https://api.github.com/repos/{self.github_repo}/releases/latest"
        
        self._update_info = {
            "has_update": False,
            "checked": False,
            "current_version": self.current_version,
            "latest_version": self.current_version,
            "release_name": "",
            "release_notes": "",
            "download_url": "",
            "html_url": f"https://github.com/{self.github_repo}/releases",
        }
        self._lock = threading.Lock()
        self._downloading = False

    def check_for_updates(self, timeout: float = 3.5) -> Dict[str, Any]:
        """Query GitHub Releases API for the latest version tag (non-blocking)."""
        req = urllib.request.Request(
            self.api_url,
            headers={
                "User-Agent": "EasyConnect-AutoUpdater/2.0",
                "Accept": "application/vnd.github.v3+json",
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    latest_tag = data.get("tag_name", "").strip()
                    current_v = parse_version(self.current_version)
                    latest_v = parse_version(latest_tag)

                    has_update = latest_v > current_v

                    # Find executable download URL in release assets
                    download_url = ""
                    for asset in data.get("assets", []):
                        if asset.get("name", "").lower().endswith(".exe"):
                            download_url = asset.get("browser_download_url", "")
                            break
                    if not download_url:
                        download_url = f"https://github.com/{self.github_repo}/releases/latest/download/EasyConnect.exe"

                    with self._lock:
                        self._update_info = {
                            "has_update": has_update,
                            "checked": True,
                            "current_version": self.current_version,
                            "latest_version": latest_tag or self.current_version,
                            "release_name": data.get("name", latest_tag),
                            "release_notes": data.get("body", "")[:600],
                            "download_url": download_url,
                            "html_url": data.get("html_url", f"https://github.com/{self.github_repo}/releases"),
                        }
                        if has_update:
                            print(f"\n\033[93m✨ [UPDATE AVAILABLE] New version {latest_tag} is ready! (Current: {self.current_version})\033[0m")
                            print(f"\033[93m👉 Download: {download_url}\033[0m\n", flush=True)
                            audit_log.log("UPDATE_AVAILABLE", f"New version {latest_tag} available", "AutoUpdater")
        except Exception:
            # Silent fallback if offline or API rate limited
            with self._lock:
                self._update_info["checked"] = True

        return self.get_update_info()

    def get_update_info(self) -> Dict[str, Any]:
        """Get cached update status dictionary."""
        with self._lock:
            return dict(self._update_info)

    def start_background_check(self):
        """Spawns an asynchronous background worker to check for updates without delaying startup."""
        thread = threading.Thread(target=self.check_for_updates, daemon=True)
        thread.start()

    def apply_update(self, download_url: Optional[str] = None) -> Dict[str, Any]:
        """Download latest executable and schedule seamless in-place replacement."""
        if self._downloading:
            return {"success": False, "message": "Update download is already in progress"}

        url = download_url or self._update_info.get("download_url")
        if not url:
            return {"success": False, "message": "No download URL available"}

        self._downloading = True

        def _do_update():
            try:
                base_dir = config.BASE_DIR
                target_exe = base_dir / "EasyConnect.exe"
                temp_exe = base_dir / "EasyConnect_update.exe"
                updater_bat = base_dir / "_apply_update.bat"

                print(f"[*] Downloading new version from {url}...")
                req = urllib.request.Request(url, headers={"User-Agent": "EasyConnect-AutoUpdater/2.0"})
                with urllib.request.urlopen(req, timeout=30) as resp, open(temp_exe, "wb") as f:
                    while True:
                        chunk = resp.read(64 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)

                print("[*] Update downloaded successfully. Spawning restart script...")
                audit_log.log("UPDATE_DOWNLOADED", "New version downloaded, restarting application", "AutoUpdater")

                # Generate self-deleting batch updater script
                bat_script = f"""@echo off
timeout /t 2 /nobreak > nul
if exist "{temp_exe}" (
    move /y "{temp_exe}" "{target_exe}" > nul
)
start "" "{target_exe}"
del "%~f0"
"""
                updater_bat.write_text(bat_script, encoding="utf-8")
                subprocess.Popen(["cmd.exe", "/c", str(updater_bat)], creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
                
                # Graceful termination to allow replacement
                time.sleep(0.5)
                os._exit(0)
            except Exception as e:
                print(f"[Update Error]: {e}")
                self._downloading = False

        thread = threading.Thread(target=_do_update, daemon=True)
        thread.start()
        return {"success": True, "message": "Downloading update in background. PC agent will restart automatically."}


# Global auto-updater instance
auto_updater = AutoUpdater()
