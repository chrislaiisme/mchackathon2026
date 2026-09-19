"""BFF — 一輪對話的流程控制。

前端只跟這裡講話，由這裡依序呼叫三個引擎：

    POST /round      一句話 → ENGINE 01 抽意圖 → ENGINE 02 檢索排序 → 回傳這一輪結果
    POST /feedback   回饋 → ENGINE 03 轉換 → 帶著回饋重跑 ENGINE 02 → 回傳下一輪結果

流程由程式決定，不交給模型判斷；每一步都記進 activity，前端的「Agent 活動紀錄」和
demo 時要回答「這個結果怎麼來的」都靠它。
"""
from __future__ import annotations

import os
import time
from typing import Any, Literal, Optional

import httpx
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

ENGINE01_URL = os.environ.get("ENGINE01_URL", "http://127.0.0.1:8000")
ENGINE02_URL = os.environ.get("ENGINE02_URL", "http://127.0.0.1:8002")
ENGINE03_URL = os.environ.get("ENGINE03_URL", "http://127.0.0.1:8003")
# ENGINE 01 走 codex exec，比另外兩個慢得多，逾時要拉開。
TIMEOUT = float(os.environ.get("BFF_TIMEOUT", "120"))

app = FastAPI(title="IntentWeave BFF")
_CORS_ORIGINS = os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware, allow_origins=[o.strip() for o in _CORS_ORIGINS if o.strip()],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


class Session(BaseModel):
    session_id: str
    round: int = 0
    intent: dict[str, Any] = Field(default_factory=dict)
    prev_intent: Optional[dict[str, Any]] = None
    feedback: Optional[dict[str, Any]] = None       # ENGINE 03 上一輪的產出
    rounds: list[dict[str, Any]] = Field(default_factory=list)


_SESSIONS: dict[str, Session] = {}


def _post(url: str, payload: dict[str, Any], headers: Optional[dict[str, str]] = None) -> dict[str, Any]:
    """對下游 POST。測試會替換這個函式。"""
    with httpx.Client(timeout=TIMEOUT) as client:
        r = client.post(url, json=payload, headers=headers or {})
        r.raise_for_status()
        return r.json()


def _auth_headers(authorization: Optional[str]) -> dict[str, str]:
    """把前端的登入憑證原樣往下傳。ENGINE 01 的 /intent 要求登入，ENGINE 02 用它分隔 session。"""
    return {"Authorization": authorization} if authorization else {}


def _step(activity: list[dict[str, Any]], name: str, url: str, payload: dict[str, Any],
          headers: Optional[dict[str, str]] = None) -> dict[str, Any]:
    """呼叫一個下游並記帳；失敗時明確指出是哪一步斷的。"""
    t0 = time.time()
    try:
        out = _post(url, payload, headers)
    except Exception as exc:
        activity.append({"step": name, "url": url, "ms": int((time.time() - t0) * 1000),
                         "ok": False, "error": f"{type(exc).__name__}: {exc}"[:200]})
        raise HTTPException(502, f"{name} 失敗（{url}）：{type(exc).__name__}: {exc}"[:300])
    activity.append({"step": name, "url": url, "ms": int((time.time() - t0) * 1000), "ok": True})
    return out


def _retrieve(s: Session, activity: list[dict[str, Any]], message: Optional[str], top_k: int,
              headers: Optional[dict[str, str]] = None) -> dict[str, Any]:
    return _step(activity, "engine02.retrieve", f"{ENGINE02_URL}/retrieve", {
        "session_id": s.session_id, "round": s.round, "message": message,
        "intent": s.intent, "prev_intent": s.prev_intent,
        "feedback": s.feedback, "top_k": top_k}, headers)


class RoundRequest(BaseModel):
    session_id: Optional[str] = None
    message: str
    reference_image_url: Optional[str] = None
    top_k: int = 5


