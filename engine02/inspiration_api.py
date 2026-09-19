"""HTTP endpoints for the inspiration library (靈感牆: runway / street / cosplay photos).

    GET  /inspiration?group=runway|street|cosplay&limit=30   photos + attribution for the wall
    GET  /inspiration/images/{insp_id}                         the thumbnail
    POST /inspiration/{insp_id}/recommend                      「我想要這種感覺」→ purchasable items

A photo is a query, never a catalog row: its embedding goes to /rank as
`feedback.concept_image_embedding`, the same path /visual-search uses, at the serving arm's
`concept_image_weight` (0.2; evidence says keep ≤ 0.2). The text request stays in charge.

Mount with `app.include_router(inspiration_router)`; data dir from ENGINE02_INSPIRATION
(default data/inspiration), index chosen by ENGINE02_ENCODER, built by scripts/build_inspiration.py.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ValidationError

from .contracts import ContextInput
from .inspiration import GROUPS, Inspiration, InspirationError, load

router = APIRouter()
ROOT = Path(__file__).resolve().parents[1]
_CACHE: dict = {}

DOMAIN_CAVEAT = "照片是真人整身穿搭、商品是單品圖，只取整體感覺（色調、正式度、廓形），不會逐件比對照片裡的衣服"


def _engine():
    from .api import engine
    return engine()


def _dir() -> Path:
    p = Path(os.environ.get("ENGINE02_INSPIRATION", "data/inspiration"))
    return p if p.is_absolute() else ROOT / p


def _encoder_key() -> str:
    return os.environ.get("ENGINE02_ENCODER", "marqo-fashionSigLIP")


def library() -> Inspiration:
    """Loaded once per (dir, encoder, items.parquet mtime) so a rebuild is picked up without restart."""
    root, key = _dir(), _encoder_key()
    f = root / "items.parquet"
    stamp = f.stat().st_mtime_ns if f.exists() else None
    ck = (str(root), key, stamp)
    if _CACHE.get("key") != ck:
        try:
            _CACHE["lib"] = load(root, encoder=key)
        except InspirationError as e:
            raise HTTPException(503, str(e))
        _CACHE["key"] = ck
    return _CACHE["lib"]


def _card(row: dict) -> dict:
    g = GROUPS.get(row["group"], {})
    author = row.get("author") or "unknown"
    lic = row.get("license") or ""
    return {
        "insp_id": row["insp_id"],
        "group": row["group"],
        "group_label": g.get("label", row["group"]),
        "title": row["title"],
        "image_url": f"/inspiration/images/{row['insp_id']}",
        "commons_image_url": row["image_url"],
        "page_url": row["page_url"],
        "license": lic,
        "license_url": row.get("license_url") or "",
        "author": author,
        # the one line a CC BY / BY-SA licence asks for: title, author, licence, source
        "attribution": f"「{row['title']}」— {author}，{lic}，來源 Wikimedia Commons",
    }


@router.get("/inspiration")
def inspiration_list(group: str | None = None, limit: int = Query(30, ge=1, le=200),
                     offset: int = Query(0, ge=0)) -> dict:
    lib = library()
    if group is not None and group not in GROUPS:
        raise HTTPException(400, f"unknown group {group!r}; one of {sorted(GROUPS)}")
    counts = lib.counts()
    return {
        "groups": {g: {"label": v["label"], "count": counts.get(g, 0)} for g, v in GROUPS.items()},
        "items": [_card(r) for r in lib.list_items(group, limit=limit, offset=offset)],
        "note": "靈感圖來自 Wikimedia Commons，依授權標示作者與授權；不是商品，點「我想要這種感覺」找可購買的單品",
    }


@router.get("/inspiration/images/{insp_id}")
def inspiration_image(insp_id: str):
    lib = library()
    f = lib.image_file(insp_id)
    if f is None:
        raise HTTPException(404, "unknown inspiration id")
    f = f.resolve()
    if lib.root.resolve() not in f.parents or not f.exists():
        raise HTTPException(404, "image file missing")
    return FileResponse(f, media_type="image/jpeg")


class InspirationRecommendRequest(BaseModel):
    retrieval_text: str = ""
    top_k: int = Field(5, ge=1, le=50)
    context: ContextInput | None = None
    constraints: dict = Field(default_factory=dict)
    arm: str | None = None
    session_id: str = "inspiration"
    profile: bool = True


def _note(photo: str, weight: float, has_text: bool) -> str:
    if weight <= 0:
        return f"目前的排序設定不使用參考圖（權重 0），這張{photo}不會影響結果"
    if has_text:
        return f"以這張{photo}的感覺為參考（權重 {weight:g}，文字需求仍是主角）"
    return (f"以這張{photo}的感覺為參考（權重 {weight:g}）；你還沒說想找什麼，"
            "加一句像「黑色西裝外套」的需求，結果會更準")


@router.post("/inspiration/{insp_id}/recommend")
def inspiration_recommend(insp_id: str, body: InspirationRecommendRequest) -> dict:
    from . import api
    from .config import ARMS
    from .contracts import Engine02Options, Engine02Request, HardConstraints

    lib = library()
    row = lib.row(insp_id)
    if row is None:
        raise HTTPException(404, "unknown inspiration id")
    e = _engine()
    try:
        vec = lib.embedding(insp_id, expected_dim=int(e.image_emb.shape[1]), encoder_name=e.encoder.name)
    except InspirationError as exc:
        raise HTTPException(409, str(exc))
    arm = body.arm or os.environ.get("ENGINE02_ARM", "full_zclip3")
    if arm not in ARMS:
        raise HTTPException(400, f"unknown arm {arm!r}; see GET /arms")
    try:
        hard = HardConstraints(**body.constraints) if body.constraints else HardConstraints()
    except ValidationError as exc:
        raise HTTPException(422, {"error": "constraints is not a valid HardConstraints object",
                                  "detail": exc.errors(include_url=False)})
    text = (body.retrieval_text or "").strip()
    req = Engine02Request(session_id=body.session_id, retrieval_text=text, constraints=hard,
                          context=body.context or ContextInput(),
                          options=Engine02Options(top_k=body.top_k, arm=arm, explain_with_llm=False))
    req.feedback.concept_image_embedding = [float(x) for x in vec]
    resp = api.rank(req)

    weight = float(ARMS[arm].concept_image_weight)
    photo = GROUPS.get(row["group"], {}).get("photo", "照片")
    card = _card(row)
    out: dict = {
        "response": resp.model_dump(),
        "inspiration": {k: card[k] for k in ("insp_id", "group", "group_label", "title", "license",
                                             "license_url", "author", "page_url", "image_url",
                                             "attribution")},
        "arm": arm,
        "concept_image_weight": weight,
        "note": _note(photo, weight, bool(text)),
        "caveat": DOMAIN_CAVEAT,
    }
    if body.profile:  # display only: what the photo reads as, on the catalog's own scale
        try:
            from .concepts import element_profile, load_profile_stability

            cache = api.STATE.setdefault("prompt_cache", {})
            stab = api.STATE.setdefault("profile_stability", load_profile_stability())
            prof = element_profile(e.encoder, e.image_emb, vec, e.kansei, mode=ARMS[arm].concept_mode,
                                   prompt_cache=cache, stability=stab)
            out["profile"] = [p for p in prof if p.get("reliable") is not False][:3]
            out["profile_note"] = "這張照片最突出的設計要素（相對於本商品庫，只挑穩定的要素顯示）"
        except Exception as exc:  # a profile is decoration; never fail the recommendation over it
            out["profile"] = []
            out["profile_note"] = f"設計要素分析暫時無法提供（{type(exc).__name__}）"
    return out
