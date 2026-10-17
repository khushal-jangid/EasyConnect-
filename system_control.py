"""
EasyConnect v2.0 - System Metrics, Allowlisted App Launcher & Find My PC Engine
"""
import os
import sys
import time
import ctypes
import platform
import threading
import subprocess
import psutil
import config
from activity_log import audit_log

class SystemController:
    """Provides comprehensive system diagnostics, power management, app launching & Find My PC alarm."""

    def __init__(self):
        self._last_net_time = time.time()
        self._last_net_io = psutil.net_io_counters()
        self._upload_speed_kbps = 0.0
        self._download_speed_kbps = 0.0
        
        # Find My PC Alarm State
        self._find_pc_active = False
        self._find_pc_thread = None
        self._find_pc_window = None

        # Guard Mode State (CCTV Intruder Alert)
        self._guard_mode_active = False
        self._guard_thread = None
        self._last_intruder_info = None
        self._on_intruder_callback = None

        # Anti-Theft Sentry Mode State (Cafe & Library Security Hub)
        self._sentry_active = False
        self._sentry_ringing = False
        self._sentry_armed_at = 0
        self._sentry_grace_seconds = 10
        self._sentry_thread = None
        self._sentry_siren_thread = None
        self._sentry_callback = None
        self._sentry_initial_plugged = True
        self._sentry_flash_window = None
        self._sentry_flash_proc = None
        self._sentry_stop_event = threading.Event()
        self._sentry_status_listener = None
        self._last_sentry_alert = None

        # Walk-Away Auto-Lock State
        self._walkaway_lock_enabled = False

        # Brightness Cache
        self._cached_brightness = 100
        self._brightness_initialized = False

    def get_system_stats(self) -> dict:
        """Fetch live CPU, RAM, Disk, Network I/O, Battery, and hardware metrics."""
        now = time.time()
        elapsed = max(0.1, now - self._last_net_time)
        cur_net_io = psutil.net_io_counters()

        # Calculate network throughput in KB/s
        sent_delta = cur_net_io.bytes_sent - self._last_net_io.bytes_sent
        recv_delta = cur_net_io.bytes_recv - self._last_net_io.bytes_recv
        self._upload_speed_kbps = round((sent_delta / elapsed) / 1024, 1)
        self._download_speed_kbps = round((recv_delta / elapsed) / 1024, 1)
        self._last_net_time = now
        self._last_net_io = cur_net_io

        cpu_usage = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        
        disk_path = "C:\\" if sys.platform == "win32" else "/"
        try:
            disk = psutil.disk_usage(disk_path)
            disk_info = {
                "total_gb": round(disk.total / (1024 ** 3), 1),
                "used_gb": round(disk.used / (1024 ** 3), 1),
                "free_gb": round(disk.free / (1024 ** 3), 1),
                "percent": disk.percent,
            }
        except Exception:
            disk_info = {"total_gb": 0, "used_gb": 0, "free_gb": 0, "percent": 0}

        battery_info = None
        try:
            bat = psutil.sensors_battery()
            if bat:
                battery_info = {
                    "percent": int(bat.percent),
                    "power_plugged": bool(bat.power_plugged),
                    "secsleft": bat.secsleft if bat.secsleft != psutil.POWER_TIME_UNLIMITED else None,
                }
        except Exception:
            pass

        # CPU info
        cpu_freq = psutil.cpu_freq()
        freq_mhz = round(cpu_freq.current, 0) if cpu_freq else 0

        # Initial brightness query
        if not self._brightness_initialized:
            self.get_brightness()
            self._brightness_initialized = True

        return {
            "device_name": config.DEVICE_NAME,
            "os": config.DEVICE_OS,
            "cpu_model": platform.processor() or "Multi-Core Processor",
            "cpu_percent": cpu_usage,
            "cpu_cores": psutil.cpu_count(logical=True),
            "cpu_freq_mhz": freq_mhz,
            "memory": {
                "total_gb": round(mem.total / (1024 ** 3), 1),
                "used_gb": round(mem.used / (1024 ** 3), 1),
                "free_gb": round(mem.available / (1024 ** 3), 1),
                "percent": mem.percent,
            },
            "disk": disk_info,
            "network": {
                "upload_kbps": self._upload_speed_kbps,
                "download_kbps": self._download_speed_kbps,
            },
            "battery": battery_info,
            "brightness": self._cached_brightness,
            "guard_mode_active": self._guard_mode_active,
            "walkaway_lock_enabled": self._walkaway_lock_enabled,
            "last_intruder": self._last_intruder_info,
            "uptime_seconds": int(time.time() - psutil.boot_time()),
            "find_pc_active": self._find_pc_active,
        }

    def launch_allowlisted_app(self, app_key: str, client_name: str = "Device") -> dict:
        """Launch an application from the predefined security allowlist."""
        app_key = app_key.lower().strip()
        app_entry = config.ALLOWLISTED_APPS.get(app_key)
        
        if not app_entry:
            return {"success": False, "message": f"App '{app_key}' is not in the security allowlist."}

        try:
            cmd = app_entry["command"]
            subprocess.Popen(cmd, shell=False)
            audit_log.log("APP_LAUNCH", f"Launched {app_entry['name']}", client_name)
            return {"success": True, "message": f"Launched {app_entry['name']}"}
        except Exception as e:
            return {"success": False, "message": f"Failed to launch {app_entry['name']}: {str(e)}"}

    def get_allowlisted_apps_list(self) -> list:
        """Get list of predefined quick actions for mobile UI."""
        return [
            {"key": k, "name": v["name"], "icon": v["icon"]}
            for k, v in config.ALLOWLISTED_APPS.items()
        ]

    def execute_power_action(self, action: str, client_name: str = "Device") -> dict:
        """Execute system power action with audit logging."""
        act = action.lower().strip()
        
        if act == "lock":
            if sys.platform == "win32":
                ctypes.windll.user32.LockWorkStation()
                audit_log.log("PC_LOCKED", "Emergency Lock triggered from mobile", client_name)
                return {"success": True, "message": "PC Locked Successfully"}
            return {"success": False, "message": "Lock only supported on Windows"}
            
        elif act == "sleep":
            if sys.platform == "win32":
                audit_log.log("PC_SLEEP", "Sleep mode triggered from mobile", client_name)
                subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
                return {"success": True, "message": "Entering Sleep Mode..."}
            return {"success": False, "message": "Sleep only supported on Windows"}
            
        elif act == "restart":
            if sys.platform == "win32":
                audit_log.log("PC_RESTART", "System restart requested", client_name)
                subprocess.Popen(["shutdown", "/r", "/t", "5"])
                return {"success": True, "message": "Restarting PC in 5 seconds..."}
            return {"success": False, "message": "Unsupported on this OS"}
            
        elif act == "shutdown":
            if sys.platform == "win32":
                audit_log.log("PC_SHUTDOWN", "System shutdown requested", client_name)
                subprocess.Popen(["shutdown", "/s", "/t", "5"])
                return {"success": True, "message": "Shutting down PC in 5 seconds..."}
            return {"success": False, "message": "Unsupported on this OS"}
            
        return {"success": False, "message": f"Unknown action: {action}"}

    # Find My PC Audio & Notification Engine
    def start_find_pc(self, client_name: str = "Device") -> dict:
        """Start playing an audible sound alert on PC and show visible screen banner."""
        if self._find_pc_active:
            return {"success": True, "message": "Find My PC is already ringing!"}

        self._find_pc_active = True
        audit_log.log("FIND_MY_PC", f"Find My PC sound triggered by {client_name}", client_name)

        def sound_loop():
            try:
                import winsound
                while self._find_pc_active:
                    winsound.Beep(1200, 250)
                    time.sleep(0.05)
                    winsound.Beep(1800, 350)
                    time.sleep(0.3)
            except Exception:
                pass

        self._find_pc_thread = threading.Thread(target=sound_loop, daemon=True)
        self._find_pc_thread.start()
        return {"success": True, "message": "🔊 PC sound is playing"}

    def is_find_pc_active(self) -> bool:
        """Check if Find My PC alarm is currently ringing."""
        return self._find_pc_active

    def stop_find_pc(self, client_name: str = "Device") -> dict:
        """Stop Find My PC alert sound."""
        self._find_pc_active = False
        audit_log.log("FIND_MY_PC_STOPPED", f"Find My PC sound stopped by {client_name}", client_name)
        return {"success": True, "message": "Find My PC sound stopped"}

    # --- Screen Brightness Controls ---
    def get_brightness(self) -> int:
        """Query current display brightness level (0-100%)."""
        if sys.platform != "win32":
            return 100
        try:
            res = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command", "(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness).CurrentBrightness"],
                text=True, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                timeout=2
            ).strip()
            if res:
                self._cached_brightness = int(res)
        except Exception:
            pass
        return self._cached_brightness

    def set_brightness(self, level: int) -> bool:
        """Set display brightness level (0-100%)."""
        if sys.platform != "win32":
            return False
        level = max(0, min(100, int(level)))
        self._cached_brightness = level
        try:
            cmd = f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1, {level})"
            subprocess.Popen(
                ["powershell", "-NoProfile", "-Command", cmd],
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )
            return True
        except Exception:
            return False

    # --- Panic / Boss Key Mode (Anti-Spy) ---
    def trigger_panic_mode(self, client_name: str = "Device") -> dict:
        """1-Tap Boss Key: Minimizes all windows to desktop and mutes master audio."""
        try:
            import pyautogui
            # Minimize all windows
            pyautogui.hotkey('win', 'd')
            # Mute master volume
            pyautogui.press('volumemute')
            audit_log.log("PANIC_MODE", "🚨 Boss Key triggered: Desktop revealed & audio muted", client_name)
            return {"success": True, "message": "🚨 Boss Mode Engaged: Screen hidden & audio muted!"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    # --- CCTV Stealth PC Guard Engine ---
    def start_guard_mode(self, on_intruder_callback=None, client_name: str = "Device") -> dict:
        """Activate CCTV Stealth PC Guard mode."""
        if self._guard_mode_active:
            return {"success": True, "active": True, "message": "Guard Mode is already ACTIVE"}

        self._guard_mode_active = True
        self._on_intruder_callback = on_intruder_callback
        audit_log.log("GUARD_MODE_ON", "CCTV Stealth PC Guard activated", client_name)

        def guard_worker():
            try:
                import pyautogui
                from webcam_capture import webcam
                last_pos = pyautogui.position()
                last_alert_time = 0

                while self._guard_mode_active:
                    time.sleep(0.4)
                    cur_pos = pyautogui.position()
                    dx = abs(cur_pos.x - last_pos.x)
                    dy = abs(cur_pos.y - last_pos.y)
                    now = time.time()

                    # Trigger alert on significant physical mouse movement
                    if (dx > 18 or dy > 18) and (now - last_alert_time > 6):
                        last_alert_time = now
                        last_pos = cur_pos
                        photo_b64 = webcam.capture_snapshot_base64(quality=70)
                        timestr = time.strftime("%Y-%m-%d %H:%M:%S")
                        self._last_intruder_info = {
                            "time": timestr,
                            "photo": photo_b64,
                            "reason": f"PC Mouse moved ({dx}px, {dy}px)"
                        }
                        audit_log.log("INTRUDER_DETECTED", "Stealth camera captured intruder on PC movement!", "Guard Engine")
                        if self._on_intruder_callback:
                            self._on_intruder_callback(self._last_intruder_info)
                    else:
                        last_pos = cur_pos
            except Exception as e:
                print(f"[Guard] Worker error: {e}")

        self._guard_thread = threading.Thread(target=guard_worker, daemon=True)
        self._guard_thread.start()
        return {"success": True, "active": True, "message": "🛡️ CCTV PC Guard is now ACTIVE!"}

    def stop_guard_mode(self, client_name: str = "Device") -> dict:
        """Deactivate CCTV Stealth PC Guard mode."""
        self._guard_mode_active = False
        try:
            from webcam_capture import webcam
            webcam.release()
        except Exception:
            pass
        audit_log.log("GUARD_MODE_OFF", "CCTV Stealth PC Guard deactivated", client_name)
        return {"success": True, "active": False, "message": "🛡️ CCTV PC Guard deactivated"}

    def is_guard_mode_active(self) -> bool:
        return self._guard_mode_active

    def get_last_intruder(self) -> dict:
        return self._last_intruder_info or {}

    # --- Walk-Away Proximity Auto-Lock ---
    def set_walkaway_lock(self, enabled: bool, client_name: str = "Device") -> dict:
        self._walkaway_lock_enabled = enabled
        status_txt = "ENABLED" if enabled else "DISABLED"
        audit_log.log("WALKAWAY_LOCK", f"Walk-Away Auto-Lock set to {status_txt}", client_name)
        return {"success": True, "enabled": self._walkaway_lock_enabled}

    def is_walkaway_lock_enabled(self) -> bool:
        return self._walkaway_lock_enabled

    # --- 🚨 Cafe & Library Anti-Theft Sentry Engine ---
    def arm_sentry(self, on_sentry_callback=None, client_name: str = "Device", grace_seconds: int = 10) -> dict:
        """Arm the Anti-Theft Sentry with grace period and multi-sensor monitoring."""
        if self._sentry_active and not self._sentry_ringing:
            return {
                "success": True,
                "active": True,
                "ringing": False,
                "message": "Sentry Mode is already ARMED"
            }

        # Reset any prior alert state cleanly
        self.disarm_sentry("Internal Re-Arm")

        self._sentry_active = True
        self._sentry_ringing = False
        self._sentry_stop_event = threading.Event()
        self._sentry_callback = on_sentry_callback
        self._sentry_grace_seconds = max(3, int(grace_seconds))
        self._sentry_armed_at = time.time() + self._sentry_grace_seconds

        # Detect initial power state
        try:
            bat = psutil.sensors_battery()
            self._sentry_initial_plugged = bat.power_plugged if bat else True
        except Exception:
            self._sentry_initial_plugged = True

        audit_log.log("SENTRY_ARMED", f"Anti-Theft Sentry ARMED with {self._sentry_grace_seconds}s grace period", client_name)

        def sentry_worker():
            try:
                import pyautogui
                from webcam_capture import webcam
                
                # Wait for grace period countdown to complete
                while self._sentry_active and time.time() < self._sentry_armed_at:
                    if self._sentry_stop_event.is_set():
                        return
                    time.sleep(0.2)

                if not self._sentry_active or self._sentry_stop_event.is_set():
                    return

                # Record baseline positions once armed
                last_pos = pyautogui.position()
                audit_log.log("SENTRY_ACTIVE", "Anti-Theft Sentry is now fully monitoring laptop sensors", "Sentry Engine")
                self._notify_status_listener()

                while self._sentry_active and not self._sentry_ringing:
                    if self._sentry_stop_event.is_set():
                        break
                    time.sleep(0.3)
                    if not self._sentry_active:
                        break

                    # 1. Tripwire: Charger Unplugged Check
                    try:
                        bat = psutil.sensors_battery()
                        if bat is not None and self._sentry_initial_plugged and not bat.power_plugged:
                            self.trigger_sentry_alarm(
                                reason="🔌 Charger cable was unplugged / disconnected!",
                                client_name="Sentry Power Monitor"
                            )
                            break
                    except Exception:
                        pass

                    # 2. Tripwire: Physical Mouse / Touchpad Motion Check
                    cur_pos = pyautogui.position()
                    dx = abs(cur_pos.x - last_pos.x)
                    dy = abs(cur_pos.y - last_pos.y)
                    if dx > 25 or dy > 25:
                        self.trigger_sentry_alarm(
                            reason=f"🖱️ Laptop / Touchpad moved ({dx}px, {dy}px)!",
                            client_name="Sentry Motion Sensor"
                        )
                        break
                    last_pos = cur_pos

            except Exception as e:
                print(f"[Sentry Worker Error]: {e}")

        self._sentry_thread = threading.Thread(target=sentry_worker, daemon=True)
        self._sentry_thread.start()

        return {
            "success": True,
            "active": True,
            "grace_seconds": self._sentry_grace_seconds,
            "initial_plugged": self._sentry_initial_plugged,
            "message": f"🚨 Sentry Mode Armed! ({self._sentry_grace_seconds}s countdown)"
        }

    def trigger_sentry_alarm(self, reason: str = "Physical tripwire triggered", client_name: str = "Sentry Engine"):
        """Trigger full alarm: Force volume 100%, police siren loop, visual screen lockdown, stealth webcam photo."""
        if not self._sentry_active or self._sentry_ringing:
            return

        self._sentry_ringing = True
        self._sentry_stop_event.clear()
        audit_log.log("SENTRY_TRIGGERED", f"🚨 THEFT ALARM TRIGGERED: {reason}", client_name)

        # 1. Force Max Volume quickly (non-blocking)
        self._force_max_volume()

        # 2. Stealth Webcam Snapshot (quick capture)
        photo_b64 = None
        try:
            from webcam_capture import webcam
            photo_b64 = webcam.capture_snapshot_base64(quality=50)
        except Exception as e:
            print(f"[Sentry Photo Error]: {e}")

        timestr = time.strftime("%Y-%m-%d %I:%M:%S %p")
        self._last_sentry_alert = {
            "time": timestr,
            "photo": photo_b64,
            "reason": reason,
            "status": "triggered"
        }

        # 3. Notify Phone via Callback
        if self._sentry_callback:
            try:
                self._sentry_callback(self._last_sentry_alert)
            except Exception as e:
                print(f"[Sentry Callback Error]: {e}")

        # 4. Start Police Siren Audio Loop (fast response to stop event)
        def siren_player():
            try:
                import winsound
                while self._sentry_ringing and not self._sentry_stop_event.is_set():
                    # Check if PC flash screen was closed by user pressing ESC / Space on PC
                    if hasattr(self, "_sentry_flash_proc") and self._sentry_flash_proc and self._sentry_flash_proc.poll() is not None:
                        self.disarm_sentry("PC Screen Key (Esc/Space)")
                        break
                    for freq in (950, 1550):
                        if self._sentry_stop_event.is_set() or not self._sentry_ringing:
                            break
                        winsound.Beep(freq, 220)
                        time.sleep(0.04)
            except Exception as e:
                print(f"[Sentry Siren Audio Error]: {e}")

        self._sentry_siren_thread = threading.Thread(target=siren_player, daemon=True)
        self._sentry_siren_thread.start()

        # 5. Visual Screen Flash Banner on PC (Separate Subprocess: 100% non-blocking & isolated)
        self._launch_flash_screen(reason)

    def _launch_flash_screen(self, reason: str):
        """Launch isolated Tkinter warning screen in detached subprocess."""
        try:
            screen_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sentry_screen.py")
            if os.path.exists(screen_script):
                self._sentry_flash_proc = subprocess.Popen(
                    [sys.executable, screen_script, reason],
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                )
        except Exception as e:
            print(f"[Sentry Screen Subprocess Error]: {e}")

    def disarm_sentry(self, client_name: str = "Device") -> dict:
        """Disarm the Sentry Mode and silence any active alarm instantly."""
        was_ringing = self._sentry_ringing
        self._sentry_active = False
        self._sentry_ringing = False
        if hasattr(self, "_sentry_stop_event"):
            self._sentry_stop_event.set()

        # Terminate flashing subprocess immediately
        if hasattr(self, "_sentry_flash_proc") and self._sentry_flash_proc:
            try:
                self._sentry_flash_proc.terminate()
                self._sentry_flash_proc.kill()
            except Exception:
                pass
            self._sentry_flash_proc = None

        try:
            from webcam_capture import webcam
            webcam.release()
        except Exception:
            pass

        audit_log.log("SENTRY_DISARMED", "Anti-Theft Sentry DISARMED and alarm silenced", client_name)
        self._notify_status_listener()
        return {
            "success": True,
            "active": False,
            "ringing": False,
            "was_ringing": was_ringing,
            "message": "🟢 Anti-Theft Sentry DISARMED & Alarm Silenced!"
        }

    def _force_max_volume(self):
        """Quickly maximize Windows Master Volume without blocking."""
        try:
            if sys.platform == "win32":
                VK_VOLUME_UP = 0xAF
                user32 = ctypes.windll.user32
                for _ in range(25):
                    user32.keybd_event(VK_VOLUME_UP, 0, 0, 0)
                    user32.keybd_event(VK_VOLUME_UP, 0, 2, 0)
            else:
                import pyautogui
                for _ in range(8):
                    pyautogui.press('volumeup', _pause=False)
        except Exception:
            pass

    def is_sentry_active(self) -> bool:
        return self._sentry_active

    def is_sentry_ringing(self) -> bool:
        return self._sentry_ringing

    @property
    def sentry_armed(self) -> bool:
        return self._sentry_active

    @property
    def sentry_ringing(self) -> bool:
        return self._sentry_ringing

    def set_sentry_status_listener(self, listener):
        self._sentry_status_listener = listener

    def _notify_status_listener(self):
        if self._sentry_status_listener:
            try:
                self._sentry_status_listener()
            except Exception as e:
                print(f"[Sentry Listener Error]: {e}")

    def get_security_settings(self) -> dict:
        return {
            "guard_active": self._guard_mode_active,
            "walkaway_enabled": self._walkaway_lock_enabled,
            "sentry": self.get_sentry_status(),
            "last_intruder": self._last_intruder_info or {}
        }

    def get_sentry_status(self) -> dict:
        now = time.time()
        is_grace = self._sentry_active and (now < self._sentry_armed_at)
        remaining_grace = max(0, int(self._sentry_armed_at - now)) if is_grace else 0
        return {
            "active": self._sentry_active,
            "ringing": self._sentry_ringing,
            "is_grace": is_grace,
            "grace_remaining": remaining_grace,
            "initial_plugged": self._sentry_initial_plugged,
            "last_alert": self._last_sentry_alert or {}
        }

# Global instance
system = SystemController()
