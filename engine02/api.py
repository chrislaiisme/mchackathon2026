"""HTTP API for ENGINE 02 (FastAPI).

  ENGINE02_ENCODER=marqo-fashionSigLIP uvicorn engine02.api:app --port 8002

Environment variables:
  ENGINE02_CATALOG   catalog dir with items.parquet           (default data/catalog/kagl)
  ENGINE02_ENCODER   marqo-fashionSigLIP | fashion-clip | hash (default marqo-fashionSigLIP)
  ENGINE02_DEVICE    auto | cpu | cuda                         (default auto)
  ENGINE02_RERANKER  optional cross-reranker, e.g. Qwen3-VL-Reranker-2B (GPU only in practice)
  ENGINE02_COOC      category co-occurrence json               (default data/catalog/polyvore/category_cooccurrence.json)
  ENGINE02_KANSEI    Kansei table json                         (default engine02/resources/kansei_v1_literature.json)
  ENGINE02_LLM       auto (OpenAI if OPENAI_API_KEY) | none    (default auto)
  ENGINE02_ARM       default ablation arm when the request does not set one (default full_zclip3)
  ENGINE02_OT        1 = load OutfitTransformer for /complete-look (GPU recommended); else image similarity
  ENGINE02_TRENDS    1 or a file path = load trend keywords for display badges (never for ranking)
  ENGINE02_WARMUP    0 disables the startup warm-up query (default: run it)
  ENGINE02_DEMO      1 = never call the LLM for reasons, whatever the request asks
  ENGINE02_MAX_UPLOAD_MB  /visual-search upload cap (default 12)
  ENGINE02_LLM_TIMEOUT / ENGINE02_LLM_BUDGET_S  per-call and per-request paraphrase budgets
"""

from __future__ import annotations

import io
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, ValidationError

from .catalog import Catalog
from .compat import CategoryCooccurrence
from .config import ARMS
from .contracts import (CONTRACT_VERSION, Engine02Options, Engine02Request, Engine02Response,
                        HardConstraints)
from .encoders import HashEncoder
from .kansei import KanseiTable
from .llm import get_llm
from .composed import ComposedEngine02
from .pipeline import Engine02
from .service import Engine02Service, ServiceResponse

log = logging.getLogger("engine02.api")

ROOT = Path(__file__).resolve().parents[1]
STATE: dict = {}


def _path(env: str, default: str) -> Path:
    p = Path(os.environ.get(env, default))
    return p if p.is_absolute() else ROOT / p


