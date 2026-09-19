"""服裝規定解碼器 (dress-code decoder).

Invitations say "Black Tie", 「請著深色系」, 「白色派對」 or 「禁穿白色」. This turns such text into
things the engine can act on:

  constraints   -> kwargs for contracts.HardConstraints (occasion / color / excluded_values)
  design_steps  -> kansei element id -> steps (same ids as intent_adapter.DESIGN_PHRASES)
  style         -> catalog `style` vocabulary hints

Rule table + keyword matching, no model. Unknown text returns empty constraints and says so.

Creative touch -- Taiwan wedding-guest etiquette (common custom, not law): guests avoid all-white
(白色是新娘的顏色) and avoid head-to-toe black (全黑在傳統觀念裡偏喪禮). White is excluded as a hard
rule; all-black is a soft nudge towards brighter colour, because a black dress with colour
accessories is perfectly fine.
"""

from __future__ import annotations

import re
from typing import Any

WHITE = ["White", "Off White", "Cream"]
BLACK = ["Black"]
DARK = ["Black", "Navy Blue", "Charcoal", "Grey", "Maroon", "Burgundy", "Coffee Brown"]
RED = ["Red", "Maroon", "Burgundy"]

# zh / en colour words -> catalog colour values (for generic "禁穿X色" / "no X" / "請著X色")
COLOR_WORDS: dict[str, list[str]] = {
    "白": WHITE, "white": WHITE,
    "黑": BLACK, "black": BLACK,
    "紅": RED, "red": RED,
    "粉": ["Pink", "Rose", "Peach"], "pink": ["Pink", "Rose", "Peach"],
    "藍": ["Blue", "Navy Blue"], "blue": ["Blue", "Navy Blue"],
    "綠": ["Green", "Olive"], "green": ["Green", "Olive"],
    "黃": ["Yellow", "Mustard", "Gold"], "yellow": ["Yellow", "Mustard", "Gold"],
    "金": ["Gold"], "gold": ["Gold"],
    "紫": ["Purple", "Lavender"], "purple": ["Purple", "Lavender"],
    "灰": ["Grey", "Charcoal"], "grey": ["Grey", "Charcoal"], "gray": ["Grey", "Charcoal"],
    "米": ["Beige", "Khaki"], "beige": ["Beige", "Khaki"],
}

