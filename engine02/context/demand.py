"""情境需求雷達 (context demand radar) -- a back-office panel for the manufacturer (聚陽 Makalot).

The consumer-side context modules turn weather and festivals into *ranking* preferences for one
shopper. This module turns the same inputs into what a factory can act on: for the next N days,
which catalog attribute values (warmth level, water-repellent, colour family, occasion, boldness)
should see demand move, how hard, why, and -- if a catalog is given -- whether the catalog even
carries enough of them.

=============================== ==============================================================
input                           demand shift it produces (all intuition v0, not yet measured)
=============================== ==============================================================
cold days (體感低溫 < 14 / 18°C)   warmth 3 / warmth 2 ↑ ; warmth 0 ↓
hot days (體感高溫 >= 30°C)        warmth 0 ↑ ; warmth 3 ↓
rain days (降雨機率 >= 60% or >= 5mm) water_repellent True ↑
windy days (>= 40 km/h)          category outerwear ↑
festival keywords               colour families / occasion / boldness (春節 → 紅/金, 萬聖節 → 黑/橘,
                                情人節 → 粉/紅, 尾牙 → Formal + boldness ↑, 聖誕 → 紅/綠 ...)
=============================== ==============================================================

Lead-time notes are a manufacturer-oriented heuristic (啟發式，尚未驗證): fabric sourcing takes
weeks, cut-and-sew takes weeks, so a signal is only actionable as *production* if it is seen far
enough ahead; closer than that it is an allocation / merchandising / marketing signal.

Nothing here touches ranking. Pure Python + pandas; no network, festivals are injected.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Callable

from .base import DailyForecast

EVIDENCE = "intuition v0 (not yet measured)"
LEAD_TIME_LABEL = "啟發式，尚未驗證"

# thresholds (intuition v0)
COLD_HARD_C = 14.0       # 體感 < 14°C → 保暖 3 級
COLD_SOFT_C = 18.0       # 體感 < 18°C → 保暖 2 級
HOT_C = 30.0             # 體感高溫 >= 30°C → 最輕薄
RAIN_PROB_PCT = 60.0
RAIN_MM = 5.0
WIND_KMH = 40.0

# manufacturer lead times in days (heuristic, not measured against Makalot's real calendar)
LEAD_FABRIC_DAYS = 45    # 面料備料 + 染整
LEAD_CMT_DAYS = 21       # 裁縫快反 (cut-make-trim on existing fabric)
LEAD_ALLOC_DAYS = 3      # 調撥現貨 / 上架排序

WARMTH_ZH = {0: "輕薄 0 級", 1: "保暖 1 級", 2: "保暖 2 級", 3: "保暖 3 級"}
ATTR_ZH = {"warmth": "保暖度", "water_repellent": "防潑水", "color": "色系", "occasion": "場合",
           "boldness": "大膽度", "category": "品類"}
COLOR_ZH_NAME = {"Red": "紅", "Gold": "金", "Black": "黑", "Orange": "橘", "Pink": "粉",
                 "Green": "綠", "White": "白", "Silver": "銀", "Purple": "紫", "Yellow": "黃",
                 "Brown": "棕", "Beige": "米", "Blue": "藍", "Grey": "灰"}
# colour value -> the catalog values that count as "that colour" when measuring supply
COLOR_MATCH: dict[str, tuple[str, ...]] = {
    "Red": ("red", "maroon", "burgundy", "rust"),
    "Gold": ("gold", "mustard", "yellow"),
    "Black": ("black",),
    "Orange": ("orange", "rust"),
    "Pink": ("pink", "magenta", "rose", "peach", "mauve"),
    "Green": ("green", "olive", "sea green", "lime green"),
    "White": ("white", "off white", "cream"),
    "Silver": ("silver", "metallic", "steel", "grey"),
    "Purple": ("purple", "lavender"),
    "Brown": ("brown", "coffee brown", "tan", "taupe", "bronze", "copper"),
}

# festival keyword -> list of (attribute, value, direction, base strength)
FESTIVAL_RULES: list[tuple[tuple[str, ...], list[tuple[str, Any, str, float]]]] = [
    (("春節", "農曆新年", "除夕", "過年", "新年"),
     [("color", "Red", "up", 0.8), ("color", "Gold", "up", 0.6), ("occasion", "Formal", "up", 0.3)]),
    (("萬聖", "halloween"),
     [("color", "Black", "up", 0.6), ("color", "Orange", "up", 0.6), ("boldness", "high", "up", 0.5)]),
    (("情人", "七夕", "valentine"),
     [("color", "Pink", "up", 0.6), ("color", "Red", "up", 0.5), ("occasion", "Smart Casual", "up", 0.3)]),
    (("尾牙", "春酒"),
     [("occasion", "Formal", "up", 0.7), ("boldness", "high", "up", 0.4), ("color", "Red", "up", 0.3)]),
    (("聖誕", "christmas"),
     [("color", "Red", "up", 0.6), ("color", "Green", "up", 0.4), ("color", "White", "up", 0.3)]),
    (("跨年",),
     [("boldness", "high", "up", 0.6), ("color", "Black", "up", 0.4), ("color", "Silver", "up", 0.4)]),
    (("母親節",), [("color", "Pink", "up", 0.4), ("occasion", "Smart Casual", "up", 0.3)]),
    (("中秋", "烤肉"), [("occasion", "Casual", "up", 0.4), ("color", "Orange", "up", 0.2)]),
    (("端午",), [("warmth", 0, "up", 0.3)]),
    (("清明", "掃墓"), [("color", "Black", "up", 0.3), ("color", "White", "up", 0.3),
                        ("boldness", "high", "down", 0.3)]),
    (("畢業", "謝師宴"), [("occasion", "Formal", "up", 0.5)]),
    (("婚禮", "wedding"), [("occasion", "Formal", "up", 0.5), ("color", "White", "down", 0.3)]),
]
# by `kind` when no keyword matched
KIND_RULES: dict[str, list[tuple[str, Any, str, float]]] = {
    "party": [("boldness", "high", "up", 0.4)],
    "formal": [("occasion", "Formal", "up", 0.4)],
    "romantic": [("color", "Pink", "up", 0.4)],
    "outdoor": [("occasion", "Casual", "up", 0.3)],
}


# ---------------------------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------------------------
def _d(s: Any) -> date | None:
    if s is None:
        return None
    if isinstance(s, date):
        return s
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def _feels_min(f: DailyForecast) -> float | None:
    return f.apparent_min_c if f.apparent_min_c is not None else f.temp_min_c


def _feels_max(f: DailyForecast) -> float | None:
    return f.apparent_max_c if f.apparent_max_c is not None else f.temp_max_c


def _is_rain(f: DailyForecast) -> bool:
    return ((f.precip_prob_pct is not None and f.precip_prob_pct >= RAIN_PROB_PCT)
            or (f.precip_mm is not None and f.precip_mm >= RAIN_MM))


def _value_zh(attr: str, value: Any) -> str:
    if attr == "warmth":
        return WARMTH_ZH.get(int(value), f"保暖 {value} 級")
    if attr == "water_repellent":
        return "防潑水" if value else "非防潑水"
    if attr == "color":
        return COLOR_ZH_NAME.get(value, str(value)) + "色"
    if attr == "boldness":
        return "大膽款 (≥2)" if value == "high" else f"大膽度 {value}"
    if attr == "occasion":
        return {"Formal": "正式場合", "Casual": "休閒", "Smart Casual": "小正式"}.get(value, value)
    if attr == "category":
        return {"outerwear": "外套"}.get(value, value)
    return str(value)


def lead_time_note(days_ahead: int) -> str:
    """Which lever a signal `days_ahead` away can still pull (啟發式，尚未驗證)."""
    if days_ahead >= LEAD_FABRIC_DAYS:
        lever = f"提前 {days_ahead} 天：可排面料備料＋生產（面料約需 {LEAD_FABRIC_DAYS} 天）"
    elif days_ahead >= LEAD_CMT_DAYS:
        lever = f"提前 {days_ahead} 天：面料來不及，可用現有布料快反裁縫（約 {LEAD_CMT_DAYS} 天）"
    elif days_ahead >= LEAD_ALLOC_DAYS:
        lever = f"提前 {days_ahead} 天：來不及生產，只能調撥現貨、調整上架與行銷"
    else:
        lever = f"僅剩 {max(days_ahead, 0)} 天：只能靠推薦排序與門市陳列"
    return f"{lever}（{LEAD_TIME_LABEL}）"


@dataclass
class _Acc:
    attribute: str
    value: Any
    score: float = 0.0                       # signed, accumulated
    drivers_zh: list[str] = field(default_factory=list)
    first_day: int | None = None             # days from window start to first driver
    days: int = 0                            # driving days (weather) for the supply message
    day_label: str = ""

    def add(self, signed: float, driver: str, day_offset: int, days: int = 0, day_label: str = ""):
        self.score += signed
        if driver not in self.drivers_zh:
            self.drivers_zh.append(driver)
        self.first_day = day_offset if self.first_day is None else min(self.first_day, day_offset)
        if days > self.days:
            self.days, self.day_label = days, day_label


# ---------------------------------------------------------------------------------------------
# main entry
# ---------------------------------------------------------------------------------------------
def demand_outlook(forecasts: list[DailyForecast], festivals: list[dict], items=None,
                   horizon_days: int = 14, *, today: str | date | None = None,
                   prep_lookahead_days: int = 90) -> dict:
    """Next `horizon_days` of weather + festivals → demand shifts on catalog attributes.

    `items` is an optional pandas DataFrame with any of the base.py catalog columns; when given,
    each upward shift is compared against the catalog's share of that value (`supply_gap`).
    `today` pins the window start (default: earliest forecast date, else date.today()).
    Festivals beyond the window but within `prep_lookahead_days` go to `prep_calendar`: the
    manufacturer's "start sourcing now" list.
    """
    forecasts = list(forecasts or [])
    festivals = list(festivals or [])
    start = _d(today)
    if start is None:
        fdates = [d for d in (_d(f.date) for f in forecasts) if d is not None]
        start = min(fdates) if fdates else date.today()
    end = start + timedelta(days=horizon_days - 1)

    acc: dict[tuple[str, Any], _Acc] = {}

    def push(attr, value, signed, driver, offset, days=0, day_label=""):
        a = acc.setdefault((attr, value), _Acc(attr, value))
        a.add(signed, driver, offset, days, day_label)

    # ---- weather --------------------------------------------------------------------------
    in_win = [(f, (_d(f.date) - start).days) for f in forecasts
              if _d(f.date) is not None and start <= _d(f.date) <= end]
    n_days = len(in_win)
    if n_days:
        cold_hard = [(f, o) for f, o in in_win if (_feels_min(f) is not None and _feels_min(f) < COLD_HARD_C)]
        cold_soft = [(f, o) for f, o in in_win
                     if _feels_min(f) is not None and COLD_HARD_C <= _feels_min(f) < COLD_SOFT_C]
        hot = [(f, o) for f, o in in_win if _feels_max(f) is not None and _feels_max(f) >= HOT_C]
        rain = [(f, o) for f, o in in_win if _is_rain(f)]
        windy = [(f, o) for f, o in in_win if f.wind_max_kmh is not None and f.wind_max_kmh >= WIND_KMH]

        if cold_hard:
            k = len(cold_hard)
            lo = min(_feels_min(f) for f, _ in cold_hard)
            first = min(o for _, o in cold_hard)
            label = "寒流週" if k >= 3 else "冷空氣"
            drv = f"{label}：{k}/{n_days} 天體感 < {COLD_HARD_C:.0f}°C（最低 {lo:.0f}°C）"
            push("warmth", 3, min(1.0, 0.3 + 0.7 * k / n_days), drv, first, k,
                 f"{k} 天體感 < {COLD_HARD_C:.0f}°C")
            push("warmth", 2, 0.3 * k / n_days, drv, first)
            push("warmth", 0, -min(1.0, 0.2 + 0.6 * k / n_days), drv, first)
        if cold_soft:
            k = len(cold_soft)
            first = min(o for _, o in cold_soft)
            drv = f"轉涼：{k}/{n_days} 天體感 {COLD_HARD_C:.0f}–{COLD_SOFT_C:.0f}°C"
            push("warmth", 2, min(1.0, 0.2 + 0.6 * k / n_days), drv, first, k,
                 f"{k} 天體感 < {COLD_SOFT_C:.0f}°C")
        if hot:
            k = len(hot)
            hi = max(_feels_max(f) for f, _ in hot)
            first = min(o for _, o in hot)
            drv = f"炎熱：{k}/{n_days} 天體感 ≥ {HOT_C:.0f}°C（最高 {hi:.0f}°C）"
            push("warmth", 0, min(1.0, 0.2 + 0.7 * k / n_days), drv, first, k,
                 f"{k} 天體感 ≥ {HOT_C:.0f}°C")
            push("warmth", 3, -min(1.0, 0.2 + 0.7 * k / n_days), drv, first)
        if rain:
            k = len(rain)
            first = min(o for _, o in rain)
            drv = f"雨天：{k}/{n_days} 天降雨機率 ≥ {RAIN_PROB_PCT:.0f}% 或雨量 ≥ {RAIN_MM:.0f}mm"
            push("water_repellent", True, min(1.0, 0.2 + 0.8 * k / n_days), drv, first, k, f"{k} 天下雨")
        if windy:
            k = len(windy)
            first = min(o for _, o in windy)
            drv = f"強風：{k}/{n_days} 天陣風 ≥ {WIND_KMH:.0f} km/h"
            push("category", "outerwear", min(1.0, 0.1 + 0.5 * k / n_days), drv, first, k, f"{k} 天強風")

    # ---- festivals ------------------------------------------------------------------------
    in_window_names: list[str] = []
    prep_calendar: list[dict] = []
    for fest in festivals:
        name = str(fest.get("name_zh") or fest.get("name") or fest.get("name_en") or "")
        f_start = _d(fest.get("date") or fest.get("start"))
        f_end = _d(fest.get("end")) or f_start
        if f_start is None:
            continue
        rules = _festival_rules(name, fest.get("name_en"), fest.get("kind"))
        if not rules:
            continue
        if f_end >= start and f_start <= end:                     # overlaps the window
            in_window_names.append(name)
            offset = max((f_start - start).days, 0)
            for attr, value, direction, s in rules:
                push(attr, value, s if direction == "up" else -s, f"{name}（{f_start.isoformat()}）", offset)
        elif end < f_start <= start + timedelta(days=prep_lookahead_days):
            ahead = (f_start - start).days
            prep_calendar.append({
                "festival": name, "date": f_start.isoformat(), "days_ahead": ahead,
                "attributes": [{"attribute": a, "value": v, "direction": d} for a, v, d, _ in rules],
                "lead_time_note_zh": lead_time_note(ahead),
            })
    prep_calendar.sort(key=lambda p: p["days_ahead"])

    # ---- assemble shifts ------------------------------------------------------------------
    shifts = []
    for a in acc.values():
        if abs(a.score) < 0.05:
            continue
        first = a.first_day or 0
        shifts.append({
            "attribute": a.attribute,
            "value": a.value,
            "value_zh": _value_zh(a.attribute, a.value),
            "direction": "up" if a.score > 0 else "down",
            "strength": round(min(1.0, abs(a.score)), 3),
            "drivers_zh": a.drivers_zh,
            "starts_in_days": first,
            "lead_time_note_zh": lead_time_note(first),
            "evidence": EVIDENCE,
            "_days": a.days, "_day_label": a.day_label,
        })
    shifts.sort(key=lambda s: (-s["strength"], s["attribute"], str(s["value"])))

    supply_gap = _supply_gap(shifts, items, horizon_days) if items is not None else []
    for s in shifts:
        s.pop("_days"), s.pop("_day_label")

    return {
        "window": {"start": start.isoformat(), "end": end.isoformat(), "horizon_days": horizon_days,
                   "forecast_days": n_days, "festivals_in_window": in_window_names},
        "shifts": shifts,
        "supply_gap": supply_gap,
        "prep_calendar": prep_calendar,
        "headline_zh": _headline(shifts, supply_gap, horizon_days),
        "evidence": EVIDENCE,
        "lead_time_basis_zh": (f"面料 {LEAD_FABRIC_DAYS} 天／快反 {LEAD_CMT_DAYS} 天／調撥 "
                               f"{LEAD_ALLOC_DAYS} 天（{LEAD_TIME_LABEL}）"),
    }


def _festival_rules(name: str, name_en: Any, kind: Any) -> list[tuple[str, Any, str, float]]:
    hay = f"{name} {name_en or ''}".lower()
    out: list[tuple[str, Any, str, float]] = []
    seen = set()
    for keys, rules in FESTIVAL_RULES:
        if any(k.lower() in hay for k in keys):
            for r in rules:
                if (r[0], r[1]) not in seen:
                    seen.add((r[0], r[1]))
                    out.append(r)
    if not out and kind:
        out = list(KIND_RULES.get(str(kind).lower(), []))
    return out


# ---------------------------------------------------------------------------------------------
# supply gap
# ---------------------------------------------------------------------------------------------
def _matcher(attr: str, value: Any) -> Callable[[Any], bool]:
    if attr == "warmth":
        return lambda x: x is not None and x == x and int(x) == int(value)
    if attr == "water_repellent":
        return lambda x: bool(x) == bool(value) if x is not None and x == x else False
    if attr == "boldness":
        return lambda x: x is not None and x == x and float(x) >= 2
    if attr == "color":
        names = COLOR_MATCH.get(value, (str(value).lower(),))
        return lambda x: isinstance(x, str) and x.strip().lower() in names
    return lambda x: isinstance(x, str) and x.strip().lower() == str(value).lower()


def _supply_gap(shifts: list[dict], items, horizon_days: int) -> list[dict]:
    try:
        n = len(items)
        cols = set(items.columns)
    except Exception:
        return []
    if n == 0:
        return []
    out = []
    for s in shifts:
        if s["direction"] != "up" or s["attribute"] not in cols:
            continue
        match = _matcher(s["attribute"], s["value"])
        k = int(sum(1 for x in items[s["attribute"]].tolist() if match(x)))
        share = k / n
        # demand-side target share: intuition v0 -- a full-strength shift "wants" ~35% of the range
        target = round(0.35 * s["strength"], 3)
        gap = round(target - share, 3)
        why = s["_day_label"] and f"未來 {horizon_days} 天有 {s['_day_label']}" or "、".join(s["drivers_zh"][:2])
        out.append({
            "attribute": s["attribute"], "value": s["value"], "value_zh": s["value_zh"],
            "catalog_share": round(share, 3), "catalog_count": k, "catalog_total": n,
            "target_share": target, "gap": gap, "under_supplied": gap > 0,
            "message_zh": (f"{s['value_zh']}只佔商品 {share:.0%}，但{why}"
                           + ("（供給不足）" if gap > 0 else "（供給足夠）")),
            "evidence": EVIDENCE,
        })
    out.sort(key=lambda g: -g["gap"])
    return out


def _headline(shifts: list[dict], gaps: list[dict], horizon_days: int) -> str:
    ups = [s for s in shifts if s["direction"] == "up"]
    if not ups:
        return f"未來 {horizon_days} 天沒有明顯的情境需求訊號，照常排產。"
    parts = []
    for s in ups[:2]:
        cause = s["drivers_zh"][0].split("：")[0].split("（")[0]
        parts.append(f"{cause} → {s['value_zh']}需求 ↑")
    line = f"未來 {horizon_days} 天：" + "；".join(parts)
    worst = next((g for g in gaps if g["under_supplied"]), None)
    if worst:
        line += f"。缺口：{worst['value_zh']}只佔商品 {worst['catalog_share']:.0%}"
    return line + "。"
