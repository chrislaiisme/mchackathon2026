"""HTTP endpoints for context, personal options, services and the manufacturer's demand radar.

    POST /context/signals        what the shopper's situation says (incl. display-only signals)
    POST /context/forecast       pre-fetch a forecast so the offline demo path can use it
    GET  /context/quiz           personal-colour quiz questions
    POST /context/quiz           score the quiz -> personal_color
    POST /context/demand         情境需求雷達 for the back office (next N days)
    POST /services/capsule       旅行打包膠囊衣櫥
    POST /services/dress-code    服裝規定解碼器
    POST /services/rent-or-buy   租還是買

Everything here is "intuition v0": creative, explained, and labelled as not yet measured.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .contracts import ContextInput

router = APIRouter()
RES = Path(__file__).resolve().parent / "resources"


def _engine():
    from .api import engine
    return engine()


def _items():
    from .context.engine import enriched
    return enriched(_engine().catalog.items)


def _festivals() -> list[dict]:
    f = RES / "tw_festivals.json"
    if not f.exists():
        return []
    try:
        doc = json.loads(f.read_text(encoding="utf-8"))
        return doc if isinstance(doc, list) else (doc.get("occasions") or doc.get("festivals") or [])
    except (OSError, ValueError):
        return []


def _forecasts(lat: float, lon: float, start: date, days: int, place: str):
    from .context.weather import fetch_forecast
    out = []
    for k in range(max(1, min(days, 16))):          # Open-Meteo forecasts ~16 days ahead
        fc = fetch_forecast(lat, lon, (start + timedelta(days=k)).isoformat(), place=place)
        if fc is not None:
            out.append(fc)
    return out


def _signal_json(s) -> dict:
    return {"source": s.source, "label": s.label, "affects_ranking": s.affects_ranking,
            "opt_in": s.opt_in, "evidence": s.evidence, "design_steps": s.design_steps,
            "prefs": [{"column": p.column, "weight": p.weight, "values": p.values, "target": p.target,
                       "reason": p.reason} for p in s.prefs],
            "detail": s.detail}


@router.post("/context/signals")
def context_signals(ctx: ContextInput) -> dict:
    from .context.engine import build_signals
    sigs, problems = build_signals(ctx)
    return {"signals": [_signal_json(s) for s in sigs], "problems": problems,
            "note": "affects_ranking=false 的訊號只顯示給使用者，不影響排序；全部為 intuition v0，尚未驗證"}


class ForecastReq(BaseModel):
    lat: float
    lon: float
    date: str | None = None
    city: str = ""


@router.post("/context/forecast")
def context_forecast(body: ForecastReq) -> dict:
    """Explicit pre-fetch (network): after this, the offline demo path can use the cached forecast."""
    from .context.weather import fetch_forecast
    fc = fetch_forecast(body.lat, body.lon, body.date or date.today().isoformat(), place=body.city)
    if fc is None:
        raise HTTPException(503, "forecast unavailable (network or Open-Meteo)")
    return {"forecast": fc.__dict__, "cached": True}


@router.get("/context/quiz")
def quiz_questions() -> dict:
    from .context.quiz import QUESTIONS
    return {"questions": QUESTIONS}


class QuizAnswers(BaseModel):
    answers: dict


@router.post("/context/quiz")
def quiz_score(body: QuizAnswers) -> dict:
    from .context.quiz import score_quiz
    return score_quiz(body.answers)


class DemandReq(BaseModel):
    lat: float = 25.03
    lon: float = 121.56
    city: str = "台北"
    days: int = 14


@router.post("/context/demand")
def context_demand(body: DemandReq) -> dict:
    from .context.demand import demand_outlook
    today = date.today()
    fcs = _forecasts(body.lat, body.lon, today, body.days, body.city)
    return demand_outlook(fcs, _festivals(), items=_items(), horizon_days=body.days, today=today)


class CapsuleReq(BaseModel):
    lat: float
    lon: float
    city: str = ""
    start_date: str | None = None
    days: int = 3
    n_items: int = 8
    budget: float | None = None
    gender: str | None = None


@router.post("/services/capsule")
def services_capsule(body: CapsuleReq) -> dict:
    from .services import plan_capsule
    start = date.fromisoformat(body.start_date) if body.start_date else date.today()
    fcs = _forecasts(body.lat, body.lon, start, body.days, body.city)
    items = _items()
    if body.gender and "gender" in items.columns:
        items = items[items["gender"].isin([body.gender, "Unisex"])]
    out = plan_capsule(items, fcs, n_items=body.n_items, budget=body.budget)
    out["forecast_days"] = len(fcs)
    return out


class DressCodeReq(BaseModel):
    text: str


@router.post("/services/dress-code")
def services_dress_code(body: DressCodeReq) -> dict:
    from .services import decode
    return decode(body.text)


class RentReq(BaseModel):
    item_id: str
    occasion: str | None = None
    times_expected: int | None = None


@router.post("/services/rent-or-buy")
def services_rent_or_buy(body: RentReq) -> dict:
    from .services import advise
    items = _items()
    e = _engine()
    pos = e.catalog.pos(body.item_id)
    if pos is None:
        raise HTTPException(404, "unknown item")
    row = {k: (None if (isinstance(v, float) and v != v) else v) for k, v in items.iloc[pos].to_dict().items()}
    return advise(row, body.occasion, body.times_expected)


class ItineraryReq(BaseModel):
    events: list[dict]                           # [{date, city|lat/lon, time?, occasion?, note?}]
    origin: dict | None = None                   # {city} or {lat, lon}
    n_capsule: int = 10
    budget: float | None = None
    top_k: int = 5


@router.post("/services/itinerary")
def services_itinerary(body: ItineraryReq) -> dict:
    """行程表 -> per-event weather/climate + a suggested /rank context and top items, plus one capsule."""
    from .contracts import Engine02Options, Engine02Request
    from .services.itinerary import plan_itinerary
    from .api import STATE

    svc = STATE.get("service")

    def rank_fn(ctx):
        if svc is None:
            return []
        req = Engine02Request(session_id="itinerary", retrieval_text="outfit", context=ctx,
                              options=Engine02Options(top_k=body.top_k, explain_with_llm=False))
        return svc.rank(req)

    return plan_itinerary(body.events, _items(), origin=body.origin, n_capsule=body.n_capsule,
                          budget=body.budget, rank_fn=rank_fn, top_k=body.top_k)
