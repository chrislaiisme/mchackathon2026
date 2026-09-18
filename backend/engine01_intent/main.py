"""ENGINE01 FastAPI service: one sentence -> structured intent.

Run locally:
    uvicorn backend.engine01_intent.main:app --reload
"""

from __future__ import annotations

from dotenv import load_dotenv

# 一定要在 import 其他自家模組之前呼叫，因為 llm_client.py 有幾個模組層級的
# 常數是 import 當下就讀環境變數的（例如 CODEX_MODEL），load_dotenv() 沒先跑完，
# 那些常數就會讀到預設值，等於 .env 的設定沒生效。
load_dotenv()  # must run before importing modules that read env vars at import time (llm_client)

import os

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.engine01_intent import llm_client, session_store
from backend.shared import user_store
from backend.shared.auth import create_session_token, get_current_user, verify_google_id_token
from backend.shared.schemas import (
    AuthResponse,
    GoogleAuthRequest,
    IntentRequest,
    IntentResponse,
    ProfileUpdate,
    UserProfile,
)

app = FastAPI(title="ENGINE01 - Intent Understanding")

# Same origins as the Google OAuth Client ID's "Authorized JavaScript origins"
# (see CLAUDE.md "Google OAuth Client ID") -- the browser blocks the frontend's
# calls to this API otherwise, regardless of auth. Comma-separated env override
# for whatever port/domain a given frontend actually runs on.
# （CORS：瀏覽器預設不准網頁呼叫「不同來源」的 API，這裡明確允許哪些網址
# 可以呼叫這個後端，不然不管登入對不對，瀏覽器都會直接擋掉請求。）
_CORS_ORIGINS = os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/auth/google", response_model=AuthResponse)
def post_auth_google(request: GoogleAuthRequest) -> AuthResponse:
    # 步驟：驗證前端傳來的 Google ID token → 用 Google 帳號 sub 找或建立使用者
    # → 簽一個我們自己的 session token 回傳（後續請求都用這個 token，不用 Google 的）。
    claims = verify_google_id_token(request.id_token)
    profile = user_store.get_or_create_user(
        sub=claims["sub"],
        email=claims["email"],
        name=claims.get("name"),
        picture=claims.get("picture"),
    )
    return AuthResponse(session_token=create_session_token(profile.sub), profile=profile)


@app.get("/profile", response_model=UserProfile)
def get_profile(user: UserProfile = Depends(get_current_user)) -> UserProfile:
    # get_current_user 這個 dependency 已經驗證過登入、拿到使用者資料了，
    # 這裡不用再做任何事，直接回傳即可。
    return user


@app.put("/profile", response_model=UserProfile)
def put_profile(
    update: ProfileUpdate, user: UserProfile = Depends(get_current_user)
) -> UserProfile:
    # 只更新前端有明確傳值的欄位（不是 None 的），沒傳的欄位保持原樣，
    # 這樣「略過」偏好調查時只送 onboarding_completed=True 也不會把其他欄位洗成空的。
    if update.age_range is not None:
        user.age_range = update.age_range
    if update.style_preferences is not None:
        user.style_preferences = update.style_preferences
    if update.onboarding_completed is not None:
        user.onboarding_completed = update.onboarding_completed
    user_store.save_user(user)
    return user


@app.post("/intent", response_model=IntentResponse)
def post_intent(
    request: IntentRequest, user: UserProfile = Depends(get_current_user)
) -> IntentResponse:
    # 核心流程：拿這個使用者、這個 session 目前累積的意圖 → 丟給 codex exec
    # 併入這一輪新說的話 → 把更新後的意圖存回去 → 回傳給前端。
    state = session_store.get_or_create(user.sub, request.session_id)
    extraction = llm_client.extract_intent(request.message, state.intent)

    state.intent = extraction.intent
    state.round += 1
    session_store.save(user.sub, state)

    return IntentResponse(
        session_id=state.session_id,
        round=state.round,
        intent=state.intent,
        clarifying_questions=extraction.clarifying_questions,
    )


@app.get("/health")
def health() -> dict[str, str]:
    # 純粹給人／監控工具確認服務有沒有活著，不需要登入。
    return {"status": "ok"}
