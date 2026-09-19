"""行程穿搭規劃 (itinerary planner): one trip, several stops, one suitcase.

For every event (date + city [+ time, occasion, note]):
  * weather for that day -- the forecast within 15 days, else the 5-year climate normal (labelled)
  * the travel signals (route, transport comfort, climate gap from the previous stop, event hour)
  * a ready-to-send request patch for POST /rank: {"context": ContextInput, "constraints":
    {"occasion": inferred}} -- the previous stop is the event's origin, so hopping 台北 → 札幌 →
    東京 gives each leg its own climate gap
  * if `rank_fn` is given, the top item ids it returns for that ContextInput

For the whole trip: one capsule (services.travel_capsule.plan_capsule over every event's weather;
items that rank_fn put on top for several events get a small score bonus) and packing notes.

All network access is injectable (`forecast_fn`, `geocode_fn`, `hourly_fn`) so tests run offline.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Callable

import pandas as pd

from ..context import geo, travel
from ..context.base import DailyForecast
from ..contracts import ContextInput, ItineraryEvent
from .travel_capsule import _is_rainy, plan_capsule

OCCASION_WORDS = [
    ("Formal", ("婚禮", "婚宴", "喜宴", "晚宴", "典禮", "頒獎", "面試", "正式", "formal", "wedding", "gala")),
    ("Sports", ("爬山", "登山", "健行", "跑步", "運動", "滑雪", "衝浪", "露營", "hike", "ski", "sport")),
    ("Smart Casual", ("商務", "會議", "開會", "拜訪", "約會", "餐廳", "晚餐", "看展", "音樂會", "smart",
                      "business", "dinner", "date")),
    ("Travel", ("觀光", "旅行", "逛街", "市集", "散步", "移動", "飛機", "travel", "sightseeing")),
    ("Casual", ("聚會", "咖啡", "休閒", "野餐", "海邊", "casual", "beach")),
]
CATALOG_OCCASIONS = {"Casual", "Formal", "Smart Casual", "Sports", "Travel", "Ethnic"}


def infer_occasion(occasion: str | None, note: str | None = None) -> str | None:
    """Free text ('婚禮', '海邊晚餐', 'Formal') -> catalog occasion, or None."""
    for text in (occasion, note):
        if not text:
            continue
        t = str(text).strip()
        for cat in CATALOG_OCCASIONS:
            if t.lower() == cat.lower():
                return cat
        low = t.lower()
        for cat, words in OCCASION_WORDS:
            if any(w in low for w in words):
                return cat
    return None


def _top_ids(res, k: int) -> list[str]:
    """rank_fn may return ids, dicts, RankedItem-likes, or a response with `.items`/['items']."""
    if res is None:
        return []
    if isinstance(res, dict):
        res = res.get("items") or res.get("ranked") or []
    elif hasattr(res, "items") and not isinstance(res, (list, tuple)) and not callable(res.items):
        res = res.items
    out = []
    for r in list(res)[:k]:
        if isinstance(r, str):
            out.append(r)
        elif isinstance(r, dict) and r.get("item_id") is not None:
            out.append(str(r["item_id"]))
        elif getattr(r, "item_id", None) is not None:
            out.append(str(r.item_id))
    return out


def _weather_zh(fc: DailyForecast | None) -> str:
    if fc is None:
        return "天氣查不到"
    lo, hi = fc.temp_min_c, fc.temp_max_c
    rng = (f"{lo:.0f}～{hi:.0f}°C" if lo is not None and hi is not None
           else f"{(lo if lo is not None else hi):.0f}°C" if (lo is not None or hi is not None) else "氣溫不明")
    if fc.source == travel.NORMAL_SOURCE:
        s = f"往年平均 {rng}（歷史平均，非預報）"
        if fc.precip_prob_pct is not None and fc.precip_prob_pct >= 30:
            s += f"，往年 {fc.precip_prob_pct:.0f}% 的日子下雨"
        return s
    s = f"預報 {rng}"
    if fc.precip_prob_pct is not None:
        s += f"，降雨 {fc.precip_prob_pct:.0f}%"
    return s


def plan_itinerary(events: list[ItineraryEvent | dict], items: pd.DataFrame,
                   origin: dict | None = None, n_capsule: int = 10, budget: float | None = None,
                   rank_fn: Callable[[ContextInput], Any] | None = None,
                   forecast_fn: Callable | None = None, geocode_fn: Callable | None = None,
                   hourly_fn: Callable | None = None, today: date | str | None = None,
                   top_k: int = 5) -> dict[str, Any]:
    """Per-event contexts + one capsule for the whole trip + packing notes (zh-TW)."""
    forecast_fn = forecast_fn or travel.day_weather       # (lat, lon, date_iso, place, today)
    geocode_fn = geocode_fn or geo.geocode
    hourly_fn = hourly_fn or travel.fetch_hourly
    today_d = travel._as_date(today or date.today())
    evs = [e if isinstance(e, ItineraryEvent) else ItineraryEvent(**e) for e in (events or [])]
    evs.sort(key=lambda e: (e.date, travel.parse_hour(e.time) or 0))

    prev = None
    if origin:
        o = dict(origin)
        prev = {"city": o.get("city") or o.get("origin_city"),
                "lat": o.get("lat", o.get("origin_lat")), "lon": o.get("lon", o.get("origin_lon"))}
        if (prev["lat"] is None or prev["lon"] is None) and prev["city"]:
            g = geocode_fn(prev["city"])
            if g:
                prev["lat"], prev["lon"] = g.get("lat"), g.get("lon")

    out_events: list[dict] = []
    forecasts: list[DailyForecast] = []
    hit_counts: dict[str, float] = {}
    notes_extra: list[str] = []
    missing_weather = 0
    long_flight = False

    for ev in evs:
        lat, lon = ev.lat, ev.lon
        if (lat is None or lon is None) and ev.city:
            g = geocode_fn(ev.city)
            if g:
                lat, lon = g.get("lat"), g.get("lon")
        known = lat is not None and lon is not None
        fc = None
        if known:
            try:
                fc = forecast_fn(lat, lon, ev.date, ev.city or "", today_d)
            except Exception:
                fc = None
        if fc is not None:
            forecasts.append(fc)
        else:
            missing_weather += 1

        moved = prev is not None and (prev.get("city") != ev.city or
                                      (prev.get("lat"), prev.get("lon")) != (lat, lon))
        ctx = ContextInput(city=ev.city, lat=lat, lon=lon, event_date=ev.date, event_time=ev.time,
                           origin_city=prev.get("city") if moved else None,
                           origin_lat=prev.get("lat") if moved else None,
                           origin_lon=prev.get("lon") if moved else None)
        try:
            sigs = travel.signals(ctx, today_d, forecast=fc, geocode_fn=geocode_fn,
                                  day_fn=forecast_fn, hourly_fn=hourly_fn)
        except Exception:
            sigs = []
        for s in sigs:
            if s.detail.get("transport") == "flight" and (s.detail.get("travel_hours") or 0) > 3:
                long_flight = True

        occ = infer_occasion(ev.occasion, ev.note)
        ctx_dict = ctx.model_dump(exclude_none=True, exclude_defaults=True)
        request_patch: dict[str, Any] = {"context": ctx_dict}
        if occ:
            request_patch["constraints"] = {"occasion": {"state": "inferred", "values": [occ]}}

        top: list[str] = []
        rank_error = None
        if rank_fn is not None:
            try:
                top = _top_ids(rank_fn(ctx), top_k)
            except Exception as e:                                   # noqa: BLE001
                rank_error = repr(e)
            for r, iid in enumerate(top):
                hit_counts[iid] = hit_counts.get(iid, 0.0) + 1.0 / (1 + r)

        when = f"{ev.date[5:7].lstrip('0')}/{ev.date[8:10].lstrip('0')}"
        parts = [f"{when} {ev.city or '未定地點'}", _weather_zh(fc)]
        if ev.time:
            parts.append(ev.time)
        if ev.occasion or ev.note:
            parts.append(" ".join(x for x in (ev.occasion, ev.note) if x) + (f" → {occ}" if occ else ""))
        entry = {
            "date": ev.date, "city": ev.city, "time": ev.time, "lat": lat, "lon": lon,
            "occasion": occ, "occasion_text": ev.occasion, "note": ev.note,
            "weather": ({k: v for k, v in fc.__dict__.items() if k != "fetched_at"} if fc else None),
            "weather_source": fc.source if fc else None,
            "summary_zh": "｜".join(parts),
            "signals_zh": [s.label for s in sigs],
            "context": ctx_dict,
            "request_patch": request_patch,
            "top_item_ids": top,
        }
        if rank_error:
            entry["rank_error"] = rank_error
        out_events.append(entry)
        if known:
            prev = {"city": ev.city, "lat": lat, "lon": lon}

    # ---- whole-trip capsule
    scores = {iid: 0.1 * v for iid, v in hit_counts.items()}
    capsule = plan_capsule(items, forecasts, n_items=n_capsule, budget=budget, scores=scores)

    # ---- packing notes
    cities = []
    for e in out_events:
        if e["city"] and e["city"] not in cities:
            cities.append(e["city"])
    los = [f.temp_min_c for f in forecasts if f.temp_min_c is not None]
    his = [f.temp_max_c for f in forecasts if f.temp_max_c is not None]
    span = (max(his + los) - min(los + his)) if (los or his) else None
    rainy = any(_is_rainy(f) for f in forecasts)
    notes: list[str] = []
    head = f"{len(cities)} 個城市" if len(cities) > 1 else (f"{cities[0]} {len(out_events)} 個行程" if cities
                                                          else f"{len(out_events)} 個行程")
    if span is not None:
        style = ("以洋蔥式為主" if span >= 10 else "氣溫穩定，同一組基本款輪流穿就好")
        line = f"{head}、溫差 {span:.0f}°C：{style}"
    else:
        line = f"{head}：天氣查不到，先以好穿脫的洋蔥式準備"
    if rainy:
        line += "，帶一件防潑水外套"
    notes.append(line)
    if los and min(los) <= 5:
        notes.append(f"最冷那天約 {min(los):.0f}°C：厚外套＋發熱衣別省，圍巾占位小又最有感")
    if his and max(his) >= 30:
        notes.append(f"最熱那天約 {max(his):.0f}°C：透氣短袖多帶兩件，汗濕好替換")
    formal = [e for e in out_events if e["occasion"] == "Formal"]
    if formal:
        what = "、".join(dict.fromkeys(e["occasion_text"] or e["note"] or "正式場合" for e in formal))
        notes.append(f"有正式場合（{what}）：行李箱多留一套正式服＋一雙好鞋的位置")
    if any(e["occasion"] == "Sports" for e in out_events):
        notes.append("有戶外活動：一雙好走的鞋、一件機能外層，比多帶一件上衣實用")
    if long_flight:
        notes.append("長途飛行那天穿最舒服、不易皺的那套，外套上機當毯子")
    n_normal = sum(1 for f in forecasts if f.source == travel.NORMAL_SOURCE)
    if n_normal:
        notes.append(f"{n_normal} 天超出預報範圍，用往年平均估算；出發前一週再看一次預報")
    if missing_weather:
        notes.append(f"{missing_weather} 天查不到天氣，先照同城市其他天準備")
    notes += notes_extra

    return {
        "events": out_events,
        "capsule": capsule,
        "packing_notes_zh": notes,
        "trip": {"cities": cities, "n_events": len(out_events),
                 "dates": [e["date"] for e in out_events], "temp_span_c": span,
                 "rainy": rainy, "climate_normal_days": n_normal},
    }
