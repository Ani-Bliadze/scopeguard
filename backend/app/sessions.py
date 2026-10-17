"""Local demo sessions. A persona is chosen through a localhost-only, explicitly labeled demo endpoint
and bound server-side to an opaque HttpOnly cookie. This is NOT production authentication."""

from __future__ import annotations

import hmac
import secrets
import threading
import time
import uuid
from dataclasses import dataclass

from backend.contracts import Principal, Role

COOKIE_NAME = "sg_session"
CSRF_HEADER = "x-csrf-token"


@dataclass
class DemoSession:
    session_id: str
    cookie_value: str
    csrf_token: str
    principal: Principal
    created_at: float
    access_paused: bool = False


class SessionStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_cookie: dict[str, DemoSession] = {}

    def create(self, role: Role) -> DemoSession:
        sid = uuid.uuid4().hex[:16]
        s = DemoSession(
            session_id=sid,
            cookie_value=secrets.token_urlsafe(32),
            csrf_token=secrets.token_urlsafe(24),
            principal=Principal(principal_id=f"demo-{role.value}-{sid[:6]}", role=role, session_id=sid),
            created_at=time.time(),
        )
        with self._lock:
            self._by_cookie[s.cookie_value] = s
        return s

    def get(self, cookie_value: str | None) -> DemoSession | None:
        if not cookie_value:
            return None
        with self._lock:
            return self._by_cookie.get(cookie_value)

    def drop(self, session: DemoSession) -> None:
        with self._lock:
            self._by_cookie.pop(session.cookie_value, None)

    def clear(self) -> None:
        with self._lock:
            self._by_cookie.clear()

    @staticmethod
    def csrf_ok(session: DemoSession, provided: str | None) -> bool:
        return bool(provided) and hmac.compare_digest(session.csrf_token, provided)
