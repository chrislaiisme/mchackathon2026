"""ENGINE01 FastAPI service: one sentence -> structured intent.

Run locally:
    uvicorn backend.engine01_intent.main:app --reload
"""

from __future__ import annotations

from dotenv import load_dotenv

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
    return user


@app.put("/profile", response_model=UserProfile)
def put_profile(
    update: ProfileUpdate, user: UserProfile = Depends(get_current_user)
) -> UserProfile:
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
    return {"status": "ok"}
