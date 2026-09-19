"""Personal context signals: 四季色彩 (personal colour) and 今日心情 (mood).

Both are things the user explicitly chose, so every signal here is opt_in=True. The mappings are
stylist intuition, not measured -- evidence says so, and each weight stays well under
MAX_SIGNAL_WEIGHT so it nudges the ranking rather than overriding what the user asked for.

Colour strings come from engine02/attribute_fill.py COLOR_FAMILIES (catalog vocabulary); design
step ids are kansei element ids (engine02/resources/kansei_v0.json).
"""

from __future__ import annotations

from datetime import date

from engine02.context.base import AttributePref, ContextSignal

EVIDENCE = "intuition v0 (not yet measured)"

PALETTE_WEIGHT = 0.25
AVOID_WEIGHT = -0.15

# --------------------------------------------------------------------------------------------
# 四季色彩
# --------------------------------------------------------------------------------------------

PALETTES: dict[str, list[str]] = {
    # 暖亮：蜜桃、珊瑚橘、鵝黃、米色、清新暖綠
    "spring": ["Peach", "Orange", "Yellow", "Gold", "Beige", "Cream", "Lime Green", "Sea Green",
               "Turquoise Blue", "Tan"],
    # 冷柔：薰衣草、玫瑰粉、霧灰、海軍藍、粉藍
    "summer": ["Lavender", "Pink", "Rose", "Mauve", "Grey", "Grey Melange", "Navy Blue", "Blue",
               "Off White", "Steel"],
    # 暖深：橄欖綠、芥末黃、鏽紅、咖啡、卡其、酒紅
    "autumn": ["Olive", "Mustard", "Rust", "Brown", "Coffee Brown", "Khaki", "Burgundy", "Maroon",
               "Copper", "Bronze"],
    # 冷艷：黑、白、海軍藍、桃紅、正紅、銀
    "winter": ["Black", "White", "Navy Blue", "Magenta", "Red", "Silver", "Charcoal", "Purple",
               "Teal"],
}

# warm-light <-> cool-deep, cool-soft <-> warm-deep
OPPOSITE = {"spring": "winter", "winter": "spring", "summer": "autumn", "autumn": "summer"}

SEASON_ZH = {"spring": "春季型", "summer": "夏季型", "autumn": "秋季型", "winter": "冬季型"}

PALETTE_LABEL = {
    "spring": "你是春季型：蜜桃、珊瑚橘、鵝黃最顯氣色",
    "summer": "你是夏季型：薰衣草、玫瑰粉、霧灰藍最溫柔",
    "autumn": "你是秋季型：大地色、橄欖綠最顯氣色",
    "winter": "你是冬季型：黑白、正紅、桃紅最有氣場",
}

PALETTE_REASON = {
    "spring": "春季型暖亮色，襯出好氣色",
    "summer": "夏季型冷柔色，氣質加分",
    "autumn": "秋季型大地色，顯白又有質感",
    "winter": "冬季型高對比冷艷色，氣場全開",
}


def avoid_colors(season: str) -> list[str]:
    """The opposite season's palette, minus anything that also flatters this season."""
    own = set(PALETTES[season])
    return [c for c in PALETTES[OPPOSITE[season]] if c not in own]


def personal_color_signal(season: str) -> ContextSignal:
    zh = SEASON_ZH[season]
    opp_zh = SEASON_ZH[OPPOSITE[season]]
    return ContextSignal(
        source="personal_color",
        label=PALETTE_LABEL[season],
        prefs=[
            AttributePref("color", PALETTE_WEIGHT, PALETTE_REASON[season], values=list(PALETTES[season])),
            AttributePref("color", AVOID_WEIGHT, f"{opp_zh}的顏色容易讓{zh}顯得沒精神",
                          values=avoid_colors(season)),
        ],
        affects_ranking=True,
        opt_in=True,
        evidence=EVIDENCE,
        detail={"personal_color": season, "opposite": OPPOSITE[season]},
    )


