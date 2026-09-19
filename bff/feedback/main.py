"""ENGINE 03 — 偏好回饋迴圈。

把前端的使用者回饋（分維度評分、自由文字、選了哪張卡）轉成 ENGINE 02 看得懂的
`FeedbackInput`，並保留一份跨輪次的帳本供可解釋性使用。

設計上的三個決定：

1. **送純 `FeedbackInput`，不自己算權重。** ENGINE 02 的 `feedback_from_engine03()`
   已經負責「屬性評分 → 設計軸 ±1 步」與「自由文字 → 否定詞」的轉換，而後者需要商品庫
   才能把「不要黑色」展開成整個色系。那份對應表只該存在一份。

2. **不可以混格式。** ENGINE 02 看到 `chosen_item_ids`、`design_adjust_steps` 這類欄位
   就判定「payload 已經是我方格式」而整包原樣放行，`attribute_scores` 會被靜默忽略。
   所以這裡只送 `FeedbackInput` 宣告的欄位。

3. **帳本留在這裡。** 每一輪收到什麼、送出什麼都記下來，前端的「Agent 活動紀錄」和
   demo 時要回答「這個偏好是哪一句話造成的」都靠它。

已知限制：`FeedbackInput` 沒有「不喜歡哪幾張卡」的欄位，所以倒讚只會進本地帳本，
不會傳給 ENGINE 02。要讓倒讚影響排序，需要與 ENGINE 02 擴充契約。
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from bff.shared.schemas import AttributeScore, FeedbackInput

app = FastAPI(title="ENGINE 03 — Preference Feedback Loop")

_CORS_ORIGINS = os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware, allow_origins=[o.strip() for o in _CORS_ORIGINS if o.strip()],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


class UIFeedback(BaseModel):
    """前端送過來的一輪回饋。比 `FeedbackInput` 多的欄位只進帳本，不會外送。"""

    session_id: str
    round: int
    target: Literal["recommended", "generated"] = "recommended"
    attribute_scores: list[AttributeScore] = Field(default_factory=list)
    free_text: Optional[str] = None
    selected_option_id: Optional[str] = None
    shown_item_ids: list[str] = Field(default_factory=list)
    liked_item_ids: list[str] = Field(default_factory=list)
    disliked_item_ids: list[str] = Field(default_factory=list)


class LedgerRow(BaseModel):
    at: str
    round: int
    target: str
    sent_to_engine02: dict[str, Any]
    kept_local: dict[str, Any]


_LEDGER: dict[str, list[LedgerRow]] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@app.post("/feedback")
def feedback(body: UIFeedback) -> dict[str, Any]:
    """一輪回饋 → 下一輪要放進 ENGINE 02 `/retrieve` 的 `feedback` 欄位。

    `selected_option_id` 沒給但有按讚時，取第一個按讚的當選擇，因為 `FeedbackInput`
    只容得下一個 chosen。
    """
    chosen = body.selected_option_id or (body.liked_item_ids[0] if body.liked_item_ids else None)
    payload = FeedbackInput(
        session_id=body.session_id, round=body.round, target=body.target,
        attribute_scores=body.attribute_scores, free_text=body.free_text,
        selected_option_id=chosen)
    sent = payload.model_dump(exclude_none=False)

    kept = {
        "shown_item_ids": body.shown_item_ids,
        "liked_item_ids": body.liked_item_ids,
        "disliked_item_ids": body.disliked_item_ids,
        "note": "FeedbackInput 沒有倒讚欄位，這些只留在帳本" if body.disliked_item_ids else "",
    }
    row = LedgerRow(at=_now(), round=body.round, target=body.target,
                    sent_to_engine02=sent, kept_local=kept)
    _LEDGER.setdefault(body.session_id, []).append(row)

    return {
        "feedback": sent,
        "ledger_entry": row.model_dump(),
        "rounds_recorded": len(_LEDGER[body.session_id]),
        "next_round": body.round + 1,
    }


@app.get("/session/{session_id}")
def session(session_id: str) -> dict[str, Any]:
    rows = _LEDGER.get(session_id)
    if rows is None:
        raise HTTPException(404, f"no feedback recorded for session {session_id!r}")
    return {"session_id": session_id, "rounds": [r.model_dump() for r in rows]}


@app.delete("/session/{session_id}")
def reset(session_id: str) -> dict[str, Any]:
    return {"session_id": session_id, "cleared": len(_LEDGER.pop(session_id, []))}


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "engine": "engine03", "sessions": len(_LEDGER)}
