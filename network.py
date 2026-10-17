"""
EasyConnect v2.0 - High-Performance Async Network Server & Secure Protocol Engine
"""
import os
import sys
import time
import json
import asyncio
from pathlib import Path
from aiohttp import web, WSMsgType

import config
from authentication import auth_manager
from mouse_control import mouse
from keyboard_control import keyboard
from screen_capture import screen
from webcam_capture import webcam
from clipboard import clip
from file_manager import files
from system_control import system
from window_monitor import window_monitor
from activity_log import audit_log
from auto_updater import auto_updater

# Resolve asset directories for dev & PyInstaller bundles
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    _base = Path(sys._MEIPASS)
    _exe_parent = Path(sys.executable).resolve().parent
    STATIC_DIR = (_base / "static") if (_base / "static").exists() else (_exe_parent / "static")
    DOCS_DIR = (_base / "docs") if (_base / "docs").exists() else (_exe_parent / "docs")
else:
    STATIC_DIR = Path(__file__).resolve().parent / "static"
    DOCS_DIR = Path(__file__).resolve().parent / "docs"

GESTURE_MAP = {
    "task_view": "win+tab", "show_desktop": "win+d", "alt_tab": "alt+tab",
    "alt_shift_tab": "alt+shift+tab", "search": "win+s", "action_center": "win+a",
    "desktop_next": "ctrl+win+right", "desktop_prev": "ctrl+win+left",
}

POWER_PERMS = {
    "lock": "power_lock", "sleep": "power_lock",
    "restart": "power_restart", "shutdown": "power_shutdown",
}


