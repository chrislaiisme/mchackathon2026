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

# session token 效期：7 天，比 Google ID token 的約 1 小時長很多，
# 這樣前端登入一次之後不用一直處理 Google 那邊的 token 過期／refresh 流程。
_SESSION_TOKEN_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days
# DEV_BYPASS_AUTH 開啟時，所有請求都當成這個固定帳號登入，方便本機測試。
_DEV_USER_SUB = "dev-local-user"


def _session_secret() -> bytes:
    # 簽 session token 用的密鑰，從環境變數讀，沒設定就直接噴錯，
    # 因為沒有這把密鑰，簽出來的 token 就沒有安全性可言。
    secret = os.environ.get("SESSION_SECRET")
    if not secret:
        raise RuntimeError(
            "SESSION_SECRET is not set -- copy .env.example to .env and fill it "
            "in with any random string (used to sign session tokens)."
        )
    return secret.encode("utf-8")


# 下面兩個是 URL-safe base64 編碼／解碼的小工具，用來把二進位的簽章／payload
# 轉成可以放進 HTTP header 的純文字字串；去掉補齊用的 "=" 是因為那個字元
# 在網址／header 裡不一定安全，解碼時再自己補回來就好。
def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def verify_google_id_token(token: str) -> dict:
    """Verify a Google Identity Services credential and return its claims
    (sub, email, name, picture). Raises ValueError on any invalid token."""
    # GOOGLE_CLIENT_ID 是拿來檢查這個 token 的 audience 是不是「我們的」應用程式
    # 簽發的，不是隨便一個 Google 登入的 token 都能通過驗證。
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    if not client_id:
        raise RuntimeError(
            "GOOGLE_CLIENT_ID is not set -- see CLAUDE.md for how to create one "
            "in Google Cloud Console, then put it in .env."
        )
    # 這行會連去 Google 公開的簽章金鑰驗證 JWT 簽章、audience、有效期，
    # 驗證失敗會直接丟例外，不需要我們自己再檢查一次。
    return google_id_token.verify_oauth2_token(token, google_requests.Request(), client_id)


def create_session_token(sub: str) -> str:
    # 自己簽一個 session token：內容是 { sub, exp } 這組 JSON，
    # 用 HMAC-SHA256 簽章防止被竄改，格式是「payload.簽章」用點分隔。
    payload = {"sub": sub, "exp": int(time.time()) + _SESSION_TOKEN_TTL_SECONDS}
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(_session_secret(), payload_bytes, hashlib.sha256).digest()
    return f"{_b64encode(payload_bytes)}.{_b64encode(signature)}"


def verify_session_token(token: str) -> str:
    """Return the token's `sub` if valid, otherwise raise ValueError."""
    # 先把 token 拆成 payload 跟簽章兩段，格式不對（例如沒有「.」）就直接算驗證失敗。
    try:
        payload_b64, signature_b64 = token.split(".", 1)
        payload_bytes = _b64decode(payload_b64)
        signature = _b64decode(signature_b64)
    except Exception as exc:
        raise ValueError("malformed session token") from exc

    # 重新算一次簽章，跟 token 帶來的簽章比對；用 compare_digest 而不是 `==`
    # 是為了避免 timing attack（一般字串比較的時間長短可能洩漏訊息）。
    expected_signature = hmac.new(_session_secret(), payload_bytes, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected_signature):
        raise ValueError("bad session token signature")

    # 簽章沒問題，再檢查有沒有過期。
    payload = json.loads(payload_bytes)
    if payload.get("exp", 0) < time.time():
        raise ValueError("session token expired")
    return payload["sub"]


def _dev_bypass_enabled() -> bool:
    # .env 裡的 DEV_BYPASS_AUTH 開關，只接受字面值 "true"（大小寫不拘），其餘一律當 false。
    return os.environ.get("DEV_BYPASS_AUTH", "").lower() == "true"


def get_current_user(authorization: Optional[str] = Header(default=None)) -> UserProfile:
    """FastAPI dependency: resolve the calling UserProfile from the
    `Authorization: Bearer <session token>` header. 401s on anything invalid.

    DEV_BYPASS_AUTH=true skips all of this and returns a fixed local dev
    user -- convenient for testing without a real Google login, never for
    the actual demo."""
    # 開發模式：直接回傳（或建立）一個固定的本機測試帳號，完全不驗證 token。
    if _dev_bypass_enabled():
        return load_user(_DEV_USER_SUB) or get_or_create_user(
            _DEV_USER_SUB, email="dev@localhost", name="Dev User", picture=None
        )

    # 正式流程：一定要帶 `Authorization: Bearer <token>`，格式或內容不對都回 401。
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = authorization.removeprefix("Bearer ").strip()
    try:
        sub = verify_session_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired session token") from exc

    # token 驗證通過，但如果對應的使用者檔案不存在（理論上不該發生），一樣視為未登入。
    profile = load_user(sub)
    if profile is None:
        raise HTTPException(status_code=401, detail="Unknown user")
    return profile
