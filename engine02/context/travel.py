"""Travel -> ranking preferences (intuition v0, not yet measured).

The outfit is worn at ctx.city / (lat, lon) on ctx.event_date; the shopper comes FROM
ctx.origin_city / (origin_lat, origin_lon). Signals:

  * 路線     台北 → 札幌 約 2,400 km・飛行約 3.7 小時          (shown, not scored)
  * 交通舒適 長途飛行 -> 軟針織、寬鬆不易皺；高鐵/火車 -> smart casual；機車 -> 擋風防潑水
  * 氣候落差 origin vs destination on the event date -> 洋蔥式穿搭＋一件可脫的外套
  * 往年平均 event date beyond the forecast horizon (> 15 days) -> the same calendar dates of the
             last 5 years from the Open-Meteo Historical Weather API (clearly labelled 非預報)
  * 活動時段 event_time -> hourly apparent temperature at that hour vs the daytime peak

Every network call goes through a function that can be injected (`geocode_fn`, `day_fn`,
`hourly_fn`) or monkeypatched, and every fetcher caches under data/context/ and never raises.
With ENGINE02_DEMO=1 the fetchers only read their caches (no network on the request path).
"""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path

from . import geo, weather
from .base import MAX_SIGNAL_WEIGHT, AttributePref, ContextSignal, DailyForecast

EVIDENCE = "intuition v0 (not yet measured)"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "context"
FORECAST_HORIZON_DAYS = 15
NORMAL_YEARS = 5
NORMAL_WINDOW_DAYS = 3                 # same calendar date ± 3 days, per year
NORMAL_SOURCE = "climate-normal-5y"
GAP_MIN_C = 6.0                        # origin/destination gap worth a signal
EVENING_DROP_C = 4.0                   # event hour this much colder than the day's peak -> jacket

ARCHIVE_DAILY = ("temperature_2m_max", "temperature_2m_min", "apparent_temperature_max",
                 "apparent_temperature_min", "precipitation_sum", "wind_speed_10m_max")
ARCHIVE_HOURLY = ("temperature_2m", "apparent_temperature", "precipitation")
FORECAST_HOURLY = ("temperature_2m", "apparent_temperature", "precipitation_probability")


def _cap(w: float) -> float:
    return max(-MAX_SIGNAL_WEIGHT, min(MAX_SIGNAL_WEIGHT, w))


def _network_allowed() -> bool:
    return os.environ.get("ENGINE02_DEMO") != "1"


def _as_date(x) -> date:
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, date):
        return x
    return date.fromisoformat(str(x)[:10])


def _read_cache(path: Path):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None


def _write_cache(path: Path, obj) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


