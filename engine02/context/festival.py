"""Festival / season context: "what is coming up in Taiwan around the date this outfit is for".

Reads engine02/resources/tw_festivals.json (lunar dates verified against the Hong Kong Observatory
Gregorian-Lunar conversion tables). An occasion is *active* for date d when

    start - window_days_before  <=  d  <=  end

Each active occasion becomes one ContextSignal whose preferences come from a small, intuitive,
hand-written style rule (evidence = "intuition v0 (not yet measured)"). The weight ramps up as the
day approaches: 60% of the base weight when the window opens, 100% from the day itself onwards, so
"中秋還有 10 天" nudges less than "明天就中秋".

Commercial occasions with no style meaning (雙11, 黑五) produce a display-only label.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path

from .base import MAX_SIGNAL_WEIGHT, AttributePref, ContextSignal

FESTIVALS_PATH = Path(__file__).resolve().parent.parent / "resources" / "tw_festivals.json"
EVIDENCE = "intuition v0 (not yet measured)"
MAX_ACTIVE = 3                  # at most this many festival signals at once (nearest first)
RAMP_FLOOR = 0.6                # share of the base weight when the window just opened


@dataclass(frozen=True)
class Occasion:
    key: str
    name_zh: str
    name_en: str
    start: date
    end: date
    window_days_before: int
    kind: str
    source_url: str

    def window_start(self) -> date:
        return date.fromordinal(self.start.toordinal() - self.window_days_before)

    def covers(self, d: date) -> bool:
        return self.window_start() <= d <= self.end

    def days_until(self, d: date) -> int:
        """Days from d to the start; 0 while the occasion is under way."""
        return max(0, (self.start - d).days)


def _to_date(v) -> date:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


@lru_cache(maxsize=1)
def load_occasions() -> tuple[Occasion, ...]:
    raw = json.loads(FESTIVALS_PATH.read_text(encoding="utf-8"))
    out = []
    for o in raw["occasions"]:
        start = _to_date(o.get("start") or o["date"])
        end = _to_date(o.get("end") or o.get("date") or o["start"])
        out.append(Occasion(o["key"], o["name_zh"], o["name_en"], start, end,
                            int(o.get("window_days_before", 7)), o.get("kind", "festival"),
                            o.get("source_url", "")))
    return tuple(sorted(out, key=lambda x: (x.start, x.key)))


def active_occasions(d, occasions=None) -> list[Occasion]:
    """Occasions whose influence window covers d, nearest first."""
    d = _to_date(d)
    occ = load_occasions() if occasions is None else occasions
    hits = [o for o in occ if o.covers(d)]
    return sorted(hits, key=lambda o: (o.days_until(d), o.kind == "commercial", o.key))


# ---------------------------------------------------------------------------
# Style rules: key -> (label, [(column, base_weight, values | None, target | None), ...])
# Colours are catalog vocabulary (attribute_fill.COLOR_FAMILIES). Base weights <= 0.5.
# Empty pref list = label only, affects_ranking False.
# ---------------------------------------------------------------------------

_V = "values"
_T = "target"

RULES: dict[str, tuple[str, list[tuple]]] = {
    "mid_autumn": ("中秋烤肉不怕髒：深色、好活動的休閒穿搭", [
        ("occasion", 0.30, _V, ["Casual"]),
        ("color", 0.25, _V, ["Black", "Navy Blue", "Charcoal", "Olive", "Coffee Brown", "Maroon"]),
        ("boldness", 0.10, _T, 1.0),
    ]),
    "national_day": ("雙十連假出遊：紅白藍輕鬆走", [
        ("occasion", 0.20, _V, ["Casual", "Travel"]),
        ("color", 0.20, _V, ["Red", "White", "Navy Blue", "Blue"]),
    ]),
    "halloween": ("萬聖節不怕浮誇：大膽、暗黑、有戲", [
        ("boldness", 0.40, _T, 3.0),
        ("style", 0.35, _V, ["avant_garde", "edgy"]),
        ("color", 0.20, _V, ["Black", "Orange", "Purple", "Burgundy"]),
    ]),
    "double11": ("雙11 大促：可以放心衝預算", []),
    "black_friday": ("黑五折扣季：趁機把基本款補齊", []),
    "christmas": ("聖誕交換禮物趴：紅綠金上身", [
        ("color", 0.35, _V, ["Red", "Green", "Gold", "White", "Burgundy"]),
        ("occasion", 0.20, _V, ["Smart Casual"]),
        ("boldness", 0.20, _T, 2.0),
        ("warmth", 0.15, _T, 2.0),
    ]),
    "new_year_eve": ("跨年倒數：保暖第一，還要夠閃", [
        ("warmth", 0.30, _T, 2.5),
        ("boldness", 0.30, _T, 2.5),
        ("color", 0.25, _V, ["Silver", "Metallic", "Gold", "Black"]),
    ]),
    "weiya": ("尾牙要上台抽獎：正式一點、帶點亮點", [
        ("occasion", 0.35, _V, ["Formal", "Smart Casual"]),
        ("boldness", 0.20, _T, 2.0),
        ("color", 0.20, _V, ["Gold", "Silver", "Metallic", "Red", "Burgundy"]),
    ]),
    "lunar_new_year": ("過年穿紅，新年新氣象：紅金新衣大膽一點", [
        ("color", 0.45, _V, ["Red", "Maroon", "Burgundy", "Gold"]),
        ("boldness", 0.20, _T, 2.0),          # "new outfit" = one step bolder than a basic day
        ("occasion", 0.15, _V, ["Smart Casual", "Ethnic"]),
    ]),
    "valentine": ("情人節約會：浪漫粉紅上場", [
        ("style", 0.35, _V, ["romantic"]),
        ("occasion", 0.25, _V, ["Smart Casual"]),
        ("color", 0.30, _V, ["Pink", "Rose", "Red", "Burgundy"]),
    ]),
    "lantern": ("元宵夜逛燈會：暖色系、保暖又好走", [
        ("color", 0.20, _V, ["Red", "Gold", "Orange", "Yellow"]),
        ("occasion", 0.20, _V, ["Casual"]),
        ("warmth", 0.15, _T, 2.0),
    ]),
    "peace_memorial": ("228 連假小旅行：輕便好走的旅行穿搭", [
        ("occasion", 0.25, _V, ["Travel", "Casual"]),
    ]),
    "qingming": ("清明連假：返鄉掃墓素色好走，出遊再帶點亮色", [
        ("occasion", 0.30, _V, ["Casual", "Travel"]),
        ("boldness", 0.15, _T, 1.0),
    ]),
    "mothers_day": ("母親節帶媽媽吃大餐：得體又溫柔", [
        ("occasion", 0.25, _V, ["Smart Casual"]),
        ("style", 0.20, _V, ["classic", "romantic"]),
        ("color", 0.15, _V, ["Pink", "Peach", "Cream", "White"]),
    ]),
    "520": ("520 我愛你：告白就穿粉色系", [
        ("style", 0.25, _V, ["romantic"]),
        ("color", 0.20, _V, ["Pink", "Rose", "Red"]),
    ]),
    "dragon_boat": ("端午看龍舟：輕薄透氣、不怕水花", [
        ("warmth", 0.30, _T, 0.0),
        ("occasion", 0.20, _V, ["Casual", "Sports"]),
        ("water_repellent", 0.15, _V, [True]),
    ]),
    "graduation": ("畢業典禮拍照：經典正式不出錯", [
        ("style", 0.30, _V, ["classic"]),
        ("occasion", 0.30, _V, ["Formal", "Smart Casual"]),
    ]),
    "qixi": ("七夕約會：浪漫小心機", [
        ("style", 0.35, _V, ["romantic"]),
        ("occasion", 0.25, _V, ["Smart Casual"]),
        ("color", 0.30, _V, ["Pink", "Red", "Rose", "Lavender"]),
    ]),
    "fathers_day": ("八八父親節：陪爸爸吃飯，穿得體面一點", [
        ("occasion", 0.20, _V, ["Smart Casual"]),
        ("style", 0.15, _V, ["classic", "preppy"]),
    ]),
    "ghost_festival": ("中元普渡拜拜：素雅低調就好", [
        ("boldness", 0.20, _T, 0.5),
        ("occasion", 0.15, _V, ["Casual"]),
    ]),
    "back_to_school": ("開學季：新學期新造型", [
        ("style", 0.25, _V, ["preppy", "streetwear", "minimalist"]),
        ("occasion", 0.25, _V, ["Casual"]),
    ]),
}


def _ramp(o: Occasion, d: date) -> float:
    days = o.days_until(d)
    if days <= 0 or o.window_days_before <= 0:
        return 1.0
    return RAMP_FLOOR + (1.0 - RAMP_FLOOR) * (1.0 - days / o.window_days_before)


def _countdown(o: Occasion, d: date) -> str:
    days = o.days_until(d)
    if days == 0:
        return f"{o.name_zh}就是今天" if o.start == o.end or d == o.start else f"{o.name_zh}進行中"
    if days == 1:
        return f"明天就{o.name_zh}"
    return f"{o.name_zh}倒數 {days} 天"


def signal_for(o: Occasion, d) -> ContextSignal:
    d = _to_date(d)
    base_label, rules = RULES.get(o.key, (f"{o.name_zh}快到了", []))
    k = _ramp(o, d)
    prefs = []
    for column, w, kind, arg in rules:
        weight = round(min(MAX_SIGNAL_WEIGHT, w * k), 3)
        reason = f"{o.name_zh}：{base_label.split('：', 1)[-1]}"
        if kind == _V:
            prefs.append(AttributePref(column=column, weight=weight, reason=reason, values=list(arg)))
        else:
            prefs.append(AttributePref(column=column, weight=weight, reason=reason, target=float(arg)))
    return ContextSignal(
        source="festival",
        label=f"{_countdown(o, d)}｜{base_label}",
        prefs=prefs,
        affects_ranking=bool(prefs),
        opt_in=False,
        evidence=EVIDENCE,
        detail={"festival": o.name_zh, "festival_en": o.name_en, "key": o.key, "kind": o.kind,
                "start": o.start.isoformat(), "end": o.end.isoformat(),
                "days_until": o.days_until(d), "ramp": round(k, 3), "source_url": o.source_url},
    )


def signals(ctx=None, today=None) -> list[ContextSignal]:
    """Festival signals for ctx.event_date (or today when no event date is given)."""
    ev = getattr(ctx, "event_date", None) if ctx is not None and not isinstance(ctx, dict) \
        else (ctx or {}).get("event_date")
    target = _to_date(ev) if ev else _to_date(today or date.today())
    return [signal_for(o, target) for o in active_occasions(target)[:MAX_ACTIVE]]
