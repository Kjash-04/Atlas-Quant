"""
In-process sliding-window rate limiter for order submissions.
Thread-safe, isolated per API key, configurable window and request counts.
"""

from __future__ import annotations

import threading
import time
from typing import Dict, List, Optional, Tuple


class SlidingWindowRateLimiter:
    def __init__(self, max_requests: int = 10, window_sec: int = 60):
        self.max_requests = max_requests
        self.window_sec = window_sec
        self._history: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    def check(
        self,
        key: str,
        max_requests: Optional[int] = None,
        window_sec: Optional[int] = None,
    ) -> Tuple[bool, int]:
        """
        Evaluates sliding-window allowance for the given key.
        Returns: (is_allowed: bool, retry_after_sec: int)
        """
        max_req = max_requests if max_requests is not None else self.max_requests
        win = window_sec if window_sec is not None else self.window_sec
        now = time.time()
        cutoff = now - win

        with self._lock:
            timestamps = self._history.get(key, [])
            timestamps = [t for t in timestamps if t > cutoff]

            if len(timestamps) >= max_req:
                oldest = timestamps[0]
                retry_after = max(1, int(oldest + win - now) + 1)
                self._history[key] = timestamps
                return False, retry_after

            timestamps.append(now)
            self._history[key] = timestamps
            return True, 0

    def allow_request(
        self,
        key: str,
        max_requests: Optional[int] = None,
        window_sec: Optional[int] = None,
    ) -> bool:
        """Convenience method returning boolean allowance."""
        allowed, _ = self.check(key, max_requests=max_requests, window_sec=window_sec)
        return allowed

    def reset(self, key: Optional[str] = None) -> None:
        """Clears request history for testing."""
        with self._lock:
            if key is not None:
                self._history.pop(key, None)
            else:
                self._history.clear()


order_rate_limiter = SlidingWindowRateLimiter()

