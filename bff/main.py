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
from typing import Any, Optional

import httpx
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator

from bff.images.concept import GENERATED_ROOT, ConceptImageUnavailable, generate_concepts

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
    shown_item_ids: list[str] = Field(default_factory=list)  # ENGINE 02 上輪實際展示的商品
    shown_generated_item_ids: list[str] = Field(default_factory=list)
    generated_items: dict[str, dict[str, Any]] = Field(default_factory=dict)
    feedback_rounds: list[dict[str, Any]] = Field(default_factory=list)  # 最近三輪的 ENGINE 03 原始輸入
    utterance: str = ""                             # 使用者最近說的那句原話（生圖要用）
    concept_image: Optional[dict[str, Any]] = None  # 最近一次生成的單品圖
    rounds: list[dict[str, Any]] = Field(default_factory=list)


_SESSIONS: dict[str, Session] = {}


def _post(url: str, payload: dict[str, Any], headers: Optional[dict[str, str]] = None) -> dict[str, Any]:
    """對下游 POST。測試會替換這個函式。"""
    with httpx.Client(timeout=TIMEOUT) as client:
        r = client.post(url, json=payload, headers=headers or {})
        r.raise_for_status()
        return r.json()


def _get(url: str, headers: Optional[dict[str, str]] = None) -> dict[str, Any]:
    with httpx.Client(timeout=TIMEOUT) as client:
        r = client.get(url, headers=headers or {})
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


def _shown_item_ids(retrieval: dict[str, Any]) -> list[str]:
    """Extract the exact slate returned by ENGINE 02; never trust the browser to reconstruct it."""
    ids: list[str] = []
    for product in retrieval.get("products") or []:
        item_id = product.get("product_id") or product.get("item_id")
        if item_id is not None:
            value = str(item_id)
            if value not in ids:
                ids.append(value)
    return ids


def _register_generated_items(s: Session, generated: dict[str, Any]) -> dict[str, Any]:
    """Give generated cells stable ids and retain trusted variant metadata server-side."""
    shown: list[str] = []
    for cell in generated.get("cells") or []:
        index = cell.get("index")
        if index is None:
            continue
        item_id = f"generated:{s.session_id}:r{s.round}:cell-{index}"
        cell["generated_item_id"] = item_id
        cell["source"] = "generated"
        s.generated_items[item_id] = {
            "item_id": item_id,
            "round": s.round,
            "image_url": cell.get("image_url"),
            "design_attributes": dict(cell.get("design_attributes") or {}),
        }
        shown.append(item_id)
    s.shown_generated_item_ids = shown
    return generated


