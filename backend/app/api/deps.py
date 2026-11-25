"""FastAPI dependencies and lightweight admin authentication."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time

from fastapi import HTTPException, Request

from ..config import settings
from ..services.container import AppContainer

_RUNTIME_SECRET = secrets.token_urlsafe(32)
_TOKEN_TTL_SECONDS = 12 * 3600


def _signing_key() -> bytes:
    secret = settings.admin_token or settings.admin_password or _RUNTIME_SECRET
    return hashlib.sha256(f"krishivaani-admin:{secret}".encode("utf-8")).digest()


def create_admin_token(username: str) -> str:
    expires = int(time.time()) + _TOKEN_TTL_SECONDS
    payload = f"{username}:{expires}".encode("utf-8")
    sig = hmac.new(_signing_key(), payload, hashlib.sha256).hexdigest()
    raw = f"{username}:{expires}:{sig}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def verify_admin_token(token: str) -> str | None:
    token = (token or "").strip()
    if not token:
        return None
    if settings.admin_token and hmac.compare_digest(token, settings.admin_token):
        return settings.admin_username
    try:
        decoded = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        username, expires_str, sig = decoded.split(":", 2)
        if int(expires_str) < int(time.time()):
            return None
        payload = f"{username}:{expires_str}".encode("utf-8")
        expected = hmac.new(_signing_key(), payload, hashlib.sha256).hexdigest()
        if hmac.compare_digest(sig, expected):
            return username
    except Exception:
        return None
    return None


def _extract_token(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.headers.get("X-Admin-Token", "").strip()


def optional_admin(request: Request) -> str | None:
    return verify_admin_token(_extract_token(request))


def require_admin(request: Request) -> str:
    user = optional_admin(request)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Admin authentication required. Sign in via /api/admin/login or pass X-Admin-Token.",
        )
    return user


def get_services(request: Request) -> AppContainer:
    return request.app.state.services
