"""ENGINE01 FastAPI service: one sentence -> structured intent.

Run locally:
    uvicorn backend.engine01_intent.main:app --reload
"""

from __future__ import annotations

from fastapi import FastAPI

from backend.engine01_intent import llm_client, session_store
from backend.shared.schemas import IntentRequest, IntentResponse

app = FastAPI(title="ENGINE01 - Intent Understanding")


@app.post("/intent", response_model=IntentResponse)
def post_intent(request: IntentRequest) -> IntentResponse:
    state = session_store.get_or_create(request.session_id)
    extraction = llm_client.extract_intent(request.message, state.intent)

    state.intent = extraction.intent
    state.round += 1
    session_store.save(state)

    return IntentResponse(
        session_id=state.session_id,
        round=state.round,
        intent=state.intent,
        clarifying_questions=extraction.clarifying_questions,
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