# --------------------------------------------------------------------------------------------
# 今日心情
# --------------------------------------------------------------------------------------------

# Each entry: label, boldness target (0 basic .. 3 avant-garde), design steps, extra prefs
MOODS: dict[str, dict] = {
    "energetic": {
        "label": "今天元氣滿滿 → 飽和色走起",
        "boldness": 2.0,
        "design_steps": {"bright_color": 1.0, "casual_style": 1.0},
        "prefs": [
            AttributePref("color", 0.2, "元氣色：跟心情一樣亮",
                          values=["Yellow", "Orange", "Red", "Turquoise Blue", "Lime Green", "Magenta"]),
            AttributePref("style", 0.15, "活力感單品", values=["sporty", "streetwear"]),
        ],
    },
    "calm": {
        "label": "想安安靜靜的一天 → 低飽和極簡風",
        "boldness": 0.5,
        "design_steps": {"minimal_design": 1.0, "matte_fabric": 1.0},
        "prefs": [
            AttributePref("color", 0.2, "柔和低飽和色，看了就放鬆",
                          values=["Beige", "Cream", "Off White", "Grey", "Grey Melange", "Lavender",
                                  "Khaki"]),
            AttributePref("style", 0.15, "乾淨俐落的極簡線條", values=["minimalist", "classic"]),
        ],
    },
    "confident": {
        "label": "氣場全開 → 俐落剪裁撐起主場",
        "boldness": 2.0,
        "design_steps": {"tailored_fit": 1.0, "formal_style": 1.0, "structured_shoulders": 1.0},
        "prefs": [
            AttributePref("style", 0.15, "有態度的經典款", values=["classic", "edgy"]),
        ],
    },
    "low": {
        "label": "抱抱自己：軟綿綿針織",
        "boldness": 0.0,
        "design_steps": {"soft_knit": 1.0, "relaxed_fit": 1.0},
        "prefs": [
            AttributePref("color", 0.15, "溫暖的奶茶色系，像被抱著",
                          values=["Beige", "Cream", "Tan", "Peach", "Rose", "Off White"]),
            AttributePref("style", 0.1, "舒服就好", values=["minimalist", "romantic"]),
        ],
    },
    "adventurous": {
        "label": "今天試試沒穿過的風格",
        "boldness": 3.0,
        "design_steps": {"bold_pattern": 1.0, "visible_logo": 1.0},
        "prefs": [
            AttributePref("style", 0.2, "跳出舒適圈的大膽風格", values=["avant_garde", "streetwear", "edgy"]),
        ],
    },
}

MOOD_BOLDNESS_WEIGHT = 0.2


def mood_signal(mood: str) -> ContextSignal:
    m = MOODS[mood]
    prefs = [AttributePref("boldness", MOOD_BOLDNESS_WEIGHT, f"心情配飽和度：大膽度 {m['boldness']:g}/3",
                           target=m["boldness"])]
    prefs += [AttributePref(p.column, p.weight, p.reason, values=list(p.values)) for p in m["prefs"]]
    return ContextSignal(
        source="mood",
        label=m["label"],
        prefs=prefs,
        design_steps=dict(m["design_steps"]),
        affects_ranking=True,
        opt_in=True,
        evidence=EVIDENCE,
        detail={"mood": mood},
    )


# --------------------------------------------------------------------------------------------

def _get(ctx, name):
    if ctx is None:
        return None
    if isinstance(ctx, dict):
        return ctx.get(name)
    return getattr(ctx, name, None)


def signals(ctx, today: date | None = None) -> list[ContextSignal]:
    """ContextInput (or a plain dict) -> personal colour + mood signals. Unknown values are ignored."""
    out: list[ContextSignal] = []
    season = _get(ctx, "personal_color")
    if season in PALETTES:
        out.append(personal_color_signal(season))
    mood = _get(ctx, "mood")
    if mood in MOODS:
        out.append(mood_signal(mood))
    return out
