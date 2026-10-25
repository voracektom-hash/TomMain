"""Login sessions (signed cookie, valid one year) and brute-force protection."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import threading
import time
from collections import defaultdict, deque

from hlidac import db

COOKIE = "hlidac_session"
SESSION_DAYS = 365
MAX_FAILURES = 5
LOCKOUT_S = 15 * 60


def secret_key(conn: sqlite3.Connection) -> bytes:
    """SECRET_KEY from .env, otherwise one generated once and kept in the database."""
    env = os.environ.get("SECRET_KEY")
    if env:
        return env.encode()
    key = db.get_meta(conn, "secret_key")
    if key is None:
        key = secrets.token_hex(32)
        db.set_meta(conn, "secret_key", key)
    return key.encode()


def _sign(key: bytes, payload: str) -> str:
    return hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()


def make_session(key: bytes, user_id: int, now: float | None = None) -> str:
    expires = int((now or time.time()) + SESSION_DAYS * 86400)
    payload = f"{user_id}.{expires}"
    return f"{payload}.{_sign(key, payload)}"


def read_session(key: bytes, value: str | None, now: float | None = None) -> int | None:
    """User id from a valid, unexpired cookie, else None."""
    if not value:
        return None
    try:
        user_id, expires, sig = value.split(".")
        if not hmac.compare_digest(sig, _sign(key, f"{user_id}.{expires}")):
            return None
        if int(expires) < (now or time.time()):
            return None
        return int(user_id)
    except ValueError:
        return None


class LoginLimiter:
    """At most MAX_FAILURES wrong passwords per IP within LOCKOUT_S."""

    def __init__(self, max_failures: int = MAX_FAILURES, window_s: int = LOCKOUT_S):
        self.max_failures = max_failures
        self.window_s = window_s
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, ip: str, now: float) -> deque[float]:
        q = self._failures[ip]
        while q and q[0] < now - self.window_s:
            q.popleft()
        return q

    def blocked(self, ip: str, now: float | None = None) -> bool:
        with self._lock:
            return len(self._prune(ip, now or time.time())) >= self.max_failures

    def fail(self, ip: str, now: float | None = None) -> None:
        with self._lock:
            now = now or time.time()
            self._prune(ip, now).append(now)

    def reset(self, ip: str) -> None:
        with self._lock:
            self._failures.pop(ip, None)
