"""FastAPI entry point for ENGINE 03."""

from __future__ import annotations

import os

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.shared.auth import get_current_user

from .attributes import frontend_attribute_catalog
from .contracts import Engine3Request, Engine3Response
from .service import process_feedback


app = FastAPI(title="ENGINE 03 — Structured Item Feedback", version="0.4.0")
_origins = os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in _origins if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/feedback", response_model=Engine3Response)
def feedback(body: Engine3Request, _user=Depends(get_current_user)) -> Engine3Response:
    return process_feedback(body)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "engine": "engine03", "contract_version": "0.4.0"}


@app.get("/attributes")
def attributes() -> dict:
    """Stable ids plus unambiguous Traditional-Chinese text for the frontend."""
    return frontend_attribute_catalog()
