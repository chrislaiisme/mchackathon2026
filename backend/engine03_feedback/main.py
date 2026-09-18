"""FastAPI application for ENGINE 03.

Run from the repository root:
    uvicorn backend.engine03_feedback.main:app --reload --port 8003
"""

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.shared.auth import get_current_user
from backend.shared.schemas import UserProfile

from .contracts import CONTRACT_VERSION, Engine3Request, Engine3Response, FeedbackRound
from .service import process_feedback


app = FastAPI(
    title="ENGINE 03 — preference feedback",
    description="FeedbackInput + ENGINE 02 context → FeedbackRound + updated ENGINE 01 Intent",
    version=CONTRACT_VERSION,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "contract_version": CONTRACT_VERSION}


@app.get("/contract/engine02-feedback")
def engine02_feedback_contract() -> dict:
    return FeedbackRound.model_json_schema()


@app.post("/feedback", response_model=Engine3Response)
@app.post("/api/engine3/process_feedback", response_model=Engine3Response, include_in_schema=False)
def post_feedback(
    request: Engine3Request,
    _user: UserProfile = Depends(get_current_user),
) -> Engine3Response:
    try:
        return process_feedback(request)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"ENGINE 03 failed: {type(exc).__name__}: {exc}") from exc
