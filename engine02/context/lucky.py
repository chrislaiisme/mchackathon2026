"""今日幸運色 -- ENTERTAINMENT ONLY, opt-in.

Nothing here is a style claim. It exists because users asked for it and it is fun on a card.
It only produces signals when the user fills ctx.lucky, and it only *ranks* when the user also
sets ctx.lucky["apply"] = True; otherwise the colour is shown on the card and scored nowhere.

Rule set (deterministic, documented):

1. 五行 colours:  木 綠 | 火 紅 | 土 黃/棕 | 金 白/金 | 水 黑/藍.

2. Day element (日干五行): the day's heavenly stem from the sexagenary day cycle,
       cycle index = (JDN + 49) mod 60   (0 = 甲子; e.g. 2000-01-01 -> 54 = 戊午)
       stem        = cycle index mod 10  (甲乙 木, 丙丁 火, 戊己 土, 庚辛 金, 壬癸 水)
   with JDN = date.toordinal() + 1721425.

3. birth_year -> 生肖 animal = (year - 4) mod 12 (0 = 鼠) and year element from the year's stem
   (year - 4) mod 10. (Gregorian year; the few weeks before 春節 are deliberately ignored -- it is
   a game.) Lucky element for today:
     * day element generates yours (相生, 貴人日)  -> the day's element
     * day element equals yours (比和)              -> your own element
     * otherwise                                    -> the element that generates yours (補能量)
   Cycle 相生: 木 -> 火 -> 土 -> 金 -> 水 -> 木.

4. zodiac (western) -> the sign's classical element: fire 火象 = red/orange/gold, earth 土象 =
   olive/brown/beige, air 風象 = lavender/white/sky, water 水象 = navy/teal/sea green.

The headline colour (the one named on the card) rotates daily through the element's list:
index = (day ordinal + seed) mod len(list), seed = sign index / birth year. Same inputs, same day
-> same output.
"""

from __future__ import annotations

from datetime import date, datetime

from .base import AttributePref, ContextSignal

EVIDENCE = "entertainment, not a style claim"
WEIGHT = 0.2

ELEMENTS = ("木", "火", "土", "金", "水")
GENERATES = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}   # 相生
GENERATED_BY = {v: k for k, v in GENERATES.items()}
STEMS = "甲乙丙丁戊己庚辛壬癸"
BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
ANIMALS = "鼠牛虎兔龍蛇馬羊猴雞狗豬"

WUXING_COLORS: dict[str, list[str]] = {
    "木": ["Green", "Olive", "Sea Green"],
    "火": ["Red", "Burgundy", "Maroon", "Orange"],
    "土": ["Mustard", "Brown", "Tan", "Yellow"],
    "金": ["White", "Gold", "Silver", "Cream"],
    "水": ["Black", "Navy Blue", "Blue"],
}

ZODIAC_SIGNS = ("aries", "taurus", "gemini", "cancer", "leo", "virgo",
                "libra", "scorpio", "sagittarius", "capricorn", "aquarius", "pisces")
ZODIAC_ZH = {"牡羊": "aries", "白羊": "aries", "金牛": "taurus", "雙子": "gemini", "巨蟹": "cancer",
             "獅子": "leo", "處女": "virgo", "室女": "virgo", "天秤": "libra", "天蠍": "scorpio",
             "射手": "sagittarius", "人馬": "sagittarius", "摩羯": "capricorn", "魔羯": "capricorn",
             "水瓶": "aquarius", "寶瓶": "aquarius", "雙魚": "pisces"}
ZODIAC_LABEL = {"aries": "牡羊座", "taurus": "金牛座", "gemini": "雙子座", "cancer": "巨蟹座",
                "leo": "獅子座", "virgo": "處女座", "libra": "天秤座", "scorpio": "天蠍座",
                "sagittarius": "射手座", "capricorn": "摩羯座", "aquarius": "水瓶座", "pisces": "雙魚座"}
SIGN_ELEMENT = {s: ("fire", "earth", "air", "water")[i % 4] for i, s in enumerate(ZODIAC_SIGNS)}
ZODIAC_ELEMENT_ZH = {"fire": "火象", "earth": "土象", "air": "風象", "water": "水象"}
ZODIAC_COLORS: dict[str, list[str]] = {
    "fire": ["Red", "Orange", "Gold"],
    "earth": ["Olive", "Brown", "Beige"],
    "air": ["Lavender", "White", "Turquoise Blue"],
    "water": ["Navy Blue", "Teal", "Sea Green"],
}

