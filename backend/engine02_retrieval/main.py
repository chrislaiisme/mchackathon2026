"""ENGINE 02 as the team framework expects it: `Intent` in, `RetrievalResult` out.

This is the thin service layer. The implementation is the `engine02` package at the repo root and
it deliberately stays there: `engine02/{api,compat_ot,complete_look,llm}.py` resolve their data
paths with `ROOT = Path(__file__).resolve().parents[1]`, so moving the package would break every
default `data/catalog/...` path, 14 test files, 40+ scripts and the published JSON Schemas. What
the team actually depends on is the HTTP seam, and that is what this file provides.

    uvicorn backend.engine02_retrieval.main:app --port 8002     # run from the repo root

Endpoints:
    POST /retrieve   ENGINE 01's Intent  →  RetrievalResult (docs/interface-contract.md)
    GET  /health     catalog, encoder, warm-up state
    /engine02/*      the full ENGINE 02 API, mounted unchanged (22 endpoints: /rank, /view,
                     /facets, /complete-look, /visual-search, the gap panels, ...)

Two things this file is careful about:

* **It never imports `backend.shared.auth` at module level.** That module raises RuntimeError when
  SESSION_SECRET is unset, which would take down every test on a machine without a .env. Auth is
  resolved lazily and is optional: with no auth configured the service still runs, which is what a
  demo machine needs.
* **`concept_image` is left null.** It belongs to `backend/generation/`. The team's
  `RetrievalResult` currently declares it required — see README.md here for the one-line change
  that makes this response validate, and why we are not fabricating an image to satisfy a type.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ValidationError

ROOT = Path(__file__).resolve().parents[2]

# Starlette runs the lifespan of the OUTER app only: a mounted sub-app never starts, so the
# engine would never load and every call would KeyError on an empty STATE. Reuse ENGINE 02's own
# lifespan here, which builds the engine, loads the OutfitTransformer heads and runs the warm-up.
from engine02.api import lifespan as engine02_lifespan  # noqa: E402

app = FastAPI(title="ENGINE 02 — retrieval, ranking and faithful explanation",
              description=__doc__, lifespan=engine02_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.environ.get("CORS_ALLOWED_ORIGINS", "*").split(",") if o.strip()],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)


def _engine_app():
    """The ENGINE 02 FastAPI app, imported lazily so this module is cheap to import."""
    from engine02.api import app as engine02_app

    return engine02_app


def optional_user(request: Request) -> dict | None:
    """Resolve the caller when the team's auth is configured; never require it.

    `backend/shared/auth.py` raises RuntimeError without SESSION_SECRET, so it is imported inside
    the function and any failure means "anonymous", not 500. When a user IS resolved, their id
    namespaces the session, which stops two judges on the same laptop sharing one feedback ledger.
    """
    token = (request.headers.get("authorization") or "").removeprefix("Bearer ").strip()
    if not token:
        return None
    try:
        from backend.shared.auth import decode_session_token  # type: ignore

        return decode_session_token(token)
    except Exception:
        return None


class RetrieveRequest(BaseModel):
    session_id: str = "engine01"
    round: int = 0
    message: str | None = None
    intent: dict = {}
    prev_intent: dict | None = None
    feedback: dict | None = None
    top_k: int = 5
    arm: str | None = None
    context: dict | None = None      # ContextInput: city/lat/lon/event_date/commute/mood/...


@app.post("/retrieve")
def retrieve(body: RetrieveRequest, request: Request) -> dict:
    """ENGINE 01 → ENGINE 02 → the team's `RetrievalResult`.

    The cross-engine translation (Chinese free text → this catalog's vocabulary, inferred fields
    kept soft, unusable constraints reported rather than dropped) lives in
    `engine02/intent_adapter.py` and is covered by tests that use ENGINE 01's own fixtures.
    """
    from engine02.api import engine, rank
    from engine02.config import ARMS
    from engine02.intent_adapter import intent_to_request, response_to_retrieval_result

    user = optional_user(request)
    session_id = f"{user['sub']}:{body.session_id}" if user and user.get("sub") else body.session_id

    e = engine()
    arm = body.arm or os.environ.get("ENGINE02_ARM", "full_zclip3")
    if arm not in ARMS:
        raise HTTPException(400, f"unknown arm {arm!r}; see GET /engine02/arms")

    req, unresolved = intent_to_request(
        body.intent, session_id=session_id, round=body.round, message=body.message,
        catalog_name=getattr(e.catalog, "name", None), catalog_items=e.catalog.items,
        top_k=body.top_k, arm=arm, feedback=body.feedback)
    if body.context:
        # the shopper's situation (weather, festival, commute, mood ...) rides along with the
        # intent; malformed context is a 422 naming the field, never silently dropped
        from engine02.contracts import ContextInput
        try:
            req.context = ContextInput(**body.context)
        except ValidationError as exc:
            raise HTTPException(422, {"error": "context is not a valid ContextInput",
                                      "detail": exc.errors(include_url=False)})
    prev_req = None
    if body.prev_intent:
        prev_req, _ = intent_to_request(
            body.prev_intent, session_id=session_id, round=max(0, body.round - 1),
            catalog_name=getattr(e.catalog, "name", None), catalog_items=e.catalog.items,
            top_k=body.top_k, arm=arm)

    ledger, rejected = [], []
    if isinstance(body.feedback, dict) and body.feedback.get("ops"):
        # ENGINE 03 speaks in ops; applying them here means the orchestrator never has to know
        # that /handshake exists (it still does, for callers that want the ledger alone).
        from engine02.handshake import FeedbackRound, apply_round

        fr = FeedbackRound.model_validate({"session_id": req.session_id,
                                           "round": max(0, body.round - 1), **body.feedback})
        applied = apply_round(req, None, fr, kansei=e.kansei,
                              gain=ARMS[arm].adjust_gain)
        req, ledger, rejected = applied.request, applied.ledger, applied.rejected_ops
        req.round, req.options.top_k = body.round, body.top_k

    resp = rank(req)
    out = response_to_retrieval_result(e, req, resp, arm=arm, prev_req=prev_req)
    out["engine02"]["unresolved_from_intent"] = unresolved
    out["engine02"]["authenticated"] = bool(user)
    if ledger or rejected:
        out["engine02"]["feedback_ledger"] = [entry.model_dump() for entry in ledger]
        out["engine02"]["rejected_ops"] = rejected
    return out


@app.get("/health")
def health() -> dict:
    from engine02.api import health as engine02_health

    h = engine02_health()
    return {**h, "service": "engine02_retrieval",
            "auth": "optional (set SESSION_SECRET to namespace sessions per user)"}


app.mount("/engine02", _engine_app())