# Each rule: keywords (lower-case substrings), what it means, and how sure we are.
RULES: list[dict[str, Any]] = [
    {"id": "black_tie", "keys": ["black tie", "black-tie", "黑領結", "晚宴服", "white tie"],
     "occasion": ["Formal"], "steps": {"formal_style": 1.0, "glossy_fabric": 0.5, "tailored_fit": 0.5},
     "style": ["classic"], "conf": 0.95,
     "zh": "Black Tie＝最高規格晚宴：男生深色西裝／燕尾服、女生及地長禮服，布料可以有光澤"},
    {"id": "cocktail", "keys": ["cocktail", "雞尾酒", "小禮服"],
     "occasion": ["Formal"], "steps": {"formal_style": 0.5, "tailored_fit": 0.5, "glossy_fabric": 0.3},
     "style": ["classic", "romantic"], "conf": 0.9,
     "zh": "Cocktail＝介於正式與休閒之間：及膝小禮服或合身西裝，不用打到最正式"},
    {"id": "smart_casual", "keys": ["smart casual", "smart-casual", "精緻休閒", "時髦休閒"],
     "occasion": ["Smart Casual"], "steps": {"crisp_collar": 0.5, "minimal_design": 0.5},
     "style": ["minimalist", "preppy"], "conf": 0.9,
     "zh": "Smart Casual＝有質感的休閒：襯衫／針織＋休閒褲，可以不打領帶，但別穿運動服"},
    {"id": "business_casual", "keys": ["business casual", "商務休閒", "商務便服"],
     "occasion": ["Smart Casual", "Formal"], "steps": {"crisp_collar": 1.0, "tailored_fit": 0.5,
                                                      "formal_style": 0.3},
     "style": ["classic", "minimalist"], "conf": 0.9,
     "zh": "Business Casual＝上班也體面：有領襯衫、西裝褲或及膝裙，西裝外套可有可無"},
    {"id": "business_formal", "keys": ["business formal", "business attire", "商務正式", "正式服裝",
                                       "正式服装", "正裝", "formal attire", "formal wear", "穿著正式",
                                       "服裝正式"],
     "occasion": ["Formal"], "steps": {"formal_style": 1.0, "tailored_fit": 0.5,
                                       "structured_shoulders": 0.5},
     "style": ["classic"], "conf": 0.85,
     "zh": "正式服裝＝西裝套裝或端莊洋裝，剪裁俐落最重要"},
    {"id": "white_party", "keys": ["白色派對", "white party", "all white", "全白", "白色主題"],
     "occasion": [], "color_include": WHITE, "steps": {"bright_color": 0.5},
     "style": [], "conf": 0.9,
     "zh": "白色派對＝全身白色系，米白、奶油白都算"},
    {"id": "dark", "keys": ["深色系", "深色", "dark attire", "dark colou", "dark suit", "暗色"],
     "occasion": [], "color_include": DARK, "steps": {"dark_tone": 1.0},
     "style": [], "conf": 0.85,
     "zh": "深色系＝黑、深藍、炭灰、酒紅、深咖啡都可以"},
    {"id": "casual", "keys": ["休閒輕鬆", "輕鬆休閒", "輕便", "casual", "隨性", "不拘", "休閒"],
     "occasion": ["Casual"], "steps": {"casual_style": 1.0, "relaxed_fit": 0.5},
     "style": ["minimalist", "streetwear"], "conf": 0.75,
     "zh": "休閒輕鬆＝穿得舒服就好，T 恤、牛仔褲、球鞋都 OK"},
    {"id": "beach_wedding", "keys": ["海灘婚禮", "beach wedding", "沙灘婚禮", "海邊婚禮"],
     "occasion": ["Smart Casual"], "steps": {"relaxed_fit": 0.5, "bright_color": 0.5,
                                             "matte_fabric": 0.3},
     "style": ["bohemian", "romantic"], "conf": 0.9,
     "zh": "海灘婚禮＝輕盈透氣的淺色或花卉洋裝、亞麻襯衫，鞋子選平底涼鞋，細跟會陷進沙裡"},
    {"id": "wedding", "keys": ["婚禮", "喜宴", "wedding", "喜酒", "訂婚", "結婚"],
     "occasion": ["Formal"], "steps": {"formal_style": 0.5, "bright_color": 0.5},
     "style": ["romantic", "classic"], "conf": 0.8,
     "zh": "婚禮賓客：端莊得體、帶點喜氣的顏色最討喜"},
    {"id": "sporty", "keys": ["運動", "athletic", "sportswear", "active wear", "路跑"],
     "occasion": ["Sports"], "steps": {"athletic_style": 1.0}, "style": ["sporty"], "conf": 0.8,
     "zh": "運動風＝吸濕排汗的運動服＋球鞋"},
]

_BAN = r"(?:禁穿|勿穿|請勿穿著?|請勿著|不要穿|避免穿著?|避免|不可穿|不能穿|謝絕|\bno\b|\bavoid\b|don't wear|do not wear)"
_WEAR = r"(?:請著|請穿著?|穿著|dress in|wear|wearing)"


def _color_hits(fragment: str) -> list[str]:
    out: list[str] = []
    for word in sorted(COLOR_WORDS, key=len, reverse=True):
        if word in fragment:
            for c in COLOR_WORDS[word]:
                if c not in out:
                    out.append(c)
    return out


