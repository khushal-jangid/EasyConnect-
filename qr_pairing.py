"""
EasyConnect - QR Code Generation & Local Wi-Fi Pairing Payload
"""
import io
import os
import sys
import json
import socket
import qrcode
from PIL import Image, ImageTk
from typing import Optional
import config
from authentication import auth_manager

def get_local_ip() -> str:
    """Discover the computer's primary LAN IPv4 address."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        try:
            ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            ip = "127.0.0.1"
    finally:
        s.close()
    return ip

class QRPairingManager:
    """Handles QR code generation and direct pairing payload for Local Wi-Fi."""

    def __init__(self):
        self.local_ip = get_local_ip()

    def get_server_url(self) -> str:
        """Get base HTTP URL for PC Agent."""
        return f"http://{self.local_ip}:{config.PORT}"

    def get_direct_pairing_url(self, token: str) -> str:
        """
        Direct web app pairing URL.
        When scanned with a phone camera on same Wi-Fi, this opens the mobile web app and automatically pairs!
        Using concise query parameters ensures minimal QR code density for instant camera recognition.
        """
        base_url = self.get_server_url()
        return f"{base_url}/?pair={token}"

    def generate_pairing_payload(self) -> tuple[dict, str, int]:
        """
        Generate or get current active pairing payload.
        Returns (payload_dict, token, expires_at).
        """
        current = auth_manager.get_current_pairing_token()
        if not current:
            token, expires_at = auth_manager.generate_pairing_token()
        else:
            token, expires_at = current

        payload = {
            "type": "pulse_pair",
            "device_id": config.DEVICE_ID,
            "device_name": config.DEVICE_NAME,
            "pairing_token": token,
            "mode": "local",
            "server": self.get_server_url(),
            "direct_url": self.get_direct_pairing_url(token),
            "expires_at": expires_at
        }
        return payload, token, expires_at

    def generate_qr_image(self, size: int = 240) -> tuple[Image.Image, str, int]:
        """Generate PIL Image of the QR code containing the direct pairing URL."""
        payload, token, expires_at = self.generate_pairing_payload()
        qr_data = payload["direct_url"]

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=8,
            border=2,
        )
        qr.add_data(qr_data)
        qr.make(fit=True)

        img = qr.make_image(fill_color="#000000", back_color="#ffffff").convert("RGB")
        img = img.resize((size, size), Image.Resampling.LANCZOS)
        return img, token, expires_at

    def generate_tk_image(self, size: int = 240) -> tuple[ImageTk.PhotoImage, str, int]:
        """Generate a Tkinter compatible PhotoImage for GUI display."""
        pil_img, token, expires_at = self.generate_qr_image(size=size)
        tk_img = ImageTk.PhotoImage(pil_img)
        return tk_img, token, expires_at

    def generate_terminal_qr(self, style: str = "compact", indent: str = "  ") -> str:
        """
        Generate a high-contrast, crystal-clear terminal string for the QR code.
        
        Features:
          - Pure bright-white quiet zone (border) so phone camera easily detects finder corners.
          - Pure black modules on pure white background (standard QR polarity).
          - Unicode-safe ANSI escape sequences with cross-platform terminal compatibility.
          - 'compact' (half-block): ~18 rows tall, perfect for any terminal without scrolling.
          - 'large' (2-space): ~33 rows tall, extra-large square modules.
        """
        if sys.platform == "win32":
            try:
                os.system("")  # Enable VT100 / ANSI escape sequence processing on Windows
            except Exception:
                pass

        payload, _, _ = self.generate_pairing_payload()
        qr_url = payload["direct_url"]

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=1,
            border=2,
        )
        qr.add_data(qr_url)
        qr.make(fit=True)
        matrix = qr.get_matrix()

        # ANSI Colors
        CLR_RESET = "\033[0m"
        BG_WHITE = "\033[107m"
        BG_BLACK = "\033[40m"
        FG_BLACK = "\033[30m"
        FG_WHITE = "\033[97m"

        if style == "large":
            # 2 spaces per module: large square blocks
            w_cell = f"{BG_WHITE}  {CLR_RESET}"
            b_cell = f"{BG_BLACK}  {CLR_RESET}"
            lines = []
            for row in matrix:
                line_str = "".join(b_cell if cell else w_cell for cell in row)
                lines.append(f"{indent}{line_str}")
            return "\n".join(lines)
        else:
            # Compact half-block rendering (upper half block ▀)
            rows = len(matrix)
            cols = len(matrix[0])
            if rows % 2 != 0:
                matrix.append([False] * cols)
                rows += 1

            lines = []
            for r in range(0, rows, 2):
                parts = [indent]
                for c in range(cols):
                    top = matrix[r][c]
                    bot = matrix[r + 1][c]
                    if not top and not bot:
                        # Both white
                        parts.append(f"{BG_WHITE}{FG_BLACK} {CLR_RESET}")
                    elif top and bot:
                        # Both black
                        parts.append(f"{BG_BLACK}{FG_WHITE} {CLR_RESET}")
                    elif top and not bot:
                        # Top black, bottom white (upper half ▀ is black, bg is white)
                        parts.append(f"{BG_WHITE}{FG_BLACK}▀{CLR_RESET}")
                    else:
                        # Top white, bottom black (upper half ▀ is white, bg is black)
                        parts.append(f"{BG_BLACK}{FG_WHITE}▀{CLR_RESET}")
                lines.append("".join(parts))
            return "\n".join(lines)

    def print_terminal_qr(self, style: str = "compact", indent: str = "  "):
        """Render high-contrast QR Code directly to stdout with UTF-8 encoding."""
        try:
            if hasattr(sys.stdout, "reconfigure"):
                try:
                    sys.stdout.reconfigure(encoding="utf-8")
                except Exception:
                    pass

            qr_str = self.generate_terminal_qr(style=style, indent=indent)
            print(qr_str, flush=True)
        except Exception:
            try:
                payload, _, _ = self.generate_pairing_payload()
                print(f"{indent}> Direct Pairing URL: {payload['direct_url']}", flush=True)
            except Exception:
                pass

# Global instance
qr_manager = QRPairingManager()
