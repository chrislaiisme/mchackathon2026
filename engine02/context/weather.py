"""Weather -> ranking preferences (intuition v0, not yet measured).

`fetch_forecast` talks to Open-Meteo (free, no key) and caches one JSON per (lat, lon, date) under
data/context/. It never raises: any failure returns None and the weather signal simply disappears.

`signals` turns one DailyForecast into a handful of small, explainable ContextSignals:
  * 體感溫度 -> warmth target (0..3)
  * 下雨機率 -> water-repellent + outerwear, avoid light colours that show splashes
  * 紫外線   -> light, reflective colours
  * 強風     -> tailored / structured over relaxed & flowy
  * 日夜溫差 -> 洋蔥式穿搭 (layering: outerwear)
  * 悶熱     -> light & sporty/breathable
`derive_warmth` / `derive_water_repellent` fill the agreed catalog columns from product text.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

from .base import AttributePref, ContextSignal, DailyForecast

API_URL = "https://api.open-meteo.com/v1/forecast"
DAILY_VARS = ("temperature_2m_max", "temperature_2m_min", "apparent_temperature_max",
              "apparent_temperature_min", "precipitation_probability_max", "precipitation_sum",
              "wind_speed_10m_max", "uv_index_max")
CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "context"
EVIDENCE = "intuition v0 (not yet measured)"

LIGHT_COLORS = ["White", "Off White", "Cream", "Beige", "Skin", "Nude"]
SUN_COLORS = ["White", "Off White", "Cream", "Beige", "Khaki", "Grey", "Silver", "Lavender",
              "Peach", "Yellow"]
DARK_COLORS = ["Black", "Navy Blue", "Charcoal", "Maroon", "Burgundy", "Coffee Brown"]


# ---------------------------------------------------------------------------
# fetching
# ---------------------------------------------------------------------------

def _cache_path(lat: float, lon: float, date_iso: str) -> Path:
    return CACHE_DIR / f"forecast_{lat:.2f}_{lon:.2f}_{date_iso}.json"


def _pick(daily: dict, key: str):
    vals = daily.get(key) or []
    v = vals[0] if vals else None
    return float(v) if v is not None else None


def fetch_forecast(lat: float, lon: float, date_iso: str, place: str = "",
                   timeout: float = 3.0) -> DailyForecast | None:
    """One day of Open-Meteo forecast at (lat, lon); cached on disk; None on any failure."""
    try:
        lat, lon = float(lat), float(lon)
        date_iso = str(date_iso)[:10]
        cache = _cache_path(lat, lon, date_iso)
        if cache.exists():
            try:
                d = json.loads(cache.read_text(encoding="utf-8"))
                d["place"] = place or d.get("place", "")
                return DailyForecast(**d)
            except Exception:
                pass                                   # corrupt cache -> refetch
        import requests
        params = {"latitude": lat, "longitude": lon, "daily": ",".join(DAILY_VARS),
                  "timezone": "Asia/Taipei", "start_date": date_iso, "end_date": date_iso}
        r = requests.get(API_URL, params=params, timeout=timeout)
        r.raise_for_status()
        daily = r.json().get("daily") or {}
        if not daily.get("time"):
            return None
        fc = DailyForecast(
            date=date_iso, place=place, lat=lat, lon=lon,
            temp_max_c=_pick(daily, "temperature_2m_max"),
            temp_min_c=_pick(daily, "temperature_2m_min"),
            apparent_max_c=_pick(daily, "apparent_temperature_max"),
            apparent_min_c=_pick(daily, "apparent_temperature_min"),
            precip_prob_pct=_pick(daily, "precipitation_probability_max"),
            precip_mm=_pick(daily, "precipitation_sum"),
            wind_max_kmh=_pick(daily, "wind_speed_10m_max"),
            uv_index_max=_pick(daily, "uv_index_max"),
            source="open-meteo", fetched_at=datetime.now().isoformat(timespec="seconds"))
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(fc.__dict__, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception:
            pass                                       # read-only disk: still return the forecast
        return fc
    except Exception:
        return None


# ---------------------------------------------------------------------------
# forecast -> signals
# ---------------------------------------------------------------------------

def warmth_target(feels_c: float) -> int:
    """Apparent temperature (°C) -> warmth 0..3."""
    if feels_c <= 12:
        return 3
    if feels_c <= 18:
        return 2
    if feels_c <= 25:
        return 1
    return 0


WARMTH_WORDS = {3: "厚外套、羊毛針織才夠暖", 2: "薄外套或針織衫剛剛好", 1: "長袖單穿就舒服",
                0: "短袖、透氣輕薄最實在"}


def _feels_like(fc: DailyForecast) -> float | None:
    """Representative 'what you feel when out' temperature: mean of apparent max/min, else raw."""
    lo = fc.apparent_min_c if fc.apparent_min_c is not None else fc.temp_min_c
    hi = fc.apparent_max_c if fc.apparent_max_c is not None else fc.temp_max_c
    if lo is None and hi is None:
        return None
    if lo is None or hi is None:
        return lo if hi is None else hi
    return (lo + hi) / 2


def _when(fc: DailyForecast, today) -> str:
    try:
        t = today if isinstance(today, date) else date.fromisoformat(str(today)[:10])
        d = date.fromisoformat(fc.date)
        delta = (d - t).days
        return {0: "今天", 1: "明天", 2: "後天"}.get(delta, f"{d.month}/{d.day}")
    except Exception:
        return "當天"


def _resolve_forecast(ctx, today) -> DailyForecast | None:
    lat, lon = getattr(ctx, "lat", None), getattr(ctx, "lon", None)
    if lat is None or lon is None:
        return None
    day = getattr(ctx, "event_date", None) or (today.isoformat() if hasattr(today, "isoformat")
                                                else str(today))
    return fetch_forecast(lat, lon, str(day)[:10], place=getattr(ctx, "city", None) or "")


def _sig(label: str, prefs=None, design=None, detail=None) -> ContextSignal:
    return ContextSignal(source="weather", label=label, prefs=prefs or [], design_steps=design or {},
                         affects_ranking=True, opt_in=False, evidence=EVIDENCE, detail=detail or {})


def signals(ctx, today, forecast: DailyForecast | None = None) -> list[ContextSignal]:
    """Forecast -> list of weather ContextSignals (empty when no forecast is available)."""
    fc = forecast if forecast is not None else _resolve_forecast(ctx, today)
    if fc is None:
        return []
    place = fc.place or (getattr(ctx, "city", None) or "")
    head = f"{_when(fc, today)}{place}"
    raw = {k: v for k, v in fc.__dict__.items() if k not in ("source", "fetched_at")}
    out: list[ContextSignal] = []

    feels = _feels_like(fc)
    rain = fc.precip_prob_pct if fc.precip_prob_pct is not None else 0.0
    rain_mm = fc.precip_mm or 0.0
    wind = fc.wind_max_kmh or 0.0
    uv = fc.uv_index_max or 0.0

    # 1) 體感溫度 -> warmth
    if feels is not None:
        tgt = warmth_target(feels)
        prefs = [AttributePref("warmth", 0.3, f"體感 {feels:.0f}°C", target=float(tgt))]
        if tgt == 3:
            prefs.append(AttributePref("season", 0.15, "冬季款", values=["Winter", "Fall"]))
        elif tgt == 0:
            prefs.append(AttributePref("season", 0.15, "夏季款", values=["Summer", "Spring"]))
        out.append(_sig(f"{head}體感 {feels:.0f}°C → {WARMTH_WORDS[tgt]}", prefs,
                        design={"soft_knit": 1.0} if tgt >= 2 else {},
                        detail={**raw, "feels_like_c": feels, "warmth_target": tgt}))

    # 2) 下雨
    if rain >= 60 or rain_mm >= 10:
        heavy = rain >= 80 or rain_mm >= 20
        w = 0.4 if heavy else 0.3
        prefs = [AttributePref("water_repellent", w, "防潑水", values=[True]),
                 AttributePref("category", 0.15, "帶件外套擋雨", values=["outerwear"]),
                 AttributePref("color", -0.15, "淺色怕泥水濺", values=LIGHT_COLORS)]
        label = (f"{head}降雨 {rain:.0f}%" + ("（大雨警報）" if heavy else "")
                 + " → 幫你挑了防潑水外套，淺色先放一邊")
        out.append(_sig(label, prefs, design={"glossy_fabric": 1.0, "matte_fabric": -1.0},
                        detail={**raw, "rain_trigger": True}))
    elif 30 <= rain < 60:
        out.append(_sig(f"{head}降雨 {rain:.0f}%，午後雷陣雨機率 → 包包裡塞件薄外套",
                        [AttributePref("category", 0.1, "可收納薄外套", values=["outerwear"]),
                         AttributePref("water_repellent", 0.1, "防潑水加分", values=[True])],
                        detail={**raw, "rain_trigger": "maybe"}))

    # 3) 紫外線
    if uv >= 7:
        strong = uv >= 10
        prefs = [AttributePref("color", 0.25 if strong else 0.2, "淺色反光不吸熱", values=SUN_COLORS),
                 AttributePref("color", -0.15, "深色吸熱", values=DARK_COLORS),
                 AttributePref("category", 0.1, "帽子/配件遮陽", values=["accessory"])]
        tag = "紫爆級" if strong else "過量級"
        out.append(_sig(f"{head}紫外線 {uv:.0f}（{tag}）→ 淺色系、配頂帽子，防曬也要有型",
                        prefs, design={"bright_color": 1.0, "dark_tone": -1.0},
                        detail={**raw, "uv_trigger": True}))

    # 4) 強風
    if wind >= 35:
        prefs = [AttributePref("category", -0.15, "長洋裝被風吹會很狼狽", values=["dress"])]
        out.append(_sig(f"{head}陣風 {wind:.0f} km/h → 挑合身有版型的，不怕被吹成風箏",
                        prefs, design={"tailored_fit": 1.0, "relaxed_fit": -1.0,
                                       "structured_shoulders": 1.0},
                        detail={**raw, "wind_trigger": True}))

    # 5) 日夜溫差 -> 洋蔥式穿搭
    if fc.temp_max_c is not None and fc.temp_min_c is not None:
        swing = fc.temp_max_c - fc.temp_min_c
        if swing >= 8:
            out.append(_sig(f"{head}日夜溫差 {swing:.0f}°C → 洋蔥式穿搭，早晚加一件外套",
                            [AttributePref("category", 0.2, "可穿脫的外層", values=["outerwear"])],
                            design={"soft_knit": 1.0},
                            detail={**raw, "swing_c": swing}))

    # 6) 悶熱（台灣夏天限定）
    if feels is not None and feels >= 32:
        out.append(_sig(f"{head}體感 {feels:.0f}°C 悶熱模式 → 透氣運動風，別讓汗濕說話",
                        [AttributePref("style", 0.15, "透氣機能", values=["sporty", "minimalist"]),
                         AttributePref("warmth", 0.2, "越輕越好", target=0.0)],
                        design={"athletic_style": 1.0, "soft_knit": -1.0},
                        detail={**raw, "muggy": True}))
    return out


# ---------------------------------------------------------------------------
# catalog column derivation
# ---------------------------------------------------------------------------

WARM3 = ["puffer", "padded", "down jacket", "down coat", "parka", "wool coat", "fleece", "quilted",
         "thermal", "sherpa", "teddy", "shearling", "overcoat", "duffle", "winter coat", "boots",
         "heavy knit", "chunky knit", "faux fur"]
WARM2 = ["wool", "coat", "sweater", "knit", "cardigan", "hoodie", "sweatshirt", "jacket", "blazer",
         "turtleneck", "jumper", "pullover", "cashmere", "flannel", "corduroy", "trench", "fleece"]
LIGHT0 = ["linen", "sleeveless", "tank", "camisole", "cami ", "shorts", "sandal", "flip flop",
          "slipper", "swim", "bikini", "mesh", "crop top", "strappy", "vest top", "short sleeve",
          "short-sleeve", "flip-flop", "tube top", "chiffon", "seersucker"]
WATER = ["water-repellent", "water repellent", "waterproof", "water-proof", "rain", "shell jacket",
         "windbreaker", "gore-tex", "goretex", "anorak", "wind- and water", "water-resistant",
         "water resistant", "raincoat"]
_TEXT_COLS = ("title", "prod_name", "productDisplayName", "product_type_name", "subcategory",
              "subCategory", "articleType", "category", "detail_desc", "description",
              "product_group_name", "graphical_appearance_name")


def _text(items):
    import pandas as pd
    cols = [c for c in _TEXT_COLS if c in items.columns]
    if not cols:
        return pd.Series([""] * len(items), index=items.index)
    return items[cols].fillna("").astype(str).agg(" ".join, axis=1).str.lower()


def _has_any(text, words):
    pat = "|".join(re.escape(w) for w in words)
    return text.str.contains(pat, regex=True)


def derive_warmth(items):
    """0 (tank, sandals) .. 3 (puffer, wool coat) from product text; default 1."""
    import pandas as pd
    text = _text(items)
    warmth = pd.Series(1, index=items.index, dtype="int64")
    if not len(items):
        return warmth
    light = _has_any(text, LIGHT0)
    w2 = _has_any(text, WARM2)
    w3 = _has_any(text, WARM3)
    warmth[light] = 0
    warmth[w2] = 2
    warmth[w3] = 3
    # "sleeveless padded vest" / "wool shorts": warm fabric wins but not all the way
    warmth[w3 & light] = 2
    warmth[w2 & ~w3 & light] = 1
    return warmth.clip(0, 3).astype("int64")


def derive_water_repellent(items):
    """True when the item's own text says water-repellent / waterproof / rain."""
    import pandas as pd
    text = _text(items)
    if not len(items):
        return pd.Series([], index=items.index, dtype=bool)
    # 'rain' but not 'grain'/'drain'/'train(er)'
    wr = _has_any(text, [w for w in WATER if w != "rain"]) | text.str.contains(r"\brain", regex=True)
    return wr.astype(bool)