def _mean(xs):
    xs = [float(x) for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


# ---------------------------------------------------------------------------
# fetching: climate normals (archive) and hourly forecast
# ---------------------------------------------------------------------------

def _same_day(year: int, d: date) -> date:
    try:
        return d.replace(year=year)
    except ValueError:                                  # 2/29 in a non-leap year
        return d.replace(year=year, day=28)


def fetch_climate_normals(lat: float, lon: float, date_iso: str, years: int = NORMAL_YEARS,
                          window: int = NORMAL_WINDOW_DAYS, timeout: float = 5.0) -> dict | None:
    """Average of the same calendar dates (± window) over the last `years` complete years.

    Returns {"daily": {temp_max_c, temp_min_c, apparent_max_c, apparent_min_c, precip_mm,
    precip_prob_pct (= share of days with >= 1 mm), wind_max_kmh}, "hourly": {"0".."23": {temp_c,
    feels_c, precip_prob_pct}}, "years": [...], "n_days": int}; cached; None on any failure."""
    try:
        lat, lon = float(lat), float(lon)
        d = _as_date(date_iso)
        cache = CACHE_DIR / f"normals_{lat:.2f}_{lon:.2f}_{d.month:02d}{d.day:02d}_{years}y.json"
        hit = _read_cache(cache)
        if hit and hit.get("daily"):
            return hit
        if not _network_allowed():
            return None
        import requests
        last_year = min(d.year, date.today().year) - 1
        days: list[dict] = []
        hours: dict[int, list[dict]] = {h: [] for h in range(24)}
        used_years = []
        for y in range(last_year - years + 1, last_year + 1):
            c = _same_day(y, d)
            params = {"latitude": lat, "longitude": lon,
                      "start_date": (c - timedelta(days=window)).isoformat(),
                      "end_date": (c + timedelta(days=window)).isoformat(),
                      "daily": ",".join(ARCHIVE_DAILY), "hourly": ",".join(ARCHIVE_HOURLY),
                      "timezone": "auto"}
            try:
                r = requests.get(ARCHIVE_URL, params=params, timeout=timeout)
                r.raise_for_status()
                js = r.json() or {}
            except Exception:
                continue
            daily, hourly = js.get("daily") or {}, js.get("hourly") or {}
            for k in range(len(daily.get("time") or [])):
                days.append({v: (daily.get(v) or [None] * (k + 1))[k] for v in ARCHIVE_DAILY})
            for k, t in enumerate(hourly.get("time") or []):
                h = int(str(t)[11:13])
                hours[h].append({v: (hourly.get(v) or [None] * (k + 1))[k] for v in ARCHIVE_HOURLY})
            used_years.append(y)
        if not days:
            return None
        rain_days = [x["precipitation_sum"] for x in days if x.get("precipitation_sum") is not None]
        out = {
            "daily": {
                "temp_max_c": _mean(x["temperature_2m_max"] for x in days),
                "temp_min_c": _mean(x["temperature_2m_min"] for x in days),
                "apparent_max_c": _mean(x["apparent_temperature_max"] for x in days),
                "apparent_min_c": _mean(x["apparent_temperature_min"] for x in days),
                "precip_mm": _mean(rain_days),
                "precip_prob_pct": (100.0 * sum(1 for p in rain_days if p >= 1.0) / len(rain_days)
                                    if rain_days else None),
                "wind_max_kmh": _mean(x["wind_speed_10m_max"] for x in days),
            },
            "hourly": {str(h): {"temp_c": _mean(x["temperature_2m"] for x in rows),
                                "feels_c": _mean(x["apparent_temperature"] for x in rows),
                                "precip_prob_pct": (100.0 * sum(1 for x in rows
                                                                if (x["precipitation"] or 0) >= 0.2)
                                                    / len(rows)) if rows else None}
                       for h, rows in hours.items()},
            "years": used_years, "n_days": len(days),
            "fetched_at": datetime.now().isoformat(timespec="seconds"),
        }
        _write_cache(cache, out)
        return out
    except Exception:
        return None


def normals_forecast(lat: float, lon: float, date_iso: str, place: str = "") -> DailyForecast | None:
    """Climate normals as a DailyForecast (source='climate-normal-5y') so services can use it."""
    n = fetch_climate_normals(lat, lon, date_iso)
    if not n or not n.get("daily"):
        return None
    d = n["daily"]
    return DailyForecast(date=str(date_iso)[:10], place=place, lat=float(lat), lon=float(lon),
                         temp_max_c=d.get("temp_max_c"), temp_min_c=d.get("temp_min_c"),
                         apparent_max_c=d.get("apparent_max_c"), apparent_min_c=d.get("apparent_min_c"),
                         precip_prob_pct=d.get("precip_prob_pct"), precip_mm=d.get("precip_mm"),
                         wind_max_kmh=d.get("wind_max_kmh"), source=NORMAL_SOURCE,
                         fetched_at=n.get("fetched_at"))


def _within_horizon(date_iso: str, today) -> bool:
    try:
        return (_as_date(date_iso) - _as_date(today or date.today())).days <= FORECAST_HORIZON_DAYS
    except Exception:
        return True


def day_weather(lat: float, lon: float, date_iso: str, place: str = "",
                today=None) -> DailyForecast | None:
    """The best available day at (lat, lon): forecast within 15 days, else 5-year climate normals."""
    try:
        date_iso = str(date_iso)[:10]
        if _within_horizon(date_iso, today):
            if _network_allowed():
                fc = weather.fetch_forecast(lat, lon, date_iso, place=place)
            else:
                raw = _read_cache(weather._cache_path(float(lat), float(lon), date_iso))
                fc = DailyForecast(**{**raw, "place": place}) if raw else None
            if fc is not None:
                return fc
        return normals_forecast(lat, lon, date_iso, place=place)
    except Exception:
        return None


def fetch_hourly(lat: float, lon: float, date_iso: str, place: str = "", today=None,
                 timeout: float = 3.0) -> dict | None:
    """{"source": "open-meteo"|"climate-normal-5y", "hours": {0..23: {temp_c, feels_c,
    precip_prob_pct}}} in local time at (lat, lon); None on any failure."""
    try:
        lat, lon = float(lat), float(lon)
        date_iso = str(date_iso)[:10]
        if _within_horizon(date_iso, today):
            cache = CACHE_DIR / f"hourly_{lat:.2f}_{lon:.2f}_{date_iso}.json"
            hit = _read_cache(cache)
            if not hit and _network_allowed():
                import requests
                params = {"latitude": lat, "longitude": lon, "hourly": ",".join(FORECAST_HOURLY),
                          "timezone": "auto", "start_date": date_iso, "end_date": date_iso}
                r = requests.get(FORECAST_URL, params=params, timeout=timeout)
                r.raise_for_status()
                hr = (r.json() or {}).get("hourly") or {}
                hours = {}
                for k, t in enumerate(hr.get("time") or []):
                    hours[str(int(str(t)[11:13]))] = {
                        "temp_c": hr["temperature_2m"][k], "feels_c": hr["apparent_temperature"][k],
                        "precip_prob_pct": (hr.get("precipitation_probability") or [None] * (k + 1))[k]}
                if hours:
                    hit = {"source": "open-meteo", "hours": hours,
                           "fetched_at": datetime.now().isoformat(timespec="seconds")}
                    _write_cache(cache, hit)
            if hit:
                return {"source": hit.get("source", "open-meteo"),
                        "hours": {int(h): v for h, v in hit["hours"].items()}}
        n = fetch_climate_normals(lat, lon, date_iso)
        if n and n.get("hourly"):
            return {"source": NORMAL_SOURCE, "hours": {int(h): v for h, v in n["hourly"].items()}}
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _rep_temp(fc: DailyForecast | None) -> float | None:
    """'What the day is like' in plain air temperature (mean of max/min), else apparent."""
    if fc is None:
        return None
    t = _mean([fc.temp_max_c, fc.temp_min_c])
    return t if t is not None else _mean([fc.apparent_max_c, fc.apparent_min_c])


def _feels(fc: DailyForecast | None) -> float | None:
    if fc is None:
        return None
    t = _mean([fc.apparent_max_c, fc.apparent_min_c])
    return t if t is not None else _mean([fc.temp_max_c, fc.temp_min_c])


def parse_hour(s) -> int | None:
    """'19:00' / '19' / '7pm' / '晚上7點' -> 19."""
    if s is None:
        return None
    t = str(s).strip().lower()
    m = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$", t)
    if m:
        h = int(m.group(1))
        if m.group(3) == "pm" and h < 12:
            h += 12
        if m.group(3) == "am" and h == 12:
            h = 0
        return h if 0 <= h <= 23 else None
    m = re.search(r"(\d{1,2})\s*[點点時]", t)
    if m:
        h = int(m.group(1))
        if any(w in t for w in ("晚上", "下午", "傍晚")) and h < 12:
            h += 12
        return h if 0 <= h <= 23 else None
    return None


def hour_zh(h: int) -> str:
    """19 -> '晚上 7 點', 12 -> '中午 12 點', 0 -> '凌晨 12 點'."""
    part = ("凌晨" if h < 5 else "早上" if h < 9 else "上午" if h < 12 else "中午" if h == 12
            else "下午" if h < 18 else "晚上")
    hh = h % 12 or 12
    return f"{part} {hh} 點"


def _sig(label: str, prefs=None, design=None, detail=None, ranking: bool = True) -> ContextSignal:
    return ContextSignal(source="travel", label=label, prefs=prefs or [], design_steps=design or {},
                         affects_ranking=ranking, opt_in=False, evidence=EVIDENCE, detail=detail or {})


def _resolve_place(lat, lon, name, geocode_fn) -> tuple[float | None, float | None, dict | None]:
    g = None
    if (lat is None or lon is None) and name:
        g = geocode_fn(name)
        if g:
            lat, lon = g.get("lat"), g.get("lon")
    return lat, lon, g


# ---------------------------------------------------------------------------
# signals
# ---------------------------------------------------------------------------

def signals(ctx, today, forecast: DailyForecast | None = None, *, geocode_fn=None, day_fn=None,
            hourly_fn=None) -> list[ContextSignal]:
    """Travel ContextSignals (empty when there is no origin, no transport and no event_time)."""
    geocode_fn = geocode_fn or geo.geocode
    day_fn = day_fn or day_weather
    hourly_fn = hourly_fn or fetch_hourly
    g = lambda k: getattr(ctx, k, None)                                     # noqa: E731
    has_origin = bool(g("origin_city")) or (g("origin_lat") is not None and g("origin_lon") is not None)
    if not (has_origin or g("transport") or g("event_time")):
        return []
    today_d = _as_date(today or date.today())
    day = str(g("event_date") or today_d.isoformat())[:10]

    d_name = g("city") or "目的地"
    d_lat, d_lon, d_geo = _resolve_place(g("lat"), g("lon"), g("city"), geocode_fn)
    o_name = g("origin_city") or "出發地"
    o_lat, o_lon, o_geo = (_resolve_place(g("origin_lat"), g("origin_lon"), g("origin_city"), geocode_fn)
                           if has_origin else (None, None, None))
    d_known = d_lat is not None and d_lon is not None
    o_known = o_lat is not None and o_lon is not None

    out: list[ContextSignal] = []

    # destination / origin weather for the event date
    fc_d = forecast if forecast is not None else (day_fn(d_lat, d_lon, day, g("city") or "", today_d)
                                                  if d_known else None)
    fc_o = day_fn(o_lat, o_lon, day, g("origin_city") or "", today_d) if o_known else None

    # ---- route + transport
    km = None
    mode = g("transport")
    inferred = False
    if d_known and o_known:
        km = geo.haversine_km(o_lat, o_lon, d_lat, d_lon)
        if not mode:
            if d_geo is None and g("city"):
                d_geo = geocode_fn(g("city"))
            if o_geo is None and g("origin_city"):
                o_geo = geocode_fn(g("origin_city"))
            cc = lambda x: (x or {}).get("country_code") or (x or {}).get("country")  # noqa: E731
            mode = geo.infer_transport(km, cc(o_geo), cc(d_geo))
            inferred = True
    mode_zh = {"flight": "飛行", "hsr": "高鐵", "train": "火車", "car": "開車", "scooter": "騎車",
               "mrt": "捷運", "walk": "走路", "bike": "騎單車"}
    hours = None
    if km is not None:
        if mode == "flight":
            hours = geo.flight_hours(km)
        elif mode == "hsr":
            hours = km / 250.0 + 0.3
        elif mode in ("train", "car"):
            hours = km / 80.0
        trip = f"{mode_zh.get(mode, mode)}約 {hours:.1f} 小時" if hours else mode_zh.get(mode, mode)
        out.append(_sig(f"{o_name} → {d_name} 約 {km:,.0f} km・{trip}", ranking=False,
                        detail={"km": round(km, 1), "transport": mode, "transport_inferred": inferred,
                                "travel_hours": round(hours, 2) if hours else None,
                                "origin": {"name": o_name, "lat": o_lat, "lon": o_lon},
                                "destination": {"name": d_name, "lat": d_lat, "lon": d_lon}}))

    # ---- transport comfort
    tdetail = {"transport": mode, "transport_inferred": inferred, "km": km, "travel_hours": hours}
    if mode == "flight":
        if hours is None or hours > 3:
            h_txt = f"約 {hours:.0f} 小時" if hours else ""
            out.append(_sig(f"長途飛行{h_txt}：舒服、不易皺 → 軟針織、寬鬆版型，下機直接開逛",
                            [AttributePref("occasion", 0.15, "旅行好穿", values=["Travel", "Casual"]),
                             AttributePref("style", 0.1, "舒適好活動", values=["minimalist", "sporty"])],
                            design={"relaxed_fit": 1.0, "soft_knit": 1.0, "crisp_collar": -1.0},
                            detail=tdetail))
        else:
            out.append(_sig("短程飛行：好穿脫的外層，過安檢、機上冷氣都搞定",
                            [AttributePref("category", 0.1, "好穿脫外層", values=["outerwear"])],
                            design={"relaxed_fit": 0.5}, detail=tdetail))
    elif mode in ("hsr", "train"):
        ride = "高鐵" if mode == "hsr" else "火車"
        h_txt = f" {hours:.1f} 小時" if hours else ""
        out.append(_sig(f"搭{ride}{h_txt}：smart casual，下車直接見人也不失禮",
                        [AttributePref("occasion", 0.15, "有型又好坐", values=["Smart Casual"])],
                        design={"minimal_design": 1.0, "crisp_collar": 0.5}, detail=tdetail))
    elif mode == "scooter" and not g("commute"):
        rain = (fc_d.precip_prob_pct or 0.0) if fc_d is not None else 0.0
        wet = rain >= 50
        out.append(_sig("騎車移動：擋風防潑水，長洋裝、飄逸寬版先收起來"
                        + (f"（降雨 {rain:.0f}%）" if wet else ""),
                        [AttributePref("water_repellent", 0.3 if wet else 0.15, "機車族防潑水", values=[True]),
                         AttributePref("category", 0.15, "擋風外套", values=["outerwear"]),
                         AttributePref("category", -0.15, "長洋裝會捲進輪子", values=["dress"])],
                        design={"relaxed_fit": -1.0, "tailored_fit": 1.0}, detail=tdetail))
    elif mode == "mrt" and not g("commute"):
        out.append(_sig("搭捷運：車廂冷氣強、月台悶 → 帶件薄外套隨時穿脫",
                        [AttributePref("category", 0.1, "隨身薄外套", values=["outerwear"])],
                        design={"soft_knit": 0.5}, detail=tdetail))

    # ---- climate gap origin -> destination
    t_o, t_d = _rep_temp(fc_o), _rep_temp(fc_d)
    if t_o is not None and t_d is not None and abs(t_d - t_o) >= GAP_MIN_C:
        gap = t_d - t_o
        normal = NORMAL_SOURCE in ((fc_o.source or ""), (fc_d.source or ""))
        tgt = weather.warmth_target(_feels(fc_d))
        head = f"{o_name} {t_o:.0f}°C → {d_name} {t_d:.0f}°C：落差 {abs(gap):.0f}°C"
        tail = "（往年平均）" if normal else ""
        if gap < 0:
            label = f"{head}，洋蔥式穿搭＋一件可脫的外套{tail}"
            prefs = [AttributePref("warmth", 0.2, f"{d_name}約 {t_d:.0f}°C", target=float(tgt)),
                     AttributePref("category", _cap(0.15 + 0.01 * min(abs(gap), 10)),
                                   "可穿脫的外套", values=["outerwear"])]
            design = {"soft_knit": 1.0}
        else:
            label = f"{head}，外套穿到機場就好，行李箱裝輕薄透氣{tail}"
            prefs = [AttributePref("warmth", 0.2, f"{d_name}約 {t_d:.0f}°C", target=float(tgt)),
                     AttributePref("season", 0.1, "夏季款", values=["Summer", "Spring"])]
            design = {"soft_knit": -1.0}
        out.append(_sig(label, prefs, design=design,
                        detail={"origin_c": t_o, "destination_c": t_d, "gap_c": gap,
                                "warmth_target": tgt, "climate_normal": normal}))

    # ---- beyond the forecast horizon: climate normals at the destination
    if fc_d is not None and fc_d.source == NORMAL_SOURCE:
        feels = _feels(fc_d)
        tgt = weather.warmth_target(feels) if feels is not None else None
        m = _as_date(day).month
        lo, hi = fc_d.temp_min_c, fc_d.temp_max_c
        rng = f"{lo:.0f}～{hi:.0f}°C" if lo is not None and hi is not None else f"{feels:.0f}°C"
        label = f"{m} 月{d_name}往年平均 {rng}（歷史平均，非預報）"
        prefs = []
        design = {}
        if tgt is not None:
            label += f" → {weather.WARMTH_WORDS[tgt]}"
            prefs.append(AttributePref("warmth", 0.3, f"往年同期體感約 {feels:.0f}°C", target=float(tgt)))
            if tgt >= 2:
                design["soft_knit"] = 1.0
        rain_share = fc_d.precip_prob_pct or 0.0
        if rain_share >= 40:
            label += f"；往年 {rain_share:.0f}% 的日子會下雨"
            prefs.append(AttributePref("water_repellent", 0.15, "往年常下雨", values=[True]))
        if prefs:
            out.append(_sig(label, prefs, design=design,
                            detail={**{k: v for k, v in fc_d.__dict__.items() if k != "fetched_at"},
                                    "warmth_target": tgt, "horizon_days": FORECAST_HORIZON_DAYS}))

    # ---- event_time: the hour the outfit is actually worn
    h = parse_hour(g("event_time"))
    if h is not None and d_known:
        hr = hourly_fn(d_lat, d_lon, day, g("city") or "", today_d)
        hours_map = (hr or {}).get("hours") or {}
        at = hours_map.get(h) or hours_map.get(str(h))
        if at:
            f_at = at.get("feels_c") if at.get("feels_c") is not None else at.get("temp_c")
            day_vals = [(hours_map.get(k) or hours_map.get(str(k)) or {}) for k in range(10, 17)]
            day_vals = [v.get("feels_c") if v.get("feels_c") is not None else v.get("temp_c")
                        for v in day_vals]
            day_vals = [v for v in day_vals if v is not None]
            peak = max(day_vals) if day_vals else None
            if f_at is not None:
                normal = (hr or {}).get("source") == NORMAL_SOURCE
                tgt = weather.warmth_target(f_at)
                drop = (peak - f_at) if peak is not None else 0.0
                pre = "往年同期" if normal else ""
                approx = "約 " if normal else " "
                if drop >= EVENING_DROP_C:
                    advice = "帶件保暖外套" if tgt >= 3 else "帶件外套"
                    label = (f"{pre}{hour_zh(h)}體感{approx}{f_at:.0f}°C，比白天冷 {drop:.0f}°C → {advice}")
                else:
                    label = f"{pre}{hour_zh(h)}體感{approx}{f_at:.0f}°C → {weather.WARMTH_WORDS[tgt]}"
                prefs = [AttributePref("warmth", 0.2, f"{hour_zh(h)}體感 {f_at:.0f}°C", target=float(tgt))]
                if drop >= EVENING_DROP_C or tgt >= 2:
                    prefs.append(AttributePref("category", 0.2, "入夜加一層", values=["outerwear"]))
                pop = at.get("precip_prob_pct")
                if pop is not None and pop >= 50:
                    label += f"；那時段降雨 {pop:.0f}%，外層選防潑水"
                    prefs.append(AttributePref("water_repellent", 0.2, "活動時段可能下雨", values=[True]))
                out.append(_sig(label, prefs, design={"soft_knit": 1.0} if tgt >= 2 else {},
                                detail={"hour": h, "feels_c": f_at, "daytime_peak_c": peak,
                                        "drop_c": drop, "precip_prob_pct": pop,
                                        "hourly_source": (hr or {}).get("source")}))
    return out
