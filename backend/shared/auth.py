"""Auth: Google ID token verification + our own lightweight session tokens.

No database, no JWT library needed -- see CLAUDE.md "資料庫" for the no-DB
call and "ENGINE01 執行方式" for why this is unrelated to the `codex exec`
decision (that's model calls; this is "who is asking").

Login flow: the frontend's Google Sign-In button hands us an ID token once;
verify_google_id_token() checks it against Google's own keys (via the
`google-auth` package) and gives us the account's sub/email/name/picture.
We then mint our own session token (HMAC-signed, stdlib only, no extra
dependency) with a longer expiry than Google's ~1h ID token, so the frontend
doesn't have to deal with Google's own token refresh flow on every request.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Optional

from fastapi import Header, HTTPException
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from backend.shared.schemas import UserProfile
from backend.shared.user_store import get_or_create_user, load_user

_SESSION_TOKEN_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days
_DEV_USER_SUB = "dev-local-user"


def _session_secret() -> bytes:
    secret = os.environ.get("SESSION_SECRET")
    if not secret:
        raise RuntimeError(
            "SESSION_SECRET is not set -- copy .env.example to .env and fill it "
            "in with any random string (used to sign session tokens)."
        )
    return secret.encode("utf-8")


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def verify_google_id_token(token: str) -> dict:
    """Verify a Google Identity Services credential and return its claims
    (sub, email, name, picture). Raises ValueError on any invalid token."""
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    if not client_id:
        raise RuntimeError(
            "GOOGLE_CLIENT_ID is not set -- see CLAUDE.md for how to create one "
            "in Google Cloud Console, then put it in .env."
        )
    return google_id_token.verify_oauth2_token(token, google_requests.Request(), client_id)


def create_session_token(sub: str) -> str:
    payload = {"sub": sub, "exp": int(time.time()) + _SESSION_TOKEN_TTL_SECONDS}
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(_session_secret(), payload_bytes, hashlib.sha256).digest()
    return f"{_b64encode(payload_bytes)}.{_b64encode(signature)}"


def verify_session_token(token: str) -> str:
    """Return the token's `sub` if valid, otherwise raise ValueError."""
    try:
        payload_b64, signature_b64 = token.split(".", 1)
        payload_bytes = _b64decode(payload_b64)
        signature = _b64decode(signature_b64)
    except Exception as exc:
        raise ValueError("malformed session token") from exc

    expected_signature = hmac.new(_session_secret(), payload_bytes, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected_signature):
        raise ValueError("bad session token signature")

    payload = json.loads(payload_bytes)
    if payload.get("exp", 0) < time.time():
        raise ValueError("session token expired")
    return payload["sub"]


def _dev_bypass_enabled() -> bool:
    return os.environ.get("DEV_BYPASS_AUTH", "").lower() == "true"


def get_current_user(authorization: Optional[str] = Header(default=None)) -> UserProfile:
    """FastAPI dependency: resolve the calling UserProfile from the
    `Authorization: Bearer <session token>` header. 401s on anything invalid.

    DEV_BYPASS_AUTH=true skips all of this and returns a fixed local dev
    user -- convenient for testing without a real Google login, never for
    the actual demo."""
    if _dev_bypass_enabled():
        return load_user(_DEV_USER_SUB) or get_or_create_user(
            _DEV_USER_SUB, email="dev@localhost", name="Dev User", picture=None
        )

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = authorization.removeprefix("Bearer ").strip()
    try:
        sub = verify_session_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired session token") from exc

    profile = load_user(sub)
    if profile is None:
        raise HTTPException(status_code=401, detail="Unknown user")
    return profile
