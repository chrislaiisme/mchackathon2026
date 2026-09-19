"""BFF — 一輪對話的流程控制。

前端只跟這裡講話，由這裡依序呼叫三個引擎：

    POST /round      一句話 → ENGINE 01 抽意圖 → ENGINE 02 檢索排序 → 回傳這一輪結果
    POST /feedback   回饋 → ENGINE 03 轉換 → 帶著回饋重跑 ENGINE 02 → 回傳下一輪結果

流程由程式決定，不交給模型判斷；每一步都記進 activity，前端的「Agent 活動紀錄」和
demo 時要回答「這個結果怎麼來的」都靠它。
"""
from __future__ import annotations

import os
import sys
import time
from typing import Any, Literal, Optional

import httpx
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from bff.images.concept import (GENERATED_ROOT, ConceptImageUnavailable, generate_concept_pair,
                                generate_concepts)
from bff.images.outfit_pair import OutfitPairUnavailable, pair_outfit

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
    s.utterance = body.message
    s.prev_intent = s.intent or None
    s.intent = intent_out.get("intent") or {}
    s.round = int(intent_out.get("round") or s.round + 1)

    retrieval = _retrieve(s, activity, body.message, body.top_k, headers)

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
        "concept_image": s.concept_image,
        "feedback_applied": s.feedback,
        "ledger_entry": fb_out.get("ledger_entry"),
        "activity": activity,
    }
    s.rounds.append(result)
    return result


class ConceptImageRequest(BaseModel):
    session_id: Optional[str] = None
    """走 BFF 自己那條流程時給。前端直接打 ENGINE 01 的話留空，改給 intent。"""
    intent: Optional[dict[str, Any]] = None
    """ENGINE 01 `/intent` 回傳裡的 intent，原樣帶過來即可。"""
    cells: int = 6
    model: Optional[str] = None
    """生圖模型，省略用 generate_grid.py 的預設。"""
    dry_run: bool = False
    """只組 prompt 與 manifest，不生圖、不花額度。開發時先用這個。"""
    pair: bool = False
    """True = TOP 與 BOTTOM 各生一張六格（並行），回傳 slots；False = 只生 intent 那一類。"""


@app.post("/concept-image")
def concept_image(body: ConceptImageRequest) -> dict[str, Any]:
    """使用者對檢索結果不滿意時，一次生六件新單品讓他挑。

    明確觸發，不在每一輪自動跑：一張六宮格 26–48 秒。六件擠在一張圖裡生，
    比逐一生成快三倍多，理由見 bff/images/concept.py。
    """
    # 兩種來源：BFF 自己的 session，或前端直接把 ENGINE 01 的 intent 帶過來。
    if body.intent:
        session_id = body.session_id or "direct"
        round_no = 1
        intent = body.intent
    else:
        s = _SESSIONS.get(body.session_id or "")
        if s is None or not s.rounds:
            raise HTTPException(404, "沒有 intent，也找不到這個 session 的任何一輪結果")
        if not s.intent:
            raise HTTPException(409, "這個 session 還沒有結構化意圖，無法生圖")
        session_id, round_no, intent = s.session_id, s.round, s.intent

    activity: list[dict[str, Any]] = []
    t0 = time.time()
    step = "images.concepts.pair" if body.pair else "images.concepts"
    try:
        if body.pair:
            slots = generate_concept_pair(session_id, round_no, intent,
                                          cells=body.cells, model=body.model, dry_run=body.dry_run)
        else:
            slots = None
            out = generate_concepts(session_id, round_no, intent,
                                    cells=body.cells, model=body.model, dry_run=body.dry_run)
    except ConceptImageUnavailable as exc:
        activity.append({"step": step, "ms": int((time.time() - t0) * 1000),
                         "ok": False, "error": str(exc)[:200]})
        raise HTTPException(502, f"生成單品失敗：{exc}")
    except Exception as exc:
        raise HTTPException(502, f"生成單品失敗：{type(exc).__name__}: {exc}"[:300])

    activity.append({"step": step, "ms": int((time.time() - t0) * 1000), "ok": True})

    if body.pair:
        return {"session_id": session_id, "round": round_no, "slots": slots, "activity": activity}

    if not body.intent and (s := _SESSIONS.get(session_id)):
        s.concept_image = {"image_url": out.get("grid_image"),
                           "prompt_used": out.get("prompt_used"), "response_id": None}
    return {"session_id": session_id, "round": round_no, "concepts": out, "activity": activity}


