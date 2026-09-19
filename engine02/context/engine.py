"""Glue: ContextInput -> ContextSignals (from every available module) -> per-item scores.

Modules are discovered by name and must expose `signals(ctx, today, **kw) -> list[ContextSignal]`.
A module that is missing or raises is skipped and reported, never fatal: context is garnish on
the user's request, and a broken garnish must not take the recommendation down with it.

The pipeline adds ONE term per ranking signal, "context:<source>[:n]", with normalize=False and
weight 1.0, so a card that says "+0.30" means exactly +0.30 of score.
"""

from __future__ import annotations

import importlib
import json
import os
from contextvars import ContextVar
from datetime import date

import numpy as np
import pandas as pd

from .base import ContextSignal, DailyForecast

MODULES = ("weather", "commute", "festival", "lucky", "personal")
FORECAST_MODULES = {"weather", "commute"}
DESIGN_GAMMA = 0.1           # a context design step moves a card at most this much per unit c(i,d)

# term name -> card label, for the request being ranked right now (read by explain.template_reasons)
CONTEXT_LABELS: ContextVar[dict[str, str]] = ContextVar("CONTEXT_LABELS", default={})


def is_empty(ctx) -> bool:
    if ctx is None:
        return True
    return not any([ctx.lat is not None and ctx.lon is not None, ctx.event_date, ctx.commute, ctx.mood,
                    ctx.personal_color, ctx.lucky, ctx.city])


def build_signals(ctx, today: date | None = None, forecast=None,
                  allow_network: bool | None = None) -> tuple[list[ContextSignal], list[dict]]:
    """All signals for this shopper's situation, plus a list of module problems (never raises)."""
    if is_empty(ctx):
        return [], []
    today = today or date.today()
    if allow_network is None:
        allow_network = os.environ.get("ENGINE02_DEMO") != "1"
    problems: list[dict] = []
    fc = forecast
    fctx = ctx                                          # what the forecast-using modules see
    if fc is None and ctx.lat is not None and ctx.lon is not None:
        try:
            weather = importlib.import_module(".weather", __package__)
            day = ctx.event_date or today.isoformat()
            if allow_network:
                fc = weather.fetch_forecast(ctx.lat, ctx.lon, day, place=ctx.city or "")
            else:
                # demo mode: never touch the network on the request path -- a forecast fetched
                # earlier (scripts or GET /context/forecast) is used if cached, otherwise none
                cache = weather._cache_path(ctx.lat, ctx.lon, day)
                if cache.exists():
                    fc = DailyForecast(**json.loads(cache.read_text(encoding="utf-8")))
        except Exception as e:                                   # noqa: BLE001
            problems.append({"module": "weather.forecast", "error": repr(e)})
        if fc is None:
            # without this the modules would go and fetch it themselves
            fctx = ctx.model_copy(update={"lat": None, "lon": None})
            problems.append({"module": "weather", "error": "no forecast available (offline or not cached)"})
    out: list[ContextSignal] = []
    for name in MODULES:
        try:
            mod = importlib.import_module(f".{name}", __package__)
        except ImportError:
            continue
        fn = getattr(mod, "signals", None)
        if fn is None:
            continue
        try:
            got = fn(fctx, today, forecast=fc) if name in FORECAST_MODULES else fn(ctx, today)
            out += [s for s in (got or []) if isinstance(s, ContextSignal)]
        except Exception as e:                                   # noqa: BLE001
            problems.append({"module": name, "error": repr(e)})
    return out, problems


_ENRICHED: dict[int, pd.DataFrame] = {}


def enriched(items: pd.DataFrame) -> pd.DataFrame:
    """Add `warmth` / `water_repellent` when the catalog lacks them (derived from its own text)."""
    key = id(items)
    if key in _ENRICHED:
        return _ENRICHED[key]
    df = items
    need = [c for c in ("warmth", "water_repellent") if c not in items.columns]
    if need:
        try:
            weather = importlib.import_module(".weather", __package__)
            df = items.copy()
            if "warmth" in need:
                df["warmth"] = weather.derive_warmth(items)
            if "water_repellent" in need:
                df["water_repellent"] = weather.derive_water_repellent(items)
        except Exception:                                        # noqa: BLE001
            df = items
    _ENRICHED[key] = df
    return df


def item_scores(sig: ContextSignal, items: pd.DataFrame, pos, c_mat=None,
                element_ids: list[str] | None = None) -> np.ndarray:
    """What one signal adds to each candidate's score (0 where nothing applies)."""
    pos = np.asarray(pos, dtype=int)
    s = np.zeros(len(pos), dtype=np.float64)
    for p in sig.prefs:
        if p.column not in items.columns:
            continue
        col = items[p.column].to_numpy()[pos]
        if p.values is not None:
            wanted = set(p.values)
            s += p.weight * np.array([v in wanted for v in col], dtype=np.float64)
        else:
            x = pd.to_numeric(pd.Series(col), errors="coerce").to_numpy(dtype=np.float64)
            close = np.clip(1.0 - np.abs(x - float(p.target)) / max(p.scale, 1e-9), 0.0, 1.0)
            s += p.weight * np.nan_to_num(close, nan=0.0)
    if sig.design_steps and c_mat is not None and element_ids:
        for d, step in sig.design_steps.items():
            if d in element_ids:
                z = np.clip(np.asarray(c_mat[pos, element_ids.index(d)], dtype=np.float64), -3, 3) / 3.0
                s += DESIGN_GAMMA * float(step) * z
    return s