def decode(text: str) -> dict[str, Any]:
    """Translate an invitation's dress-code text into constraints the engine can use."""
    raw = (text or "").strip()
    t = raw.lower()
    if not t:
        return _empty("沒有收到任何服裝規定文字")

    matched: list[dict] = []
    for rule in RULES:
        if any(k in t for k in rule["keys"]):
            # 「海灘婚禮」 already covers the generic wedding rule; 「休閒」 inside 「商務休閒」 does not count
            if rule["id"] == "wedding" and any(r["id"] == "beach_wedding" for r in matched):
                matched.append({**rule, "occasion": [], "steps": {}, "style": [], "zh": "", "conf": 0.8})
                continue
            if rule["id"] == "casual" and any(r["id"] in ("smart_casual", "business_casual")
                                               for r in matched):
                continue
            matched.append(rule)

    include: list[str] = []
    exclude: list[str] = []
    explain: list[str] = []
    steps: dict[str, float] = {}
    style: list[str] = []
    occasion: list[str] = []
    conf = 0.0

    for r in matched:
        for o in r.get("occasion", []):
            if o not in occasion:
                occasion.append(o)
        for c in r.get("color_include", []):
            if c not in include:
                include.append(c)
        for k, v in r.get("steps", {}).items():
            steps[k] = round(steps.get(k, 0.0) + v, 3)
        for s in r.get("style", []):
            if s not in style:
                style.append(s)
        if r.get("zh"):
            explain.append(r["zh"])
        conf = max(conf, r["conf"])

    # generic colour prohibitions: 禁穿白色 / 請勿穿著紅色 / no white
    for m in re.finditer(_BAN + r"\s*([^，。,.;；、]{0,12})", t):
        hits = _color_hits(m.group(1))
        for c in hits:
            if c not in exclude:
                exclude.append(c)
        if hits:
            explain.append(f"邀請函寫明「{m.group(0).strip()}」：這些顏色一律排除")
            conf = max(conf, 0.95)

    # generic colour requests: 請著紅色 / wear pink  (skip if it is itself a ban)
    for m in re.finditer(_WEAR + r"\s*([^，。,.;；、]{0,8})", t):
        start = m.start()
        if re.search(_BAN + r"\s*$", t[max(0, start - 8):start]):
            continue
        frag = m.group(1)
        if "深色" in frag or "dark" in frag:
            continue
        hits = _color_hits(frag)
        for c in hits:
            if c not in include:
                include.append(c)
        if hits:
            explain.append(f"指定色系「{m.group(0).strip()}」")
            conf = max(conf, 0.85)

    # Taiwan wedding-guest etiquette (a creative, custom-based touch)
    ids = {r["id"] for r in matched}
    if ids & {"wedding", "beach_wedding"}:
        for c in WHITE:
            if c not in exclude:
                exclude.append(c)
        steps["dark_tone"] = round(steps.get("dark_tone", 0.0) - 0.5, 3)
        explain.append("台灣喝喜酒的習俗：白色留給新娘，賓客避開全白；全身黑在傳統觀念裡偏喪禮，"
                       "建議加點亮色配件或選柔和的粉、藍、香檳色 💐")

    # a requirement that is also excluded cannot be satisfied: the exclusion wins
    include = [c for c in include if c not in exclude]

    if not matched and not include and not exclude:
        return _empty(f"看不懂「{raw}」是哪一種服裝規定，先不加任何條件；"
                      "可以試試 black tie、cocktail、smart casual、正式服裝、深色系、禁穿白色")

    constraints: dict[str, Any] = {}
    if occasion:
        constraints["occasion"] = {"state": "value", "values": occasion}
    if include:
        constraints["color"] = {"state": "value", "values": include}
    if exclude:
        constraints["excluded_values"] = {"color": exclude}

    return {
        "constraints": constraints,
        "design_steps": steps,
        "style": style,
        "matched_rules": [r["id"] for r in matched],
        "explanation_zh": "；".join(e for e in explain if e),
        "confidence": round(conf, 2),
    }


def _empty(why: str) -> dict[str, Any]:
    return {"constraints": {}, "design_steps": {}, "style": [], "matched_rules": [],
            "explanation_zh": why, "confidence": 0.0}
