"""
EasyConnect v2.0 - Security Activity Audit Logger
"""
import time
import threading
from typing import List, Dict, Any, Optional

class ActivityLogger:
    """In-memory security activity audit log with thread safety."""

    def __init__(self, max_entries: int = 200):
        self._lock = threading.Lock()
        self._max_entries = max_entries
        self._logs: List[Dict[str, Any]] = []

    def log(self, event_type: str, description: str, client_name: Optional[str] = None, client_ip: Optional[str] = None):
        """Record an activity or security event safely."""
        with self._lock:
            entry = {
                "id": len(self._logs) + 1,
                "timestamp": int(time.time()),
                "time_str": time.strftime("%H:%M:%S", time.localtime()),
                "event_type": event_type,
                "description": description,
                "client_name": client_name or "System",
                "client_ip": client_ip or "Local",
            }
            self._logs.insert(0, entry)
            if len(self._logs) > self._max_entries:
                self._logs.pop()

    def get_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent security activity logs."""
        with self._lock:
            return self._logs[:limit]

    def clear(self):
        """Clear log entries."""
        with self._lock:
            self._logs.clear()

# Global instance
audit_log = ActivityLogger()