@app.post("/round")
def run_round(body: RoundRequest, authorization: Optional[str] = Header(default=None)) -> dict[str, Any]:
    """一句話 → 意圖 → 推薦。第一輪和後續輪次走同一條路。"""
    activity: list[dict[str, Any]] = []
    headers = _auth_headers(authorization)

    intent_out = _step(activity, "engine01.intent", f"{ENGINE01_URL}/intent", {
        "session_id": body.session_id, "message": body.message,
        "reference_image_url": body.reference_image_url}, headers)

    sid = intent_out.get("session_id") or body.session_id or "anonymous"
    s = _SESSIONS.get(sid) or Session(session_id=sid)
    s.prev_intent = s.intent or None
    s.intent = intent_out.get("intent") or {}
    s.round = int(intent_out.get("round") or s.round + 1)

    retrieval = _retrieve(s, activity, body.message, body.top_k, headers)

    result = {
        "session_id": sid, "round": s.round,
        "intent": s.intent,
        "clarifying_questions": intent_out.get("clarifying_questions") or [],
        "retrieval": retrieval,
        "feedback_applied": s.feedback,
        "activity": activity,
    }
    s.rounds.append(result)
    _SESSIONS[sid] = s
    return result


class FeedbackRequest(BaseModel):
    session_id: str
    round: int
    target: Literal["recommended", "generated"] = "recommended"
    attribute_scores: list[dict[str, Any]] = Field(default_factory=list)
    free_text: Optional[str] = None
    selected_option_id: Optional[str] = None
    shown_item_ids: list[str] = Field(default_factory=list)
    liked_item_ids: list[str] = Field(default_factory=list)
    disliked_item_ids: list[str] = Field(default_factory=list)
    top_k: int = 5


@app.post("/feedback")
def feedback(body: FeedbackRequest, authorization: Optional[str] = Header(default=None)) -> dict[str, Any]:
    """回饋 → ENGINE 03 → 帶著回饋重跑 ENGINE 02，直接回傳下一輪結果。

    這就是評審要看的「出題 → 回饋 → 再出題」：同一個意圖、多了一輪回饋，排序就該不同。
    """
    s = _SESSIONS.get(body.session_id)
    if s is None:
        raise HTTPException(404, f"session {body.session_id!r} 不存在，請先呼叫 /round")

    activity: list[dict[str, Any]] = []
    headers = _auth_headers(authorization)
    fb_out = _step(activity, "engine03.feedback", f"{ENGINE03_URL}/feedback",
                   body.model_dump(exclude={"top_k"}), headers)
    s.feedback = fb_out.get("feedback")
    s.round = int(fb_out.get("next_round") or s.round + 1)

    retrieval = _retrieve(s, activity, None, body.top_k, headers)

    result = {
        "session_id": s.session_id, "round": s.round,
        "intent": s.intent,
        "retrieval": retrieval,
        "feedback_applied": s.feedback,
        "ledger_entry": fb_out.get("ledger_entry"),
        "activity": activity,
    }
    s.rounds.append(result)
    return result


@app.get("/session/{session_id}")
def session(session_id: str) -> dict[str, Any]:
    s = _SESSIONS.get(session_id)
    if s is None:
        raise HTTPException(404, f"session {session_id!r} 不存在")
    return s.model_dump()


@app.get("/health")
def health() -> dict[str, Any]:
    """一次看三個引擎在不在，現場排查用。"""
    out: dict[str, Any] = {"status": "ok", "sessions": len(_SESSIONS), "downstream": {}}
    for name, url in (("engine01", ENGINE01_URL), ("engine02", ENGINE02_URL), ("engine03", ENGINE03_URL)):
        try:
            with httpx.Client(timeout=5) as client:
                out["downstream"][name] = {"url": url, "ok": client.get(f"{url}/health").status_code == 200}
        except Exception as exc:
            out["downstream"][name] = {"url": url, "ok": False, "error": type(exc).__name__}
            out["status"] = "degraded"
    return out