class OutfitCandidate(BaseModel):
    id: str = Field(..., min_length=1)
    label: Optional[str] = None
    """跟同一格其他候選的差別（varied_label），純展示用，判斷主要看 keywords。"""
    keywords: Any = None
    """`{欄位: 中文值}` 的 dict，或前端 `FashionRecommendation.attributes` 那種字串陣列——
    兩種形狀 pair_outfit.py 都吃，這裡不用先轉一次。"""


class OutfitPairRequest(BaseModel):
    session_id: Optional[str] = None
    intent: dict[str, Any] = Field(default_factory=dict)
    tops: list[OutfitCandidate] = Field(..., min_length=1)
    bottoms: list[OutfitCandidate] = Field(..., min_length=1)


def _outfit_pair_fallback(tops: list[dict[str, Any]], bottoms: list[dict[str, Any]],
                          note: str) -> dict[str, Any]:
    """BFF 自己這層退場：只在 pair_outfit.py 連跑都跑不起來、或它回傳的 id 不在
    請求的清單裡時才會用到（腳本自己內建的退場已經處理了 codex 失敗／逾時／
    回傳不合法這幾種情況，正常不會落到這裡）。理由不編造判斷，只講清楚這組是
    自動退回來的第一件配第一件，跟腳本自己 fallback 的用意一致。"""
    print(f"[warn] /outfit-pair 走 BFF 層退場（{note}）", file=sys.stderr)
    top, bottom = tops[0], bottoms[0]
    label = lambda item: str(item.get("label") or item["id"])  # noqa: E731
    return {"top_id": top["id"], "bottom_id": bottom["id"],
            "reason": f"{label(top)}配{label(bottom)}，配對服務暫時無法使用，先給預設的第一組。",
            "source": "fallback"}


@app.post("/outfit-pair")
def outfit_pair(body: OutfitPairRequest) -> dict[str, Any]:
    """「AI 幫我搭」按鈕：從已生成的上衣與下身候選裡挑一組最搭的。

    永遠回 200——按鈕按下去使用者要看到一組結果，不是一個錯誤畫面；請求本身不合法
    （tops／bottoms 缺 id 或整份是空的）才會是 4xx，交給 pydantic 在進到這裡之前擋下。

    兩層退場：`pair_outfit.py` 自己失敗／逾時／回傳不合法時內建退到 `tops[0]`／
    `bottoms[0]`（退出碼仍是 0，見該腳本開頭註解）；這支腳本連跑都跑不起來
    （找不到、逾時到來不及印出退場、stdout 壞掉），或它回傳的 id 不在這次請求的
    清單裡，這裡再退一層，一樣是 `tops[0]`／`bottoms[0]`。
    """
    tops = [t.model_dump() for t in body.tops]
    bottoms = [b.model_dump() for b in body.bottoms]
    top_ids = {t["id"] for t in tops}
    bottom_ids = {b["id"] for b in bottoms}

    try:
        result = pair_outfit(body.intent, tops, bottoms)
    except OutfitPairUnavailable as exc:
        return _outfit_pair_fallback(tops, bottoms, str(exc)[:150])
    except Exception as exc:
        return _outfit_pair_fallback(tops, bottoms, f"{type(exc).__name__}: {exc}"[:150])

    if not isinstance(result, dict) or result.get("top_id") not in top_ids \
            or result.get("bottom_id") not in bottom_ids or not str(result.get("reason") or "").strip():
        return _outfit_pair_fallback(tops, bottoms, "回傳的配對不合法（id 不在清單裡或缺理由）")

    source = result.get("source") if result.get("source") in ("llm", "fallback") else "fallback"
    return {"top_id": result["top_id"], "bottom_id": result["bottom_id"],
            "reason": result["reason"], "source": source}


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