COLOR_ZH = {
    "Green": "草綠", "Olive": "橄欖綠", "Sea Green": "海洋綠", "Red": "正紅", "Burgundy": "酒紅",
    "Maroon": "暗紅", "Orange": "橘色", "Mustard": "芥末黃", "Brown": "咖啡棕", "Tan": "駝色",
    "Yellow": "鵝黃", "White": "純白", "Gold": "金色", "Silver": "銀色", "Cream": "奶油白",
    "Black": "黑色", "Navy Blue": "海軍藍", "Blue": "寶藍", "Beige": "米色", "Lavender": "薰衣草紫",
    "Turquoise Blue": "湖水藍", "Teal": "藍綠",
}


def _to_date(v) -> date:
    if v is None:
        return date.today()
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def day_pillar(d) -> tuple[str, str]:
    """(干支 of the day, 五行 of its stem)."""
    idx = (_to_date(d).toordinal() + 1721425 + 49) % 60
    stem = idx % 10
    return STEMS[stem] + BRANCHES[idx % 12], ELEMENTS[stem // 2]


def year_info(year: int) -> tuple[str, str]:
    """(生肖, 年五行) for a Gregorian year."""
    return ANIMALS[(year - 4) % 12], ELEMENTS[((year - 4) % 10) // 2]


def lucky_element(own: str, day_el: str) -> tuple[str, str]:
    if GENERATES[day_el] == own:
        return day_el, "今天日子生你，貴人日"
    if day_el == own:
        return own, "今天和你同氣，順勢而為"
    return GENERATED_BY[own], "今天幫你補能量"


def _pick(colors: list[str], d: date, seed: int) -> str:
    return colors[(d.toordinal() + seed) % len(colors)]


def _normalize_sign(z) -> str | None:
    if not z:
        return None
    s = str(z).strip().lower().replace("座", "")
    if s in ZODIAC_SIGNS:
        return s
    return ZODIAC_ZH.get(s)


def _signal(label: str, colors: list[str], apply: bool, detail: dict) -> ContextSignal:
    return ContextSignal(
        source="lucky_color",
        label=label,
        prefs=[AttributePref(column="color", weight=WEIGHT, reason=label, values=list(colors))],
        affects_ranking=apply,
        opt_in=True,
        evidence=EVIDENCE,
        detail=detail,
    )


def signals(ctx=None, today=None) -> list[ContextSignal]:
    lucky = getattr(ctx, "lucky", None) if ctx is not None and not isinstance(ctx, dict) \
        else (ctx or {}).get("lucky")
    if not lucky or not isinstance(lucky, dict):
        return []
    ev = getattr(ctx, "event_date", None) if not isinstance(ctx, dict) else ctx.get("event_date")
    d = _to_date(ev or today)
    apply = lucky.get("apply") is True
    out: list[ContextSignal] = []

    year = lucky.get("birth_year")
    if year is not None:
        try:
            year = int(year)
        except (TypeError, ValueError):
            year = None
    if year is not None and 1900 <= year <= 2100:
        animal, own = year_info(year)
        pillar, day_el = day_pillar(d)
        el, why = lucky_element(own, day_el)
        colors = WUXING_COLORS[el]
        head = _pick(colors, d, year)
        out.append(_signal(
            f"今日幸運色：{COLOR_ZH.get(head, head)}（僅供娛樂）｜屬{animal}・{own}命，{pillar}日屬{day_el}，{why}",
            [head] + [c for c in colors if c != head], apply,
            {"system": "wuxing", "birth_year": year, "animal": animal, "year_element": own,
             "day_pillar": pillar, "day_element": day_el, "lucky_element": el, "headline": head,
             "date": d.isoformat()}))

    sign = _normalize_sign(lucky.get("zodiac"))
    if sign:
        elem = SIGN_ELEMENT[sign]
        colors = ZODIAC_COLORS[elem]
        head = _pick(colors, d, ZODIAC_SIGNS.index(sign))
        out.append(_signal(
            f"今日幸運色：{COLOR_ZH.get(head, head)}（僅供娛樂）｜{ZODIAC_LABEL[sign]}・{ZODIAC_ELEMENT_ZH[elem]}星座",
            [head] + [c for c in colors if c != head], apply,
            {"system": "western_zodiac", "zodiac": sign, "element": elem, "headline": head,
             "date": d.isoformat()}))
    return out