def build_engine() -> ComposedEngine02:
    catalog = Catalog.load(_path("ENGINE02_CATALOG", "data/catalog/kagl"))
    enc_name = os.environ.get("ENGINE02_ENCODER", "marqo-fashionSigLIP")
    device = os.environ.get("ENGINE02_DEVICE", "auto")
    if enc_name == "hash":
        encoder = HashEncoder(dim=256, captions={Path(p).name: t for p, t in zip(catalog.items["image_path"], catalog.texts())})
    else:
        from .models import TorchEncoder

        encoder = TorchEncoder(enc_name, device=device)
    cooc_file = _path("ENGINE02_COOC", "data/catalog/polyvore/category_cooccurrence.json")
    reranker = None
    if os.environ.get("ENGINE02_RERANKER"):
        from .models import CrossEncoderReranker

        reranker = CrossEncoderReranker(os.environ["ENGINE02_RERANKER"], catalog, device=device)
    llm = None if os.environ.get("ENGINE02_LLM", "auto") == "none" else get_llm("auto")
    return ComposedEngine02(
        catalog,
        encoder,
        kansei=KanseiTable.load(_path("ENGINE02_KANSEI", "") if os.environ.get("ENGINE02_KANSEI") else None),
        cooccurrence=CategoryCooccurrence.load(cooc_file) if cooc_file.exists() else None,
        llm=llm,
        cross_reranker=reranker,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = build_engine()
    STATE["engine"] = engine
    ctl = None
    if engine.cooc is not None:
        from .complete_look import CompleteTheLook

        ot = None
        if os.environ.get("ENGINE02_OT") == "1":
            from .complete_look import FastOutfitTransformer

            # /complete-look ranks with the complementary head (best in T5: MRR 0.277), so load it —
            # ENGINE02_OT_HEADS overrides; missing checkpoints are skipped instead of breaking startup.
            want = tuple(h.strip() for h in os.environ.get("ENGINE02_OT_HEADS", "complementary,compatibility").split(",") if h.strip())
            have = FastOutfitTransformer.checkpoints()
            heads = tuple(h for h in want if h in have)
            if not heads:
                log.warning("ENGINE02_OT=1 but no OutfitTransformer checkpoint found; falling back to image similarity")
            else:
                if len(heads) < len(want):
                    log.warning("OutfitTransformer heads missing: %s", sorted(set(want) - set(heads)))
                # item embeddings depend only on the catalog; without this cache every
                # /complete-look re-encodes ~100 images inside the request (p50 554 ms → see
                # docs/engine02-design.md §3.21). scripts/precompute_ot_cache.py writes it.
                ot_cache = Path(os.environ.get("ENGINE02_OT_CACHE", "")) if os.environ.get("ENGINE02_OT_CACHE")                     else _path("ENGINE02_CATALOG", "data/catalog/kagl") / "index" / "ot_items.npz"
                if not ot_cache.exists():
                    log.warning("no OutfitTransformer embedding cache at %s — /complete-look will be slow; "
                                "run scripts/precompute_ot_cache.py", ot_cache)
                ot = FastOutfitTransformer(engine.catalog, device=os.environ.get("ENGINE02_DEVICE", "auto"),
                                           heads=heads, cache_file=ot_cache)
        ctl = CompleteTheLook(engine.catalog, engine.image_emb, engine.cooc, ot=ot)
    STATE["service"] = Engine02Service(engine, ctl)
    tr = os.environ.get("ENGINE02_TRENDS")
    if tr:  # badges only — attach_trends() (the ranking term) is deliberately never called (§3.15)
        from .trends import load_trends

        try:
            STATE["trends"] = load_trends(None if tr == "1" else tr)
        except OSError as e:
            log.warning("could not load trend keywords: %s", e)
    if os.environ.get("ENGINE02_WARMUP", "1") != "0":
        STATE["warm_ms"] = _warmup()
    yield
    STATE.clear()


def _warmup() -> float | None:
    """Pay the first-request costs before the demo starts.

    A cold process spends its first query on things that never repeat: the CUDA context and the
    first kernel launch, the taxonomy JSON, the per-catalog attribute index, the design matrix, the
    pydantic validators. On stage that lands on the judge's first question.
    """
    import time

    from .contracts import Engine02Options, Engine02Request

    t = time.perf_counter()
    try:
        svc = STATE["service"]
        req = Engine02Request(session_id="__warmup__", retrieval_text="navy blue shirt",
                              options=Engine02Options(top_k=5, explain_with_llm=False))
        resp = svc.rank(req, os.environ.get("ENGINE02_ARM", "full_zclip3"))
        if getattr(svc, "ctl", None) is not None and resp.items:
            try:
                svc.complete_look([resp.items[0].item_id], n_categories=1, k=3)
            except Exception as e:  # a missing co-occurrence or checkpoint must not block startup
                log.warning("complete-look warmup skipped: %s", e)
        ms = (time.perf_counter() - t) * 1000
        log.info("warmup finished in %.0f ms", ms)
        return round(ms, 1)
    except Exception as e:
        log.warning("warmup failed (serving anyway): %s", e)
        return None


app = FastAPI(title="ENGINE 02 — retrieval, ranking, faithful explanation", version=CONTRACT_VERSION, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def engine() -> Engine02:
    return STATE["engine"]


def _encode_upload(e, blob: bytes) -> "np.ndarray":
    """Normalise whatever a phone or a screenshot hands us, then encode it with the catalog encoder.

    Real uploads are not catalog images: they carry EXIF rotation (a sideways photo embeds as a
    sideways photo), alpha or CMYK channels, and occasionally 50 MP. Each of those silently changes
    the embedding, so normalise first and refuse clearly rather than returning a confident answer
    about a rotated, transparent picture.
    """
    import tempfile

    from PIL import Image, ImageOps, UnidentifiedImageError

    Image.MAX_IMAGE_PIXELS = 80_000_000  # refuse decompression bombs instead of freezing the demo
    try:
        with Image.open(io.BytesIO(blob)) as im:
            im = ImageOps.exif_transpose(im)  # honour the camera's rotation flag
            if im.mode in ("RGBA", "LA", "P"):  # flatten transparency onto white, like a product shot
                im = im.convert("RGBA")
                bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
                im = Image.alpha_composite(bg, im)
            im = im.convert("RGB")
            if max(im.size) > 1600:  # the encoder resizes to 224/384 anyway
                im.thumbnail((1600, 1600))
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as fh:
                im.save(fh, format="PNG")
                tmp = Path(fh.name)
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(400, f"could not read the image: {type(exc).__name__}: {exc}")
    try:
        return e.encoder.encode_images([tmp])[0]
    except Exception as exc:
        raise HTTPException(400, f"could not encode the image: {type(exc).__name__}: {exc}")
    finally:
        tmp.unlink(missing_ok=True)


def _record_demand(req: Engine02Request) -> None:
    """Keep what was asked for, so the gap panel has a real (and small, and stated) denominator."""
    from collections import deque

    import time

    buf = STATE.get("demand")
    if buf is None:
        buf = STATE["demand"] = deque(maxlen=int(os.environ.get("ENGINE02_DEMAND_LOG", "500")))
    c = req.constraints
    buf.append((
        {n.need_id: n.prob for n in req.needs},
        dict(req.feedback.design_adjust_steps),
        ((c.category.values[0] if c.category.values else None),
         (c.color.values[0] if c.color.values else None)),
        time.time(),  # so the panel can say "demand in this session changed", with a real window
    ))


@app.get("/gap/elements")
def gap_elements(arm: str = "full_zclip3", threshold: float = 0.5) -> dict:
    """Design-element demand (from the queries this server served) vs catalog supply.

    What a garment maker can act on: an element many requests wanted that little of the catalog
    expresses. `n_sessions` is the denominator — say it out loud when showing this.
    """
    from .panels import element_gap

    if arm not in ARMS:
        raise HTTPException(400, f"unknown arm {arm!r}; see GET /arms")
    buf = list(STATE.get("demand", []))
    labels = {e.id: e.label for e in engine().kansei.elements}
    rep = element_gap(engine(), [(p, s) for p, s, *_ in buf], arm, threshold, labels)
    return rep.model_dump()


@app.get("/gap/elements/change")
def gap_elements_change(arm: str = "full_zclip3", threshold: float = 0.5, min_per_window: int = 30) -> dict:
    """How element demand moved **within this session**, earlier half vs later half.

    This is deliberately *not* a trend or a forecast. The denominator is the requests this process
    has served since it started (the log is in memory and resets on restart), so it describes the
    room, not the market — and with few requests it refuses to answer instead of drawing a line
    through noise. A hostile reading is correct: someone can move this by typing more queries.
    """
    from .panels import element_gap

    if arm not in ARMS:
        raise HTTPException(400, f"unknown arm {arm!r}; see GET /arms")
    buf = list(STATE.get("demand", []))
    if len(buf) < 2 * min_per_window:
        return {"status": "insufficient_data", "n_sessions": len(buf),
                "needed": 2 * min_per_window,
                "note": "本場請求數不足，不畫趨勢線（需求側＝本服務啟動後收到的查詢）"}
    half = len(buf) // 2
    labels = {e.id: e.label for e in engine().kansei.elements}
    early = element_gap(engine(), [(p, s) for p, s, *_ in buf[:half]], arm, threshold, labels)
    late = element_gap(engine(), [(p, s) for p, s, *_ in buf[half:]], arm, threshold, labels)
    e_share = {e.element: e.demand_share for e in early.elements}
    l_share = {e.element: e.demand_share for e in late.elements}
    rows = []
    for el in sorted(set(e_share) | set(l_share), key=lambda x: -abs(l_share.get(x, 0) - e_share.get(x, 0))):
        rows.append({"element": el, "label": labels.get(el, el),
                     "share_early": round(e_share.get(el, 0.0), 4),
                     "share_late": round(l_share.get(el, 0.0), 4),
                     "delta": round(l_share.get(el, 0.0) - e_share.get(el, 0.0), 4)})
    return {"status": "ok", "n_early": half, "n_late": len(buf) - half,
            "window_seconds": round(float(buf[-1][3] - buf[0][3]), 1) if len(buf[0]) > 3 else None,
            "elements": rows,
            "note": "本場需求變化，不是市場趨勢也不是預測；分母是本服務啟動後的請求數"}


@app.get("/gap/cells")
def gap_cells(top: int = 20) -> dict:
    """Requested (category, colour) cells against how many items the catalog has in each."""
    from .panels import category_color_gap

    buf = list(STATE.get("demand", []))
    rows = category_color_gap(engine(), [r[2] for r in buf], top)
    return {"n_sessions": len(buf), "cells": [r.model_dump() for r in rows],
            "note": "需求側 = 本服務實際收到的查詢，不是市場量測"}


def _complete_look_status() -> dict:
    svc = STATE.get("service")
    ctl = getattr(svc, "ctl", None)
    if ctl is None:
        return {"available": False, "reason": "no category co-occurrence for this catalog"}
    ot = getattr(ctl, "ot", None)
    return {"available": True, "method": svc.complete_look_method(),
            "ot_heads": list(getattr(ot, "heads", ()) or ())}


@app.get("/health")
def health() -> dict:
    e = engine()
    return {
        "status": "ok",
        "contract_version": CONTRACT_VERSION,
        "catalog": e.catalog.name,
        "n_items": len(e.catalog),
        "encoder": e.encoder.name,
        "reranker": getattr(e.cross_reranker, "name", None),
        "llm": e.llm is not None,
        "demo_mode": DEMO_MODE,
        "kansei_version": e.kansei.version,
        "complete_look": _complete_look_status(),
        "warm_ms": STATE.get("warm_ms"),
        "init_ms": round(e.init_ms, 1),
    }


@app.get("/arms")
def arms() -> dict:
    return {name: vars(cfg) for name, cfg in ARMS.items()}


@app.get("/kansei")
def kansei() -> dict:
    """Need ids and design-element ids that ENGINE 01 / 03 must use."""
    k = engine().kansei
    return {
        "version": k.version,
        "needs": k.needs,
        "design_elements": {el.id: el.label for el in k.elements},
        "step_size": k.step_size,
        "max_steps": k.max_steps,
    }


@app.get("/vocabulary")
def vocabulary() -> dict:
    """Catalog values ENGINE 01 must normalise slot values to (hard filters are exact matches)."""
    from .taxonomy import load_taxonomy

    items = engine().catalog.items
    out = {}
    for col in ("category", "subcategory", "color", "occasion", "season", "gender"):
        vc = items[col].dropna().astype(str).value_counts()
        out[col] = vc.to_dict()
    tax = load_taxonomy()
    out["taxonomy"] = tax.vocabulary_payload(items, engine().catalog.name)
    out["closed_vocabulary"] = tax.closed_vocabulary(max_synonyms=4)  # give this to ENGINE 01's GPT
    return out


DEMO_MODE = os.environ.get("ENGINE02_DEMO") == "1"


@app.post("/rank", response_model=ServiceResponse)
def rank(req: Engine02Request) -> ServiceResponse:
    """Composed critique (if reference_item_id + critique) → additive ranking → slate diversification."""
    if DEMO_MODE and req.options.explain_with_llm:
        # on stage the venue network is not guaranteed; templates are always available and the
        # reason text is verified either way. The client cannot opt back in.
        req = req.model_copy(deep=True)
        req.options.explain_with_llm = False
    arm = req.options.arm or os.environ.get("ENGINE02_ARM", "full_zclip3")
    if arm not in ARMS:
        raise HTTPException(400, f"unknown arm {arm!r}; see GET /arms")
    if ARMS[arm].use_cross_reranker and engine().cross_reranker is None:
        raise HTTPException(400, "this arm needs ENGINE02_RERANKER to be set on the server")
    _record_demand(req)
    return STATE["service"].rank(req, arm)


@app.post("/rank/plain", response_model=Engine02Response)
def rank_plain(req: Engine02Request) -> Engine02Response:
    """The additive pipeline alone (no critique composition, no diversification) — for ablations."""
    arm = req.options.arm or os.environ.get("ENGINE02_ARM", "full_zclip3")
    if arm not in ARMS:
        raise HTTPException(400, f"unknown arm {arm!r}; see GET /arms")
    return engine().run(req, arm)


class ViewRequest(BaseModel):
    """One round for the PRD §7 screens; pass the previous round to get the diff panel."""

    request: Engine02Request
    prev_request: Engine02Request | None = None
    prev_response: Engine02Response | None = None


@app.post("/view")
def view(body: ViewRequest) -> dict:
    """Rank + every §7 panel (said/unsaid, needs, diversity, provenance, round diff, trend badges).

    The frontend should not re-derive these aggregates from the cards: `Div@k`, the need shares and
    the provenance counts are computed from the same contributions that produced the ranking.
    """
    from .panels import build_view, view_labels

    resp = rank(body.request)
    labels = view_labels(engine())
    v = build_view(body.request, resp, body.prev_request, body.prev_response, **labels)
    out = {"response": resp.model_dump(), "view": v.model_dump()}
    if STATE.get("trends") is not None:  # display-only labels; trends never enter the score (§3.15)
        from .trends import trend_badges

        out["trend_badges"] = trend_badges(engine(), resp, STATE["trends"].keywords())
    return out


class IntentRankRequest(BaseModel):
    """ENGINE 01 speaks this. `intent` is `backend.shared.schemas.Intent` as plain JSON."""

    session_id: str = "engine01"
    round: int = 0
    message: str | None = None          # the user's original sentence, for the record
    intent: dict = {}
    feedback: dict | None = None        # ENGINE 03's ledger, unchanged
    top_k: int = 5
    arm: str | None = None


@app.post("/intent/rank")
def intent_rank(body: IntentRankRequest) -> dict:
    """ENGINE 01's `Intent` in, the team's `RetrievalResult` out (docs/interface-contract.md).

    The whole cross-engine boundary lives in `engine02/intent_adapter.py`: Chinese free text is
    resolved to this catalog's own vocabulary, `inferred_fields` stay soft, and anything that could
    not be resolved is reported rather than quietly dropped — a Chinese value passed straight
    through would fall out of the relaxation ladder and return a confident, wrong slate.
    """
    from .intent_adapter import intent_to_request, response_to_retrieval_result

    e = engine()
    arm = body.arm or os.environ.get("ENGINE02_ARM", "full_zclip3")
    if arm not in ARMS:
        raise HTTPException(400, f"unknown arm {arm!r}; see GET /arms")
    try:
        req, unresolved = intent_to_request(
            body.intent, session_id=body.session_id, round=body.round, message=body.message,
            catalog_name=getattr(e.catalog, "name", None), top_k=body.top_k, arm=arm,
            feedback=body.feedback)
    except ValidationError as exc:
        raise HTTPException(422, {"error": "intent could not be converted to an Engine02Request",
                                  "detail": exc.errors(include_url=False)})
    resp = rank(req)
    out = response_to_retrieval_result(e, req, resp, arm=arm)
    # what ENGINE 01 should fix, in ENGINE 01's own terms, next to what the pipeline itself found
    out["engine02"]["unresolved_from_intent"] = unresolved
    return out


@app.get("/context")
def context() -> dict:
    """External context (weather) as fetched EARLIER by scripts/fetch_context.py — never now.

    The serving path does not touch the network: from Taipei a cold call to Open-Meteo is p50
    1.57 s against a 12.8 ms /rank, and ENGINE02_DEMO=1 has no network at all. So this reads a
    local file, reports how stale it is, and hands the caller a season word it MAY attach as
    `constraints.season` with state="inferred" (a soft signal that never shrinks the candidate
    pool). ENGINE 02 never attaches it by itself: season is the caller's statement about the user.

    Missing or stale file is not an error — it is the documented no-op.
    """
    import json as _json
    from datetime import datetime, timezone

    f = _path("ENGINE02_CONTEXT", "data/context/weather.json")
    if not f.exists():
        return {"available": False,
                "note": "沒有情境檔；這是正常的 no-op。要啟用請先跑 scripts/fetch_context.py（它會連網，服務路徑不會）。"}
    try:
        ctx = _json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return {"available": False, "note": f"情境檔讀不起來（{type(e).__name__}），視為 no-op"}
    age = None
    try:
        age = (datetime.now(timezone.utc)
               - datetime.fromisoformat(str(ctx.get("fetched_at")))).total_seconds()
    except (TypeError, ValueError):
        pass
    fresh = age is not None and age < float(os.environ.get("ENGINE02_CONTEXT_MAX_AGE_S", "10800"))
    return {"available": True, "age_seconds": None if age is None else round(age), "fresh": fresh,
            "context": ctx,
            "suggested_constraint": ({"season": {"state": "inferred",
                                                 "values": [ctx["suggested_season"]]}}
                                     if fresh and ctx.get("suggested_season") else None),
            "note": ("情境是離線抓好的，排序不會因此連網。" +
                     ("" if fresh else "這份情境已過期，建議忽略或重新抓。"))}


@app.get("/profile/questions")
def profile_questions_endpoint(n: int = 3, arm: str | None = None) -> dict:
    """n forced choices between two real photos, to build a prior before the user types anything.

    Three is a stage decision (≈15 s inside a 30 s段 script), not a literature result: Zou et al.
    (SIGIR 2020) measure that elicitation keeps improving up to ~10 questions. See §3.32.
    """
    from .panels import profile_questions

    a = arm or os.environ.get("ENGINE02_ARM", "full_zclip3")
    if a not in ARMS:
        raise HTTPException(400, f"unknown arm {a!r}; see GET /arms")
    qs = profile_questions(engine(), a, n=n)
    return {"arm": a, "n": len(qs), "questions": qs,
            "note": "答案請以 [{axis, side}] 送回 POST /profile；side 是 high 或 low。"}


class ProfileAnswers(BaseModel):
    answers: list[dict] = []
    kappa0: float = 3.0


@app.post("/profile")
def profile_endpoint(body: ProfileAnswers) -> dict:
    """Turn those choices into `Engine02Request.profile`, ready to send with every round."""
    from .panels import profile_from_answers

    return profile_from_answers(engine(), body.answers, kappa0=body.kappa0)


class FacetRequest(BaseModel):
    """Read one ranking three ways. The ranking itself is untouched."""

    request: Engine02Request
    n_pool: int = 50      # how many ranked items to slice (the cards shown stay request.options.top_k)
    n_groups: int = 3
    examples: int = 2


@app.post("/facets")
def facets(body: FacetRequest) -> dict:
    """Named facets over the SAME ranking: "your sentence reads three ways, here is the axis".

    Inspired by GenFacet (SIGIR 2026, shipped at JD.com, facet CTR +42.0% relative online), but
    deliberately not its method: our facets are not generated, they are the design-element axes of
    §3.3 that already have AUROC evidence behind them. This is a panel, never a reranker — the
    order, the scores and every contribution are exactly what /rank returns, so no retrieval
    number in docs/engine02-design.md changes and the facet cannot misdescribe the score.
    """
    from .panels import facet_slices

    req = body.request.model_copy(deep=True)
    req.options.top_k = max(body.n_pool, req.options.top_k)
    req.options.explain_with_llm = False           # a panel never pays for wording
    resp = rank(req)
    arm = req.options.arm or os.environ.get("ENGINE02_ARM", "full_zclip3")
    panel = facet_slices(engine(), arm, [it.item_id for it in resp.items],
                         [it.score for it in resp.items], n_groups=body.n_groups,
                         examples=body.examples)
    return {"arm": arm, "n_ranked": len(resp.items), "facets": panel.model_dump()}


class VisualSearchRequest(BaseModel):
    """A photo the customer or the brand hands over. base64 so no multipart dependency is needed."""

    image_base64: str
    top_k: int = 5
    constraints: dict = {}
    retrieval_text: str = ""
    arm: str | None = None
    profile: bool = True


@app.post("/visual-search")
def visual_search(body: VisualSearchRequest) -> dict:
    """Search the catalog with an uploaded photo, and say what design elements the photo has.

    Two answers from one embedding: the design-element profile (z and percentile against this
    catalog, the same scale the cards' design terms use) and the ranked items, folding the photo
    into the query at the measured weight (§3.16; `concept_image_weight`, a no-op without a photo).
    Deliberately **not** a new model: the same encoder that indexed the catalog encodes the photo.
    """
    import base64
    import binascii

    e = engine()
    arm = body.arm or os.environ.get("ENGINE02_ARM", "full_zclip3")
    if arm not in ARMS:
        raise HTTPException(400, f"unknown arm {arm!r}; see GET /arms")
    raw = body.image_base64.split(",", 1)[-1]  # tolerate a data: URL prefix
    try:
        blob = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(400, f"image_base64 is not valid base64: {exc}")
    if not blob:
        raise HTTPException(400, "image_base64 is empty")
    limit = int(os.environ.get("ENGINE02_MAX_UPLOAD_MB", "12")) * 1024 * 1024
    if len(blob) > limit:
        raise HTTPException(413, f"image is {len(blob) / 1e6:.1f} MB; the limit is {limit / 1e6:.0f} MB")
    vec = _encode_upload(e, blob)

    out: dict = {"encoder": e.encoder.name, "arm": arm}
    if body.profile:
        from .concepts import element_profile, load_profile_stability

        cache = STATE.setdefault("prompt_cache", {})
        stab = STATE.setdefault("profile_stability", load_profile_stability())
        prof = element_profile(e.encoder, e.image_emb, vec, e.kansei,
                               mode=ARMS[arm].concept_mode, prompt_cache=cache, stability=stab)
        out["profile"] = prof
        shaky = [p["label"] for p in prof if p.get("reliable") is False]
        out["profile_note"] = "z 與百分位都是相對於本商品庫，和卡片上的設計要素用同一把尺"
        if shaky:
            out["profile_caveat"] = (
                "下列要素在『同一件衣服、不同拍攝方式』下不穩定（T16 實測平均 |Δz| > 0.4，"
                f"整體有 9.7% 的要素會正負反轉），只當參考不要當事實：{'、'.join(shaky)}")
    # `constraints` is a free-form dict on this endpoint (the photo is the point, not the JSON), so
    # a malformed one has to come back as a 422 naming the field — the same answer /rank gives —
    # instead of an uncaught ValidationError and a 500.
    try:
        hard = HardConstraints(**body.constraints) if body.constraints else HardConstraints()
    except ValidationError as exc:
        raise HTTPException(422, {"error": "constraints is not a valid HardConstraints object",
                                  "detail": exc.errors(include_url=False)})
    req = Engine02Request(session_id="visual", retrieval_text=body.retrieval_text, constraints=hard,
                          options=Engine02Options(top_k=body.top_k, explain_with_llm=False))
    req.feedback.concept_image_embedding = [float(x) for x in vec]
    resp = rank(req)
    out["response"] = resp.model_dump()
    out["concept_image_weight"] = ARMS[arm].concept_image_weight
    return out


class ConceptImageRequest(BaseModel):
    embedding: list[float]
    k: int = 3


@app.post("/concept-image/nearest")
def concept_image_nearest(body: ConceptImageRequest) -> dict:
    """PRD §6.5 接回推薦: catalog items closest to a generated concept image (display only).

    Deliberately not routed through the reranker — a generated image must never be presented as
    the cause of a ranked recommendation. To fold it into retrieval, send it as
    `feedback.concept_image_embedding` to /rank (weight 0.2 on the serving arm, §3.16).
    """
    from .panels import concept_image_neighbors

    e = engine()
    if len(body.embedding) != e.image_emb.shape[1]:
        raise HTTPException(400, f"embedding must have {e.image_emb.shape[1]} dims for encoder {e.encoder.name}")
    return {"encoder": e.encoder.name, "items": concept_image_neighbors(e, body.embedding, body.k)}


@app.get("/needs/supply")
def needs_supply(arm: str = "full", threshold: float = 0.5) -> dict:
    """PRD §6.7 supply side Sup(n): the share of the catalog that expresses each hidden need.

    ENGINE 03 owns demand D(occasion, n) and the Gap product; this half needs c(i,d).
    """
    from .panels import need_supply

    if arm not in ARMS:
        raise HTTPException(400, f"unknown arm {arm!r}; see GET /arms")
    return {"arm": arm, "threshold": threshold, "n_items": len(engine().catalog),
            "supply": need_supply(engine(), arm, threshold)}


@app.get("/trends")
def trends() -> dict:
    """Trend keywords used for display badges only (set ENGINE02_TRENDS=1 to load them)."""
    t = STATE.get("trends")
    if t is None:
        return {"loaded": False, "reason": "set ENGINE02_TRENDS=1 (or ENGINE02_TRENDS=<file>)",
                "note": "trends are never part of the score: 28 configurations all hurt NDCG@5 (§3.15)"}
    from .trends import trend_coverage

    return {"loaded": True, "source": t.source, "as_of": t.as_of, "ephemeral": t.ephemeral,
            "notes": t.notes, "keywords": t.keywords(),
            "coverage": trend_coverage(engine(), t.keywords()), "used_in_ranking": False}


class CompleteLookRequest(BaseModel):
    anchor_item_ids: list[str]
    n_categories: int = 2
    k: int = 5
    filters: dict[str, list[str]] = {}


@app.post("/complete-look")
def complete_look(body: CompleteLookRequest) -> dict:
    """給一件，推薦能搭的：complementary categories (NPMI) then items (OutfitTransformer / similarity)."""
    try:
        return STATE["service"].complete_look(body.anchor_item_ids, body.n_categories, body.k, body.filters or None)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    except Exception as e:  # a broken model head used to surface as a bare 500 with no hint
        log.exception("/complete-look failed")
        raise HTTPException(500, f"{type(e).__name__}: {e}")


@app.get("/items/{item_id}")
def item(item_id: str) -> dict:
    e = engine()
    pos = e.catalog.pos(item_id)
    if pos is None:
        raise HTTPException(404, "unknown item")
    row = e.catalog.items.iloc[pos].to_dict()
    row["design_scores"] = {el.id: float(e.design_matrix(ARMS["full"])[pos, j]) for j, el in enumerate(e.kansei.elements)}
    return {k: (None if (isinstance(v, float) and v != v) else v) for k, v in row.items() if k != "outfit_ids"}


@app.get("/images/{item_id}")
def image(item_id: str):
    e = engine()
    pos = e.catalog.pos(item_id)
    if pos is None:
        raise HTTPException(404, "unknown item")
    return FileResponse(e.catalog.image_paths()[pos])
