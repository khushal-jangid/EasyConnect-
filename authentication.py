"""
EasyConnect v2.0 - Cryptographic Authentication, Session & Granular Permission Engine
"""
import os
import json
import time
import secrets
import threading
from typing import Optional, Dict, Any, List
from pathlib import Path
import config
from activity_log import audit_log

class AuthManager:
    """Manages pairing tokens, persistent paired devices, active sessions & granular permissions."""

    def __init__(self):
        self._lock = threading.Lock()
        self._current_pairing_token: Optional[str] = None
        self._pairing_token_expires_at: float = 0.0
        # session_token -> session_info dict
        self._sessions: Dict[str, Dict[str, Any]] = {}
        # client_id -> device_info dict (persisted in .paired_devices.json)
        self._devices: Dict[str, Dict[str, Any]] = {}
        
        self._load_devices()
        self.generate_pairing_token()

    def _load_devices(self):
        """Load paired devices registry from disk and restore persistent sessions."""
        if config.PAIRED_DEVICES_FILE.exists():
            try:
                data = json.loads(config.PAIRED_DEVICES_FILE.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    now = int(time.time())
                    for d_id, dev in data.items():
                        if isinstance(dev, dict):
                            # Ensure all default permissions are present in existing devices
                            perms = dev.setdefault("permissions", config.DEFAULT_PERMISSIONS.copy())
                            for perm, val in config.DEFAULT_PERMISSIONS.items():
                                if perm not in perms:
                                    perms[perm] = val
                            # Restore active sessions for previously paired devices
                            tokens = dev.get("session_tokens", [])
                            if isinstance(tokens, str):
                                tokens = [tokens]
                            for tok in tokens:
                                self._sessions[tok] = {
                                    "session_token": tok,
                                    "client_id": d_id,
                                    "client_name": dev.get("name", "Smartphone"),
                                    "client_ip": dev.get("ip", "Unknown"),
                                    "created_at": dev.get("paired_at", now),
                                    "last_active": now,
                                    "permissions": perms,
                                }
                    self._devices = data
            except Exception as e:
                print(f"[Auth] Error loading paired devices: {e}")

    def get_active_sessions(self) -> List[Dict[str, Any]]:
        """Get list of active sessions."""
        with self._lock:
            return list(self._sessions.values())

    def _save_devices(self):
        """Save paired devices registry to disk."""
        try:
            config.PAIRED_DEVICES_FILE.write_text(json.dumps(self._devices, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"[Auth] Error saving paired devices: {e}")

    def generate_pairing_token(self) -> tuple[str, int]:
        """
        Generate a secure 6-digit temporary pairing PIN/token.
        Expires in config.PAIRING_TOKEN_LIFESPAN seconds.
        """
        with self._lock:
            # 6-digit numeric PIN (e.g. 583920)
            self._current_pairing_token = f"{secrets.randbelow(900000) + 100000}"
            self._pairing_token_expires_at = time.time() + config.PAIRING_TOKEN_LIFESPAN
            return self._current_pairing_token, int(self._pairing_token_expires_at)

    def get_current_pairing_token(self) -> Optional[tuple[str, int]]:
        """Retrieve current pairing token and remaining seconds if not expired."""
        with self._lock:
            if not self._current_pairing_token:
                return None
            remaining = self._pairing_token_expires_at - time.time()
            if remaining <= 0:
                self._current_pairing_token = None
                return None
            return self._current_pairing_token, int(self._pairing_token_expires_at)

    def validate_and_consume_pairing_token(self, token: str, client_info: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        Validate pairing token. If valid and not expired, immediately invalidate it
        (one-time use security) and return a new persistent session token.
        """
        with self._lock:
            if not self._current_pairing_token or time.time() >= self._pairing_token_expires_at:
                return None
            
            # Clean token string
            token_clean = str(token).strip().replace(" ", "").replace("-", "")
            expected_clean = str(self._current_pairing_token).strip()

            # Constant-time comparison to prevent timing attacks
            if not secrets.compare_digest(expected_clean, token_clean):
                return None
            
            # Token is valid: immediately invalidate the pairing token
            self._current_pairing_token = None
            self._pairing_token_expires_at = 0.0
            
            # Generate long-lived session token
            session_token = secrets.token_hex(32)
            now = int(time.time())
            
            client_id = client_info.get("device_id") if client_info else f"client-{secrets.token_hex(4)}"
            client_name = client_info.get("name", "Smartphone") if client_info else "Smartphone"
            client_ip = client_info.get("ip", "Unknown") if client_info else "Unknown"
            
            # Retrieve or initialize device permissions
            if client_id in self._devices:
                permissions = self._devices[client_id].get("permissions", config.DEFAULT_PERMISSIONS.copy())
            else:
                permissions = config.DEFAULT_PERMISSIONS.copy()

            existing_tokens = self._devices.get(client_id, {}).get("session_tokens", [])
            if not isinstance(existing_tokens, list):
                existing_tokens = [existing_tokens] if existing_tokens else []
            if session_token not in existing_tokens:
                existing_tokens.append(session_token)

            device_record = {
                "device_id": client_id,
                "name": client_name,
                "ip": client_ip,
                "paired_at": self._devices.get(client_id, {}).get("paired_at", now),
                "last_seen": now,
                "is_online": True,
                "permissions": permissions,
                "session_tokens": existing_tokens,
            }
            self._devices[client_id] = device_record
            self._save_devices()

            session_data = {
                "session_token": session_token,
                "client_id": client_id,
                "client_name": client_name,
                "client_ip": client_ip,
                "created_at": now,
                "last_active": now,
                "permissions": permissions,
            }
            
            self._sessions[session_token] = session_data
            audit_log.log("DEVICE_PAIRED", f"Paired with device '{client_name}' ({client_id})", client_name, client_ip)
            return session_token

    def validate_session(self, session_token: str) -> Optional[Dict[str, Any]]:
        """Validate if a session token is active, update last_seen, and sync permissions."""
        if not session_token:
            return None
        with self._lock:
            session = self._sessions.get(session_token)
            now = int(time.time())

            if not session:
                # Check if session_token belongs to any known paired device
                for d_id, dev in self._devices.items():
                    toks = dev.get("session_tokens", [])
                    if isinstance(toks, str):
                        toks = [toks]
                    if session_token in toks:
                        session = {
                            "session_token": session_token,
                            "client_id": d_id,
                            "client_name": dev.get("name", "Smartphone"),
                            "client_ip": dev.get("ip", "Unknown"),
                            "created_at": dev.get("paired_at", now),
                            "last_active": now,
                            "permissions": dev.get("permissions", config.DEFAULT_PERMISSIONS.copy()),
                        }
                        self._sessions[session_token] = session
                        break

            if not session:
                return None
            
            # Check session expiration
            if now - session["last_active"] > config.SESSION_TIMEOUT:
                del self._sessions[session_token]
                return None
            
            session["last_active"] = now
            client_id = session.get("client_id")
            if client_id and client_id in self._devices:
                self._devices[client_id]["last_seen"] = now
                self._devices[client_id]["is_online"] = True
                session["permissions"] = self._devices[client_id].get("permissions", config.DEFAULT_PERMISSIONS.copy())
            
            return session

    def check_permission(self, session_token: str, permission_name: str) -> bool:
        """
        Enforce backend security permission check.
        Returns True only if session is valid and permission is granted.
        """
        session = self.validate_session(session_token)
        if not session:
            return False
        
        perms = session.get("permissions", {})
        allowed = perms.get(permission_name, config.DEFAULT_PERMISSIONS.get(permission_name, False))
        if not allowed:
            client_name = session.get("client_name", "Device")
            audit_log.log("PERMISSION_DENIED", f"Action '{permission_name}' denied for {client_name}", client_name)
        return allowed

    def get_paired_devices(self) -> List[Dict[str, Any]]:
        """Get full list of registered paired devices with status."""
        with self._lock:
            now = int(time.time())
            active_client_ids = {s["client_id"] for s in self._sessions.values()}
            
            devices_list = []
            for d_id, d_info in self._devices.items():
                is_online = d_id in active_client_ids
                last_seen_sec = now - d_info.get("last_seen", now)
                
                if last_seen_sec < 60:
                    last_seen_str = "Just now"
                elif last_seen_sec < 3600:
                    last_seen_str = f"{last_seen_sec // 60}m ago"
                elif last_seen_sec < 86400:
                    last_seen_str = f"{last_seen_sec // 3600}h ago"
                else:
                    last_seen_str = f"{last_seen_sec // 86400}d ago"

                devices_list.append({
                    "device_id": d_id,
                    "name": d_info.get("name", "Unknown"),
                    "ip": d_info.get("ip", "Unknown"),
                    "paired_at": d_info.get("paired_at", now),
                    "last_seen_str": last_seen_str,
                    "is_online": is_online,
                    "permissions": d_info.get("permissions", config.DEFAULT_PERMISSIONS.copy()),
                })
            return devices_list

    def update_device_permissions(self, client_id: str, new_permissions: Dict[str, bool]) -> bool:
        """Update permissions for a specific device."""
        with self._lock:
            if client_id in self._devices:
                self._devices[client_id]["permissions"].update(new_permissions)
                self._save_devices()
                
                # Update any active live session
                for s in self._sessions.values():
                    if s["client_id"] == client_id:
                        s["permissions"].update(new_permissions)
                
                audit_log.log("PERMISSIONS_UPDATED", f"Updated permissions for device '{client_id}'")
                return True
            return False

    def revoke_device(self, client_id: str) -> bool:
        """Revoke a device and terminate any active sessions."""
        with self._lock:
            # Terminate active sessions for this device
            tokens_to_remove = [tok for tok, s in self._sessions.items() if s["client_id"] == client_id]
            for tok in tokens_to_remove:
                del self._sessions[tok]
            
            if client_id in self._devices:
                dev_name = self._devices[client_id].get("name", client_id)
                del self._devices[client_id]
                self._save_devices()
                audit_log.log("DEVICE_REVOKED", f"Revoked paired device '{dev_name}' ({client_id})")
                return True
            return False

    def revoke_all_sessions(self) -> int:
        """Disconnect and revoke all authenticated sessions."""
        with self._lock:
            count = len(self._sessions)
            self._sessions.clear()
            self._current_pairing_token = secrets.token_urlsafe(32)
            self._pairing_token_expires_at = time.time() + config.PAIRING_TOKEN_LIFESPAN
            audit_log.log("ALL_DISCONNECTED", f"Disconnected all {count} active device sessions")
            return count

# Global instance
auth_manager = AuthManager()
