"""
EasyConnect v2.0 - Main Python PC Agent (Local Wi-Fi Hub)
"""
import os
import sys
import time
import asyncio
import threading
import webbrowser
import argparse

# Enable UTF-8 and ANSI VT processing on Windows immediately
if sys.platform == "win32":
    try:
        os.system("")
    except Exception:
        pass
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    import tkinter as tk
    from tkinter import messagebox
    from PIL import Image, ImageTk
except ImportError:
    tk = None
    messagebox = None
    Image = None
    ImageTk = None

import config
from authentication import auth_manager
from qr_pairing import qr_manager, get_local_ip
from screen_capture import screen
from system_control import system
from network import NetworkServer
from auto_updater import auto_updater


class PulseAgentCLI:
    """High-Performance, Standalone Terminal CLI Hub for EasyConnect v2.0."""

    def __init__(self, qr_style: str = "compact"):
        self.qr_style = qr_style
        self.is_connected = False
        self.connected_device_name = None
        self.expires_at = 0
        self.current_token = None
        self.running = True
        self._lock = threading.Lock()
        self.server_ready = threading.Event()

        # Start Asyncio Network Server in background daemon thread
        self.server = NetworkServer(
            on_device_connected=self.on_device_connected,
            on_device_disconnected=self.on_device_disconnected,
        )
        self.server_thread = threading.Thread(target=self._run_async_server, daemon=True)
        self.server_thread.start()

    def _run_async_server(self):
        """Asynchronous server execution loop."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.server.start(config.HOST, config.PORT))
        self.server_ready.set()
        loop.run_forever()

    def on_device_connected(self, device_info):
        """Callback when mobile phone pairs or connects."""
        with self._lock:
            self.is_connected = True
            if isinstance(device_info, dict):
                self.connected_device_name = device_info.get("name", "Smartphone")
                ip = device_info.get("ip", "")
                ip_str = f" ({ip})" if ip else ""
            else:
                self.connected_device_name = str(device_info)
                ip_str = ""
            print(f"\n\033[92m🟢 [CONNECTED] Device linked: {self.connected_device_name}{ip_str}\033[0m", flush=True)

    def on_device_disconnected(self):
        """Callback when phone disconnects."""
        with self._lock:
            self.is_connected = False
            prev_device = self.connected_device_name or "Mobile Phone"
            self.connected_device_name = None
            print(f"\n\033[93m🟡 [DISCONNECTED] {prev_device} disconnected. Ready for new connection.\033[0m", flush=True)

    def regenerate_token(self):
        """Generate a new pairing PIN and update expiry timestamp."""
        token, expires_at = auth_manager.generate_pairing_token()
        with self._lock:
            self.current_token = token
            self.expires_at = expires_at

    def print_dashboard(self):
        """Display the complete, clean terminal UI with high-contrast QR code."""
        with self._lock:
            token = self.current_token
            expires_at = self.expires_at
            is_conn = self.is_connected
            dev_name = self.connected_device_name

        remaining = max(0, int(expires_at - time.time()))
        mins, secs = divmod(remaining, 60)
        formatted_pin = f"{token[:3]} {token[3:]}" if token and len(token) == 6 else (token or "------")
        server_url = qr_manager.get_server_url()
        direct_url = qr_manager.get_direct_pairing_url(token) if token else server_url
        monitors = screen.get_monitors_list()

        status_line = (
            f"\033[92m🟢 Connected: {dev_name}\033[0m"
            if is_conn
            else f"\033[93m🟡 Ready for connection (Waiting for smartphone...)\033[0m"
        )

        print("\n" + "=" * 68, flush=True)
        print("          ⚡ EASYCONNECT v2.1 - LOCAL WI-FI PC AGENT", flush=True)
        print("=" * 68, flush=True)
        print(f"  🖥️  PC Name:       {config.DEVICE_NAME} ({config.DEVICE_OS})", flush=True)
        print(f"  🌐 Server URL:    \033[96m{server_url}\033[0m", flush=True)
        print(f"  📥 Download Page: \033[95m{server_url}/download\033[0m", flush=True)
        print(f"  🔑 Pairing PIN:   \033[93m\033[1m{formatted_pin}\033[0m  (For manual entry)", flush=True)
        print(f"  ⏱️  Token Expiry:  {mins:02d}:{secs:02d}", flush=True)
        print(f"  📡 Monitors:      {len(monitors)} active display(s)", flush=True)
        print(f"  ⚡ Status:        {status_line}", flush=True)
        print("=" * 68, flush=True)
        print("  📱 SCAN THIS QR CODE WITH YOUR PHONE CAMERA TO CONNECT:", flush=True)
        print("", flush=True)

        qr_manager.print_terminal_qr(style=self.qr_style, indent="    ")

        print("", flush=True)
        print(f"  🔗 Direct Pairing Link: \033[94m{direct_url}\033[0m", flush=True)
        print(f"  💡 Or open browser and enter PIN: \033[93m{formatted_pin}\033[0m", flush=True)
        up_info = auto_updater.get_update_info()
        if up_info.get("has_update"):
            print(f"  \033[93m✨ [UPDATE AVAILABLE] Version {up_info.get('latest_version')} is ready! Press [U] to update now.\033[0m", flush=True)
        print("=" * 68, flush=True)
        print("  HOTKEYS:  [R] New QR/PIN   [U] Update   [O] Open Web   [S] Alarm   [Q] Quit", flush=True)
        print("=" * 68, flush=True)

    def run(self):
        """Main execution and hotkey polling loop."""
        self.server_ready.wait(timeout=2.5)
        self.regenerate_token()
        self.print_dashboard()

        has_msvcrt = False
        if sys.platform == "win32":
            try:
                import msvcrt
                has_msvcrt = True
            except Exception:
                has_msvcrt = False

        last_alarm_alert = 0
        try:
            while self.running:
                time.sleep(0.1)

                # Check token expiry
                now = time.time()
                with self._lock:
                    rem = self.expires_at - now
                    is_conn = self.is_connected

                if rem <= 0 and not is_conn:
                    print("\n[Auth] Pairing token expired. Regenerating new QR Code...", flush=True)
                    self.regenerate_token()
                    self.print_dashboard()

                # Check Find My PC alarm
                if system.is_find_pc_active():
                    if now - last_alarm_alert > 3:
                        print("\n\033[91m🚨 FIND MY PC SOUND RINGING! Press [S] to stop alarm! 🚨\033[0m", flush=True)
                        last_alarm_alert = now

                # Interactive hotkeys in terminal
                if has_msvcrt and sys.stdin.isatty():
                    if msvcrt.kbhit():
                        key = msvcrt.getch()
                        if key in (b'\x00', b'\xe0'):
                            msvcrt.getch()
                            continue
                        
                        char = key.decode("utf-8", errors="ignore").lower()
                        if char == 'r':
                            print("\n[Action] Regenerating pairing token...", flush=True)
                            self.regenerate_token()
                            self.print_dashboard()
                        elif char == 't':
                            self.qr_style = "large" if self.qr_style == "compact" else "compact"
                            print(f"\n[Action] Toggled QR style to: {self.qr_style}", flush=True)
                            self.print_dashboard()
                        elif char == 'd':
                            print("\n[Action] Disconnecting all mobile sessions...", flush=True)
                            auth_manager.revoke_all_sessions()
                            self.on_device_disconnected()
                        elif char == 'o':
                            print("\n[Action] Opening controller in PC browser...", flush=True)
                            webbrowser.open(qr_manager.get_server_url())
                        elif char == 'u':
                            print("\n[Update] Checking & applying latest update...", flush=True)
                            res = auto_updater.apply_update()
                            print(f"[Update] {res.get('message')}", flush=True)
                        elif char == 's':
                            stopped_any = False
                            if system.is_find_pc_active():
                                system.stop_find_pc()
                                print("\n[Action] Stopped Find My PC alarm.", flush=True)
                                stopped_any = True
                            if getattr(system, 'sentry_ringing', False) or getattr(system, 'sentry_armed', False):
                                system.disarm_sentry("Terminal [S]")
                                print("\n[Action] Disarmed Sentry alarm.", flush=True)
                                stopped_any = True
                            if not stopped_any:
                                print("\n[Action] No active alarm to stop.", flush=True)
                        elif char == 'q':
                            print("\n[EasyConnect] Exiting PC Agent. Goodbye!", flush=True)
                            self.running = False
                            break
        except KeyboardInterrupt:
            print("\n[EasyConnect] Stopping PC Agent (Ctrl+C)...", flush=True)
            self.running = False


class PulseAgentGUI:
    """Modern Dark GUI for EasyConnect v2.0 with Local Wi-Fi Connection."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("EasyConnect - PC Agent")
        self.root.geometry("440x630")
        self.root.configure(bg="#080c16")
        self.root.resizable(False, False)

        # Set Window Icon
        try:
            icon_candidates = [
                Path(__file__).resolve().parent / "icon.ico",
                Path(getattr(sys, "_MEIPASS", "")) / "icon.ico",
            ]
            for ic in icon_candidates:
                if ic.exists():
                    self.root.iconbitmap(default=str(ic))
                    break
        except Exception:
            pass

        # Center window on screen
        self.center_window(440, 630)

        # State
        self.current_qr_img = None
        self.connected_device_name = None
        self.is_connected = False
        self.expires_at = 0

        # Build UI layout
        self._build_ui()

        # Start Asyncio Network Server in background thread
        self.server = NetworkServer(
            on_device_connected=self.on_device_connected,
            on_device_disconnected=self.on_device_disconnected,
        )
        self.server_thread = threading.Thread(target=self._run_async_server, daemon=True)
        self.server_thread.start()

        # Initial QR Render
        self.regenerate_qr()

        # Print Terminal QR Code
        monitors = screen.get_monitors_list()
        print("=" * 60, flush=True)
        print("  EASYCONNECT v2.1 - LOCAL WI-FI PC AGENT ACTIVE", flush=True)
        print("=" * 60, flush=True)
        print(f"> Local Wi-Fi URL:  {qr_manager.get_server_url()}", flush=True)
        print(f"> Device Name:      {config.DEVICE_NAME} ({config.DEVICE_OS})", flush=True)
        print(f"> Displays Found:   {len(monitors)} Connected Monitor(s)", flush=True)
        for m in monitors:
            print(f"  - {m['name']}: {m['width']}x{m['height']}", flush=True)
        print("=" * 60, flush=True)
        qr_manager.print_terminal_qr(style="compact", indent="  ")

        # Start timer tick update loop
        self.update_timer()

    def center_window(self, width, height):
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = int((screen_width / 2) - (width / 2))
        y = int((screen_height / 2) - (height / 2))
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _build_ui(self):
        # 1. Header Banner
        header_frame = tk.Frame(self.root, bg="#080c16")
        header_frame.pack(fill="x", pady=(14, 6), padx=24)

        title_badge = tk.Label(
            header_frame,
            text="⚡ EASYCONNECT",
            font=("Plus Jakarta Sans", 11, "bold"),
            fg="#38bdf8",
            bg="#0f1a2e",
            padx=14,
            pady=4,
            relief="solid",
            bd=1,
        )
        title_badge.pack()

        subtitle = tk.Label(
            header_frame,
            text="Local Wi-Fi PC Remote Control Hub",
            font=("Plus Jakarta Sans", 9),
            fg="#64748b",
            bg="#080c16",
        )
        subtitle.pack(pady=(4, 8))

        # Find My PC Alert Banner
        self.find_pc_banner = tk.Frame(self.root, bg="#f43f5e", padx=10, pady=6)
        self.find_pc_label = tk.Label(
            self.find_pc_banner,
            text="🚨 FIND MY PC SOUND RINGING! 🚨",
            font=("Plus Jakarta Sans", 10, "bold"),
            fg="#ffffff",
            bg="#f43f5e",
        )
        self.find_pc_label.pack(side="left", padx=6)

        btn_stop_find = tk.Button(
            self.find_pc_banner,
            text="Stop Alarm",
            font=("Plus Jakarta Sans", 9, "bold"),
            bg="#ffffff",
            fg="#f43f5e",
            bd=0,
            padx=8,
            pady=2,
            cursor="hand2",
            command=lambda: (system.stop_find_pc(), system.disarm_sentry("GUI Button")),
        )
        btn_stop_find.pack(side="right", padx=6)

        # 2. QR Code Frame Container
        self.qr_container = tk.Frame(
            self.root, bg="#0f172a", bd=2, relief="solid", highlightbackground="#0284c7", highlightthickness=1
        )
        self.qr_container.pack(pady=4, padx=30)

        self.qr_label = tk.Label(self.qr_container, bg="#ffffff", bd=0)
        self.qr_label.pack(padx=6, pady=6)

        # 3. Instruction & URL
        self.instruction_label = tk.Label(
            self.root,
            text="Scan with smartphone camera to connect",
            font=("Plus Jakarta Sans", 10, "bold"),
            fg="#f8fafc",
            bg="#080c16",
        )
        self.instruction_label.pack(pady=(2, 2))

        self.url_label = tk.Label(
            self.root,
            text=f"http://{get_local_ip()}:{config.PORT}",
            font=("JetBrains Mono", 8, "bold"),
            fg="#38bdf8",
            bg="#0f172a",
            padx=10,
            pady=3,
            relief="flat",
        )
        self.url_label.pack(pady=(0, 4))

        # 4. PIN Box (For manual entry if not scanning QR)
        pin_frame = tk.Frame(
            self.root, bg="#0f172a", bd=1, relief="solid", highlightbackground="#0284c7", highlightthickness=1
        )
        pin_frame.pack(fill="x", padx=30, pady=(0, 6))

        tk.Label(
            pin_frame,
            text="PAIRING PIN (For Manual Entry)",
            font=("Plus Jakarta Sans", 8, "bold"),
            fg="#94a3b8",
            bg="#0f172a",
        ).pack(pady=(4, 0))

        self.pin_label = tk.Label(
            pin_frame,
            text="-- -- --",
            font=("JetBrains Mono", 16, "bold"),
            fg="#38bdf8",
            bg="#0f172a",
        )
        self.pin_label.pack(pady=(0, 4))

        # 5. Status HUD Box
        hud_frame = tk.Frame(self.root, bg="#0b1324", bd=1, relief="solid")
        hud_frame.pack(fill="x", padx=24, pady=(0, 8))

        self.status_dot_label = tk.Label(
            hud_frame,
            text="🟡 Status: Ready for connection",
            font=("Plus Jakarta Sans", 9, "bold"),
            fg="#f59e0b",
            bg="#0b1324",
            pady=4,
        )
        self.status_dot_label.pack()

        self.expiry_label = tk.Label(
            hud_frame,
            text="QR Token expires in: 5:00",
            font=("JetBrains Mono", 8),
            fg="#94a3b8",
            bg="#0b1324",
            pady=2,
        )
        self.expiry_label.pack()

        # 6. Buttons Row
        btn_frame = tk.Frame(self.root, bg="#080c16")
        btn_frame.pack(fill="x", padx=24, pady=2)

        btn_regen = tk.Button(
            btn_frame,
            text="🔄 New QR Code",
            font=("Plus Jakarta Sans", 9, "bold"),
            bg="#0284c7",
            fg="#ffffff",
            bd=0,
            padx=10,
            pady=7,
            cursor="hand2",
            command=self.regenerate_qr,
        )
        btn_regen.pack(side="left", expand=True, fill="x", padx=(0, 4))

        btn_disconnect = tk.Button(
            btn_frame,
            text="❌ Disconnect All",
            font=("Plus Jakarta Sans", 9, "bold"),
            bg="#334155",
            fg="#f8fafc",
            bd=0,
            padx=10,
            pady=7,
            cursor="hand2",
            command=self.disconnect_all,
        )
        btn_disconnect.pack(side="left", expand=True, fill="x", padx=(4, 0))

        # Open Web browser shortcut
        btn_web = tk.Button(
            self.root,
            text="🌐 Open Controller in PC Browser",
            font=("Plus Jakarta Sans", 8),
            bg="#0f172a",
            fg="#94a3b8",
            bd=0,
            pady=3,
            cursor="hand2",
            command=lambda: webbrowser.open(qr_manager.get_server_url()),
        )
        btn_web.pack(pady=(4, 8))

    def _run_async_server(self):
        """Asynchronous server execution loop."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.server.start(config.HOST, config.PORT))
        loop.run_forever()

    def regenerate_qr(self):
        """Force regenerate pairing token and update QR display."""
        auth_manager.generate_pairing_token()
        tk_img, token, expires_at = qr_manager.generate_tk_image(size=180)
        self.current_qr_img = tk_img
        self.qr_label.configure(image=self.current_qr_img)
        self.expires_at = expires_at
        display_url = qr_manager.get_server_url()
        self.url_label.config(text=display_url)
        formatted_pin = f"{token[:3]} {token[3:]}" if len(token) == 6 else token
        self.pin_label.config(text=formatted_pin)
        print(f"> Active Pairing PIN: {formatted_pin} | URL: {display_url}", flush=True)
        qr_manager.print_terminal_qr(style="compact", indent="  ")

    def disconnect_all(self):
        """Disconnect all active mobile sessions."""
        auth_manager.revoke_all_sessions()
        self.on_device_disconnected()
        if messagebox:
            messagebox.showinfo("EasyConnect", "All paired devices have been disconnected.")

    def on_device_connected(self, device_info):
        """Callback when a phone connects."""
        self.is_connected = True
        if isinstance(device_info, dict):
            self.connected_device_name = device_info.get("name", "Mobile Phone")
        else:
            self.connected_device_name = str(device_info)
        self.root.after(0, self._update_connected_ui)

    def _update_connected_ui(self):
        self.status_dot_label.config(
            text=f"🟢 Connected: {self.connected_device_name}",
            fg="#10b981",
        )

    def on_device_disconnected(self):
        """Callback when phone disconnects."""
        self.is_connected = False
        self.connected_device_name = None
        self.root.after(0, self._update_disconnected_ui)

    def _update_disconnected_ui(self):
        self.status_dot_label.config(
            text="🟡 Status: Ready for connection",
            fg="#f59e0b",
        )

    def update_timer(self):
        """Update token expiry countdown and check Find My PC alarm."""
        remaining = max(0, int(self.expires_at - time.time()))
        mins, secs = divmod(remaining, 60)
        self.expiry_label.config(text=f"Token expires in: {mins:02d}:{secs:02d}")

        if remaining <= 0 and not self.is_connected:
            self.regenerate_qr()

        # Update Find My PC / Sentry Alarm Banner visibility
        is_sentry = getattr(system, 'sentry_ringing', False)
        is_find = system.is_find_pc_active()
        if is_find or is_sentry:
            if not self.find_pc_banner.winfo_ismapped():
                if is_sentry:
                    self.find_pc_label.config(text="🚨 SENTRY THEFT ALARM RINGING! 🚨")
                else:
                    self.find_pc_label.config(text="🚨 FIND MY PC SOUND RINGING! 🚨")
                self.find_pc_banner.pack(fill="x", padx=24, pady=4, before=self.qr_container)
        else:
            if self.find_pc_banner.winfo_ismapped():
                self.find_pc_banner.pack_forget()

        self.root.after(1000, self.update_timer)


def main():
    parser = argparse.ArgumentParser(description="EasyConnect PC Agent v2.1")
    parser.add_argument(
        "--gui", "-g",
        action="store_true",
        help="Launch desktop Tkinter GUI window instead of running directly in terminal",
    )
    parser.add_argument(
        "--large-qr",
        action="store_true",
        help="Use large high-contrast double-space QR code format in terminal",
    )
    args = parser.parse_args()

    if args.gui:
        if tk is None:
            print("[Error] Tkinter is not available on this system. Running in terminal mode.")
            cli = PulseAgentCLI(qr_style="large" if args.large_qr else "compact")
            cli.run()
            return

        root = tk.Tk()
        app = PulseAgentGUI(root)

        def on_closing():
            root.destroy()
            sys.exit(0)

        root.protocol("WM_DELETE_WINDOW", on_closing)
        root.mainloop()
    else:
        # Default: Run cleanly in terminal (No separate GUI window popup!)
        cli = PulseAgentCLI(qr_style="large" if args.large_qr else "compact")
        cli.run()


if __name__ == "__main__":
    main()