def _trusted_item_feedbacks(s: Session, raw_feedbacks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Inject generated metadata from the session; never trust browser-supplied attributes."""
    trusted: list[dict[str, Any]] = []
    for raw in raw_feedbacks:
        item = dict(raw)
        source = str(item.get("source") or "catalog")
        item_id = str(item.get("item_id") or "")
        if source == "catalog":
            item["source"] = "catalog"
            item.pop("design_attributes", None)
        elif source == "generated":
            generated = s.generated_items.get(item_id)
            if generated is None or item_id not in s.shown_generated_item_ids:
                raise HTTPException(422, f"generated item {item_id!r} was not shown this round")
            item["source"] = "generated"
            item["design_attributes"] = dict(generated.get("design_attributes") or {})
        else:
            raise HTTPException(422, f"unknown feedback source {source!r}")
        trusted.append(item)
    return trusted


def _trusted_outfit_feedbacks(s: Session, raw_feedbacks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Inject trusted generated metadata into each outfit member."""

    trusted: list[dict[str, Any]] = []
    for raw_outfit in raw_feedbacks:
        outfit = dict(raw_outfit)
        trusted_items: list[dict[str, Any]] = []
        for raw_item in outfit.get("items") or []:
            item = dict(raw_item)
            source = str(item.get("source") or "catalog")
            item_id = str(item.get("item_id") or "")
            if source == "catalog":
                item["source"] = "catalog"
                item.pop("design_attributes", None)
            elif source == "generated":
                generated = s.generated_items.get(item_id)
                if generated is None or item_id not in s.shown_generated_item_ids:
                    raise HTTPException(422, f"generated outfit item {item_id!r} was not shown this round")
                item["source"] = "generated"
                item["design_attributes"] = dict(generated.get("design_attributes") or {})
            else:
                raise HTTPException(422, f"unknown outfit item source {source!r}")
            trusted_items.append(item)
        outfit["items"] = trusted_items
        trusted.append(outfit)
    return trusted


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
    s.utterance = body.message
    s.prev_intent = s.intent or None
    s.intent = intent_out.get("intent") or {}
    s.round = int(intent_out.get("round") or s.round + 1)

    retrieval = _retrieve(s, activity, body.message, body.top_k, headers)
    s.shown_item_ids = _shown_item_ids(retrieval)
    s.shown_generated_item_ids = []

    result = {
        "session_id": sid, "round": s.round,
        "intent": s.intent,
        "clarifying_questions": intent_out.get("clarifying_questions") or [],
        "retrieval": retrieval,
        "concept_image": s.concept_image,
        "feedback_applied": s.feedback,
        # 目錄給不出使用者要的東西時才值得按「生成單品」，前端拿這個決定按鈕要不要亮。
        "concept_image_suggested": bool(
            ((retrieval.get("engine02") or {}).get("match_score_detail") or {}).get("relaxed")),
        "activity": activity,
    }
    s.rounds.append(result)
    _SESSIONS[sid] = s
    return result


class FeedbackRequest(BaseModel):
    session_id: str
    round: int
    item_feedbacks: list[dict[str, Any]] = Field(default_factory=list)
    outfit_feedbacks: list[dict[str, Any]] = Field(default_factory=list)
    top_k: int = 5

    @model_validator(mode="after")
    def validate_actions(self) -> "FeedbackRequest":
        if not self.item_feedbacks and not self.outfit_feedbacks:
            raise ValueError("feedback must contain item_feedbacks or outfit_feedbacks")
        return self


@app.post("/feedback")
def feedback(body: FeedbackRequest, authorization: Optional[str] = Header(default=None)) -> dict[str, Any]:
    """回饋 → ENGINE 03 → 帶著回饋重跑 ENGINE 02，直接回傳下一輪結果。

    這就是評審要看的「出題 → 回饋 → 再出題」：同一個意圖、多了一輪回饋，排序就該不同。
    """
    s = _SESSIONS.get(body.session_id)
    if s is None:
        raise HTTPException(404, f"session {body.session_id!r} 不存在，請先呼叫 /round")
    if body.round != s.round:
        raise HTTPException(409, f"feedback round {body.round} 與目前 round {s.round} 不一致")
    if not s.shown_item_ids and not s.shown_generated_item_ids:
        raise HTTPException(409, "上一輪沒有可供回饋的商品或生成圖")

    activity: list[dict[str, Any]] = []
    headers = _auth_headers(authorization)
    trusted_feedbacks = _trusted_item_feedbacks(s, body.item_feedbacks)
    trusted_outfits = _trusted_outfit_feedbacks(s, body.outfit_feedbacks)
    current_feedback_round = {
        "round": s.round,
        "shown_item_ids": s.shown_item_ids,
        "shown_generated_item_ids": s.shown_generated_item_ids,
        "item_feedbacks": trusted_feedbacks,
        "outfit_feedbacks": trusted_outfits,
    }
    engine3_payload = {
        "session_id": s.session_id,
        "previous_rounds": s.feedback_rounds[-3:],
        **current_feedback_round,
    }
    fb_out = _step(activity, "engine03.feedback", f"{ENGINE03_URL}/feedback",
                   engine3_payload, headers)
    engine02_feedback = fb_out.get("engine02_feedback")
    if not isinstance(engine02_feedback, dict):
        raise HTTPException(502, "engine03.feedback 缺少 engine02_feedback")

    # Work on a copy so a failed ENGINE 02 call does not leave the session half-advanced.
    next_session = s.model_copy(deep=True)
    next_session.feedback = engine02_feedback
    next_session.feedback_rounds = (s.feedback_rounds + [current_feedback_round])[-3:]
    next_session.round = s.round + 1
    retrieval = _retrieve(next_session, activity, None, body.top_k, headers)
    next_session.shown_item_ids = _shown_item_ids(retrieval)
    next_session.shown_generated_item_ids = []

    result = {
        "session_id": next_session.session_id, "round": next_session.round,
        "intent": next_session.intent,
        "retrieval": retrieval,
        "concept_image": next_session.concept_image,
        "feedback_applied": next_session.feedback,
        "attribute_evidence": fb_out.get("attribute_evidence") or [],
        "generated_attribute_evidence": fb_out.get("generated_attribute_evidence") or [],
        "outfit_evidence": fb_out.get("outfit_evidence") or [],
        "activity": activity,
    }
    next_session.rounds.append(result)
    _SESSIONS[next_session.session_id] = next_session
    return result


class ConceptImageRequest(BaseModel):
    session_id: str
    cells: int = 6
    model: Optional[str] = None
    """生圖模型，省略用 generate_grid.py 的預設。"""
    dry_run: bool = False
    """只組 prompt 與 manifest，不生圖、不花額度。開發時先用這個。"""


@app.post("/concept-image")
def concept_image(body: ConceptImageRequest) -> dict[str, Any]:
    """使用者對檢索結果不滿意時，一次生六件新單品讓他挑。

    明確觸發，不在每一輪自動跑：一張六宮格 26–48 秒。六件擠在一張圖裡生，
    比逐一生成快三倍多，理由見 bff/images/concept.py。
    """
    s = _SESSIONS.get(body.session_id)
    if s is None or not s.rounds:
        raise HTTPException(404, f"session {body.session_id!r} 還沒有任何一輪結果")
    if not s.intent:
        raise HTTPException(409, "這個 session 還沒有結構化意圖，無法生圖")

    activity: list[dict[str, Any]] = []
    t0 = time.time()
    try:
        out = generate_concepts(s.session_id, s.round, s.intent,
                                cells=body.cells, model=body.model, dry_run=body.dry_run)
    except ConceptImageUnavailable as exc:
        activity.append({"step": "images.concepts", "ms": int((time.time() - t0) * 1000),
                         "ok": False, "error": str(exc)[:200]})
        raise HTTPException(502, f"生成單品失敗：{exc}")
    except Exception as exc:
        raise HTTPException(502, f"生成單品失敗：{type(exc).__name__}: {exc}"[:300])

    activity.append({"step": "images.concepts", "ms": int((time.time() - t0) * 1000), "ok": True})
    if not body.dry_run:
        out = _register_generated_items(s, out)
    s.concept_image = {"image_url": out.get("grid_image"), "prompt_used": out.get("prompt_used"),
                       "response_id": None,
                       "generated_item_ids": list(s.shown_generated_item_ids)}
    return {"session_id": s.session_id, "round": s.round, "concepts": out, "activity": activity}


@app.get("/generated/{path:path}")
def generated_image(path: str) -> FileResponse:
    """把生成的圖給前端。解析後必須仍在 data/generated 底下，擋住 ../ 之類的路徑。"""
    target = (GENERATED_ROOT / path).resolve()
    if not target.is_relative_to(GENERATED_ROOT.resolve()):
        raise HTTPException(400, "路徑不合法")
    if not target.is_file():
        raise HTTPException(404, f"找不到 {path}")
    return FileResponse(target)


@app.get("/session/{session_id}")
def session(session_id: str) -> dict[str, Any]:
    s = _SESSIONS.get(session_id)
    if s is None:
        raise HTTPException(404, f"session {session_id!r} 不存在")
    return s.model_dump()


@app.get("/feedback/attributes")
def feedback_attributes(authorization: Optional[str] = Header(default=None)) -> dict[str, Any]:
    """Proxy ENGINE 03's stable ids and Traditional-Chinese display text to the frontend."""
    try:
        return _get(f"{ENGINE03_URL}/attributes", _auth_headers(authorization))
    except Exception as exc:
        raise HTTPException(502, f"engine03.attributes 失敗：{type(exc).__name__}: {exc}"[:300])


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