class NetworkServer:
    """Asynchronous HTTP and WebSocket server for EasyConnect v2.0."""

    def __init__(self, on_device_connected=None, on_device_disconnected=None):
        self.app = web.Application(client_max_size=config.MAX_UPLOAD_SIZE)
        self.runner = None
        self.site = None
        self.active_ws_connections = set()
        self.on_device_connected = on_device_connected
        self.on_device_disconnected = on_device_disconnected
        self._last_client_ping = time.time()
        self._client_had_ping = False
        self._watchdog_task = None
        self._active_peer_connections = set()
        self._setup_routes()

    def _setup_routes(self):
        """Register REST APIs, static files, and download routes."""
        self.app.router.add_post("/api/pair", self.handle_pair)
        self.app.router.add_get("/api/status", self.handle_status)
        self.app.router.add_get("/api/files/download", self.handle_file_download)
        self.app.router.add_post("/api/files/upload", self.handle_file_upload)
        self.app.router.add_get("/api/security/logs", self.handle_security_logs)
        self.app.router.add_get("/ws", self.handle_websocket)

        # Web Client
        self.app.router.add_get("/", self.handle_index)
        self.app.router.add_static("/static", path=str(STATIC_DIR), name="static")

        # Official Download / Landing Page
        if DOCS_DIR.exists():
            self.app.router.add_get("/download", self.handle_download_page)
            self.app.router.add_get("/download/", self.handle_download_page)
            self.app.router.add_get("/download/style.css", self._serve_docs_asset("style.css"))
            self.app.router.add_get("/download/script.js", self._serve_docs_asset("script.js"))
            self.app.router.add_static("/docs", path=str(DOCS_DIR), name="docs")

    def _serve_docs_asset(self, filename: str):
        async def handler(request):
            f = DOCS_DIR / filename
            return web.FileResponse(f) if f.exists() else web.Response(status=404)
        return handler

    async def handle_download_page(self, request):
        docs_file = DOCS_DIR / "index.html"
        if docs_file.exists():
            return web.FileResponse(docs_file, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
        return web.Response(text="EasyConnect Download page loading...", content_type="text/html")

    async def handle_index(self, request):
        index_file = STATIC_DIR / "index.html"
        if index_file.exists():
            return web.FileResponse(index_file, headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"})
        return web.Response(text="EasyConnect Web Client starting...", content_type="text/html")

    async def handle_status(self, request):
        return web.json_response({
            "status": "online", "version": config.APP_VERSION,
            "device_id": config.DEVICE_ID, "device_name": config.DEVICE_NAME,
            "os": config.DEVICE_OS, "active_sessions": len(auth_manager.get_active_sessions()),
            "update": auto_updater.get_update_info(),
        })

    async def handle_security_logs(self, request):
        token = request.headers.get("X-Session-Token") or request.query.get("token")
        if not auth_manager.validate_session(token):
            return web.json_response({"error": "Unauthorized"}, status=401)
        return web.json_response({"logs": audit_log.get_logs()})

    async def handle_pair(self, request):
        try:
            data = await request.json()
            token = data.get("pairing_token")
            if not token:
                return web.json_response({"error": "Missing pairing_token"}, status=400)

            client_info = {"device_id": data.get("device_id", "phone"), "name": data.get("name", "Smartphone"), "ip": request.remote}
            session_token = auth_manager.validate_and_consume_pairing_token(token, client_info)
            if not session_token:
                return web.json_response({"error": "Invalid or expired pairing token"}, status=401)

            if self.on_device_connected:
                self.on_device_connected(client_info)

            return web.json_response({
                "success": True, "session_token": session_token,
                "device_id": config.DEVICE_ID, "device_name": config.DEVICE_NAME,
                "permissions": auth_manager.validate_session(session_token).get("permissions", {}),
            })
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_file_download(self, request):
        token = request.query.get("token")
        if not auth_manager.check_permission(token, "files"):
            return web.Response(text="Unauthorized / Permission Denied", status=403)

        file_path = request.query.get("path")
        if not file_path or not os.path.exists(file_path) or not os.path.isfile(file_path):
            return web.Response(text="File not found", status=404)

        session_info = auth_manager.validate_session(token)
        audit_log.log("FILE_DOWNLOAD", f"Downloaded '{os.path.basename(file_path)}'", session_info.get("client_name", "Device") if session_info else "Device")
        return web.FileResponse(file_path)

    async def handle_file_upload(self, request):
        token = request.headers.get("X-Session-Token") or request.query.get("token")
        if not auth_manager.check_permission(token, "files"):
            return web.json_response({"error": "Permission Denied: File transfers disabled for this device."}, status=403)

        reader = await request.multipart()
        field = await reader.next()
        dest_dir = request.query.get("dir") or str(Path.home() / "Downloads")

        if field and field.filename:
            file_data = await field.read()
            res = files.save_uploaded_file(dest_dir, field.filename, file_data)
            session_info = auth_manager.validate_session(token)
            audit_log.log("FILE_UPLOAD", f"Uploaded '{res['filename']}' ({res['size']} bytes)", session_info.get("client_name", "Device") if session_info else "Device")
            return web.json_response(res)

        return web.json_response({"error": "No file uploaded"}, status=400)

    def broadcast_event(self, event: str, data: dict):
        """Thread-safe event broadcast to all active WebSocket clients."""
        if not hasattr(self, "loop") or self.loop is None:
            return
        for conn in list(self.active_ws_connections):
            if not conn.closed:
                try:
                    asyncio.run_coroutine_threadsafe(conn.send_json({"event": event, "data": data}), self.loop)
                except Exception:
                    pass

    async def _require_perm(self, ws, token: str, perm: str) -> bool:
        """Check device permission and send failure event if denied."""
        if not auth_manager.check_permission(token, perm):
            asyncio.create_task(ws.send_json({
                "event": "permission_denied",
                "data": {"permission": perm, "message": f"Action '{perm}' is disabled for this device."}
            }))
            return False
        return True

    async def handle_websocket(self, request):
        """Real-time bidirectional WebSocket handler with clean event routing."""
        ws = web.WebSocketResponse(heartbeat=25.0, max_msg_size=16 * 1024 * 1024)
        await ws.prepare(request)
        self.active_ws_connections.add(ws)

        authenticated = False
        session_token = None
        client_name = "Phone"

        try:
            async for msg in ws:
                if msg.type != WSMsgType.TEXT:
                    continue
                try:
                    data = json.loads(msg.data)
                    event = data.get("event")
                    payload = data.get("data", {})

                    # Authentication Handshake
                    if event == "auth":
                        session_token = payload.get("session_token")
                        session_info = auth_manager.validate_session(session_token)
                        if session_info:
                            authenticated = True
                            client_name = session_info.get("client_name", "Phone")
                            audit_log.log("DEVICE_CONNECTED", f"Device '{client_name}' connected", client_name, request.remote)
                            await ws.send_json({
                                "event": "auth_success",
                                "data": {
                                    "device_name": config.DEVICE_NAME,
                                    "device_id": config.DEVICE_ID,
                                    "permissions": session_info.get("permissions", {}),
                                }
                            })
                            await ws.send_json({"event": "sentry:status", "data": system.get_sentry_status()})
                            await ws.send_json({"event": "security:settings", "data": system.get_security_settings()})
                            await ws.send_json({"event": "system:update_info", "data": auto_updater.get_update_info()})
                            if self.on_device_connected:
                                self.on_device_connected(client_name)
                        else:
                            await ws.send_json({"event": "auth_error", "data": {"error": "Invalid session token"}})
                            await ws.close()
                            break
                        continue

                    if not authenticated:
                        await ws.send_json({"event": "auth_required", "data": {}})
                        continue

                    # Dispatch command
                    await self._dispatch_event(ws, event, payload, client_name, session_token)

                except Exception as cmd_err:
                    print(f"[WS Command Error]: {cmd_err}")
        finally:
            self.active_ws_connections.discard(ws)
            webcam.release()
            for pc in list(self._active_peer_connections):
                try:
                    asyncio.create_task(pc.close())
                except Exception:
                    pass
            self._active_peer_connections.clear()
            active_live = [c for c in self.active_ws_connections if not c.closed]
            if authenticated:
                audit_log.log("DEVICE_DISCONNECTED", f"Device '{client_name}' disconnected", client_name)
            if self.on_device_disconnected and not active_live:
                self.on_device_disconnected()
            if not active_live and system.is_walkaway_lock_enabled():
                print("[Security] Walk-Away Auto-Lock triggered: Device disconnected!", flush=True)
                system.execute_power_action("lock", "WalkAway_AutoLock")

        return ws

    async def _dispatch_event(self, ws, event: str, payload: dict, client_name: str, session_token: str):
        """Clean modular dispatcher: all commands mapped in compact, extensible blocks."""
        # 1. Mouse & Touchpad Gestures
        if event == "mouse:move":
            if await self._require_perm(ws, session_token, "mouse"):
                mouse.move(payload.get("dx", 0), payload.get("dy", 0), payload.get("sensitivity", 1.0))

        elif event == "mouse:click":
            if await self._require_perm(ws, session_token, "mouse"):
                mouse.click(payload.get("button", "left"), payload.get("double", False))

        elif event == "mouse:down":
            if await self._require_perm(ws, session_token, "mouse"):
                mouse.mouse_down(payload.get("button", "left"))

        elif event == "mouse:up":
            if await self._require_perm(ws, session_token, "mouse"):
                mouse.mouse_up(payload.get("button", "left"))

        elif event == "mouse:scroll":
            if await self._require_perm(ws, session_token, "mouse"):
                mouse.scroll(payload.get("dy", 0), payload.get("dx", 0))

        elif event == "mouse:zoom":
            if await self._require_perm(ws, session_token, "mouse"):
                mouse.zoom(payload.get("delta", 0))

        elif event == "touchpad:gesture":
            if await self._require_perm(ws, session_token, "keyboard"):
                shortcut = GESTURE_MAP.get(payload.get("gesture", ""))
                if shortcut:
                    keyboard.press_shortcut(shortcut)

        elif event == "mouse:click_rel":
            if await self._require_perm(ws, session_token, "mouse"):
                abs_x, abs_y = screen.map_relative_to_screen(payload.get("rel_x", 0), payload.get("rel_y", 0), payload.get("monitor_id"))
                mouse.set_position(abs_x, abs_y)
                mouse.click(payload.get("button", "left"))

        # 2. Keyboard & Shortcuts
        elif event == "keyboard:type":
            if await self._require_perm(ws, session_token, "keyboard"):
                keyboard.type_text(payload.get("text", ""))

        elif event == "keyboard:key":
            if await self._require_perm(ws, session_token, "keyboard"):
                keyboard.press_key(payload.get("key", ""))

        elif event == "keyboard:shortcut":
            if await self._require_perm(ws, session_token, "keyboard"):
                keyboard.press_shortcut(payload.get("shortcut", ""))

        elif event == "media:command":
            if await self._require_perm(ws, session_token, "media"):
                keyboard.press_shortcut(payload.get("command", ""))

        # 3. Screen Mirroring & Monitors
        elif event == "monitors:list":
            await ws.send_json({"event": "monitors:list_data", "data": {"monitors": screen.get_monitors_list()}})

        elif event == "monitors:select":
            mon_id = payload.get("monitor_id", 1)
            screen.select_monitor(mon_id)
            audit_log.log("MONITOR_SWITCHED", f"Switched to Monitor {mon_id}", client_name)
            await ws.send_json({"event": "monitors:selected", "data": {"monitor_id": mon_id}})

        elif event == "screen:frame":
            if await self._require_perm(ws, session_token, "screen"):
                frame_b64 = screen.capture_frame_base64(
                    quality=payload.get("quality", config.SCREEN_JPEG_QUALITY),
                    max_width=payload.get("maxWidth", 1280),
                    monitor_id=payload.get("monitor_id")
                )
                await ws.send_json({"event": "screen:frame_data", "data": {"frame": frame_b64}})

        elif event == "webrtc:offer":
            if await self._require_perm(ws, session_token, "screen"):
                try:
                    from aiortc import RTCPeerConnection, RTCSessionDescription
                    from screen_capture import ScreenStreamTrack, HAS_WEBRTC

                    if not HAS_WEBRTC:
                        await ws.send_json({"event": "webrtc:error", "data": {"error": "WebRTC not available on host"}})
                    else:
                        sdp = payload.get("sdp")
                        sdp_type = payload.get("type", "offer")
                        if sdp:
                            pc = RTCPeerConnection()
                            self._active_peer_connections.add(pc)
                            fps = min(60, max(15, int(payload.get("fps", 60))))
                            max_w = min(1920, max(640, int(payload.get("maxWidth", 1280))))
                            track = ScreenStreamTrack(fps=fps, max_width=max_w)
                            pc.addTrack(track)

                            @pc.on("connectionstatechange")
                            async def on_state_change():
                                if pc.connectionState in ["failed", "closed"]:
                                    self._active_peer_connections.discard(pc)
                                    try:
                                        await pc.close()
                                    except Exception:
                                        pass

                            await pc.setRemoteDescription(RTCSessionDescription(sdp=sdp, type=sdp_type))
                            answer = await pc.createAnswer()
                            await pc.setLocalDescription(answer)

                            await ws.send_json({
                                "event": "webrtc:answer",
                                "data": {
                                    "sdp": pc.localDescription.sdp,
                                    "type": pc.localDescription.type,
                                    "fps": fps,
                                }
                            })
                except Exception as rtc_err:
                    print(f"[WebRTC Offer Error]: {rtc_err}")
                    await ws.send_json({"event": "webrtc:error", "data": {"error": str(rtc_err)}})

        elif event == "webrtc:stop":
            for pc in list(self._active_peer_connections):
                try:
                    asyncio.create_task(pc.close())
                except Exception:
                    pass
            self._active_peer_connections.clear()

        # 4. Webcam Sentry
        elif event == "webcam:list":
            if await self._require_perm(ws, session_token, "webcam"):
                await ws.send_json({"event": "webcam:list_data", "data": {"cameras": webcam.get_available_cameras()}})

        elif event == "webcam:frame":
            if await self._require_perm(ws, session_token, "webcam"):
                frame_b64 = webcam.capture_frame_base64(
                    cam_id=payload.get("camera_id", 0),
                    quality=payload.get("quality", config.WEBCAM_JPEG_QUALITY)
                )
                await ws.send_json({"event": "webcam:frame_data", "data": {"frame": frame_b64}})

        elif event == "webcam:stop":
            webcam.release()

        # 5. Taskbar App Windows Live Monitor & Controls
        elif event == "windows:list":
            await ws.send_json({"event": "windows:list_data", "data": {"windows": window_monitor.get_open_windows()}})

        elif event == "windows:thumbnails":
            await ws.send_json({"event": "windows:thumbnails_data", "data": {"windows": window_monitor.get_windows_with_thumbnails()}})

        elif event == "windows:frame":
            hwnd = payload.get("hwnd")
            frame_b64 = window_monitor.capture_window_base64(int(hwnd), quality=payload.get("quality", 65), max_width=payload.get("maxWidth", 960)) if hwnd else ""
            await ws.send_json({"event": "windows:frame_data", "data": {"hwnd": hwnd, "frame": frame_b64}})

        elif event == "windows:action":
            hwnd, act = payload.get("hwnd"), payload.get("action", "focus")
            fn = getattr(window_monitor, f"{act}_window", None)
            success = fn(int(hwnd), client_name) if fn and hwnd else False
            await ws.send_json({"event": "windows:action_result", "data": {"hwnd": hwnd, "action": act, "success": success}})

        # 6. Allowlisted App Launcher & Find My PC
        elif event == "app:list":
            await ws.send_json({"event": "app:list_data", "data": {"apps": system.get_allowlisted_apps_list()}})

        elif event == "app:launch":
            if await self._require_perm(ws, session_token, "app_launcher"):
                res = system.launch_allowlisted_app(payload.get("app_key", ""), client_name)
                await ws.send_json({"event": "app:launch_result", "data": res})

        elif event == "find_pc:start":
            await ws.send_json({"event": "find_pc:status", "data": system.start_find_pc(client_name)})

        elif event == "find_pc:stop":
            await ws.send_json({"event": "find_pc:status", "data": system.stop_find_pc(client_name)})

        # 7. Clipboard Sync & History
        elif event == "clipboard:get":
            if await self._require_perm(ws, session_token, "clipboard"):
                await ws.send_json({"event": "clipboard:data", "data": {"text": clip.get_text(), "history": clip.get_history()}})

        elif event == "clipboard:set":
            if await self._require_perm(ws, session_token, "clipboard"):
                clip.set_text(payload.get("text", ""), client_name)
                await ws.send_json({"event": "clipboard:updated", "data": {"success": True}})

        elif event == "clipboard:clear":
            if await self._require_perm(ws, session_token, "clipboard"):
                clip.clear_clipboard()
                audit_log.log("CLIPBOARD_CLEARED", "PC clipboard cleared", client_name)
                await ws.send_json({"event": "clipboard:cleared", "data": {"success": True}})

        # 8. System Diagnostics, Power & Panic Boss Key
        elif event == "system:stats":
            await ws.send_json({"event": "system:stats_data", "data": system.get_system_stats()})

        elif event == "system:action":
            act = payload.get("action", "")
            perm = POWER_PERMS.get(act, "power_lock")
            if await self._require_perm(ws, session_token, perm):
                res = system.execute_power_action(act, client_name)
                await ws.send_json({"event": "system:action_result", "data": res})

        elif event == "system:panic":
            await ws.send_json({"event": "system:panic_result", "data": system.trigger_panic_mode(client_name)})

        elif event == "brightness:set":
            level = payload.get("level", 100)
            await ws.send_json({"event": "brightness:changed", "data": {"level": level, "success": system.set_brightness(level)}})

        # 9. Remote File Manager
        elif event == "files:list":
            if await self._require_perm(ws, session_token, "files"):
                await ws.send_json({"event": "files:list_data", "data": files.list_directory(payload.get("path"))})

        # 10. Device Permissions & Pairing
        elif event == "devices:list":
            await ws.send_json({"event": "devices:list_data", "data": {"devices": auth_manager.get_paired_devices()}})

        elif event == "devices:update_perms":
            tgt, perms = payload.get("device_id"), payload.get("permissions", {})
            success = auth_manager.update_device_permissions(tgt, perms) if tgt and perms else False
            await ws.send_json({"event": "devices:perms_updated", "data": {"success": success}})

        elif event == "devices:revoke":
            tgt = payload.get("device_id")
            success = auth_manager.revoke_device(tgt) if tgt else False
            await ws.send_json({"event": "devices:revoked", "data": {"success": success, "device_id": tgt}})

        elif event == "devices:revoke_all":
            await ws.send_json({"event": "devices:all_revoked", "data": {"count": auth_manager.revoke_all_sessions()}})

        # 11. Security Audit Logs & Settings
        elif event == "security:logs":
            await ws.send_json({"event": "security:logs_data", "data": {"logs": audit_log.get_logs()}})

        elif event == "security:get_settings":
            await ws.send_json({"event": "security:settings", "data": system.get_security_settings()})

        # 12. Custom Remotes
        elif event == "custom_remotes:get":
            remotes = []
            if config.CUSTOM_REMOTES_FILE.exists():
                try:
                    remotes = json.loads(config.CUSTOM_REMOTES_FILE.read_text(encoding="utf-8"))
                except Exception:
                    pass
            await ws.send_json({"event": "custom_remotes:data", "data": {"remotes": remotes}})

        elif event == "custom_remotes:save":
            remotes = payload.get("remotes", [])
            try:
                config.CUSTOM_REMOTES_FILE.write_text(json.dumps(remotes, indent=2), encoding="utf-8")
                audit_log.log("CUSTOM_REMOTES_SAVED", f"Saved {len(remotes)} custom remote(s)", client_name)
                await ws.send_json({"event": "custom_remotes:saved", "data": {"success": True}})
            except Exception as e:
                await ws.send_json({"event": "custom_remotes:saved", "data": {"success": False, "error": str(e)}})

        # 13. Proximity Auto-Lock & Ping
        elif event == "ping:proximity":
            self._last_client_ping = time.time()
            self._client_had_ping = True
            await ws.send_json({"event": "pong:proximity", "data": {"time": time.time()}})

        elif event == "settings:walkaway_lock":
            enabled = payload.get("enabled", False)
            self._last_client_ping = time.time()
            self._client_had_ping = enabled
            res = system.set_walkaway_lock(enabled, client_name)
            self.broadcast_event("settings:walkaway_status", res)

        # 14. Guard Mode & Sentry Anti-Theft
        elif event == "guard:toggle":
            enabled = payload.get("enabled", False)
            if enabled:
                res = system.start_guard_mode(lambda data: self.broadcast_event("guard:intruder_alert", data), client_name)
            else:
                res = system.stop_guard_mode(client_name)
            self.broadcast_event("guard:status", res)

        elif event == "sentry:arm":
            res = system.arm_sentry(
                lambda data: self.broadcast_event("sentry:triggered", data),
                client_name,
                grace_seconds=payload.get("grace_seconds", 10)
            )
            self.broadcast_event("sentry:status", system.get_sentry_status())

        elif event == "sentry:disarm":
            system.disarm_sentry(client_name)
            self.broadcast_event("sentry:status", system.get_sentry_status())

        elif event == "sentry:get_status":
            await ws.send_json({"event": "sentry:status", "data": system.get_sentry_status()})

        # 15. Software Updates
        elif event == "update:check":
            info = auto_updater.check_for_updates()
            await ws.send_json({"event": "system:update_info", "data": info})

        elif event == "update:apply":
            res = auto_updater.apply_update()
            await ws.send_json({"event": "system:update_result", "data": res})

    async def _walkaway_watchdog(self):
        """Active proximity watcher: Locks PC if client heartbeat stops for > 8 seconds."""
        while True:
            await asyncio.sleep(2.0)
            try:
                if system.is_walkaway_lock_enabled():
                    active_live = [c for c in self.active_ws_connections if not c.closed]
                    if self._client_had_ping and (time.time() - self._last_client_ping > 8.0) and active_live:
                        print("[Security] Walk-Away Watchdog: Phone out of Wi-Fi range. Locking PC!", flush=True)
                        self._client_had_ping = False
                        system.execute_power_action("lock", "WalkAway_Watchdog")
            except Exception:
                pass

    async def start(self, host: str = config.HOST, port: int = config.PORT):
        """Start aiohttp web server."""
        self.loop = asyncio.get_running_loop()
        auto_updater.start_background_check()
        system.set_sentry_status_listener(lambda: self.broadcast_event("sentry:status", system.get_sentry_status()))
        self._watchdog_task = asyncio.create_task(self._walkaway_watchdog())
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, host, port)
        await self.site.start()
        print(f"[*] EasyConnect v2.0 Server running on http://{host}:{port}")

    async def stop(self):
        """Stop server gracefully."""
        webcam.release()
        for pc in list(self._active_peer_connections):
            try:
                await pc.close()
            except Exception:
                pass
        self._active_peer_connections.clear()
        if self.runner:
            await self.runner.cleanup()
