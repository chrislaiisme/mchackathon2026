"""五題四季色彩小測驗 (zh-TW). Pure data + deterministic scoring, ready to render on a frontend.

answers = {"vein": "green", "metal": "gold", ...}  (question id -> option id)
score_quiz(answers) -> {"personal_color": "autumn", "confidence": 0.55, "explanation_zh": "..."}

Two axes underneath: 冷暖 (vein, metal) and 深淺/對比 (sun, contrast); the neutral question votes
directly for a season. Entertainment-grade, not a colour analyst.
"""

from __future__ import annotations

SEASONS = ("spring", "summer", "autumn", "winter")      # also the tie-break order

QUESTIONS: list[dict] = [
    {
        "id": "vein",
        "question": "看看手腕內側的血管，大多是什麼顏色？",
        "options": [
            {"id": "green", "text": "偏綠色", "scores": {"spring": 1, "autumn": 1}},
            {"id": "blue", "text": "偏藍紫色", "scores": {"summer": 1, "winter": 1}},
            {"id": "unsure", "text": "藍綠都有、分不太出來", "scores": {"spring": 0.5, "summer": 0.5}},
        ],
    },
    {
        "id": "metal",
        "question": "戴哪種飾品時，朋友最常說你氣色好？",
        "options": [
            {"id": "gold", "text": "金色、玫瑰金", "scores": {"spring": 1, "autumn": 1}},
            {"id": "silver", "text": "銀色、白金", "scores": {"summer": 1, "winter": 1}},
            {"id": "both", "text": "兩種都還可以", "scores": {}},
        ],
    },
    {
        "id": "sun",
        "question": "夏天在外面曬一整天，皮膚通常會？",
        "options": [
            {"id": "burn", "text": "很快曬紅、不太會黑", "scores": {"summer": 1, "spring": 0.5}},
            {"id": "golden", "text": "先微紅，之後變成健康小麥色", "scores": {"spring": 1, "autumn": 0.5}},
            {"id": "tan", "text": "很快就曬黑", "scores": {"autumn": 1, "winter": 1}},
        ],
    },
    {
        "id": "contrast",
        "question": "天生的髮色、眼珠和膚色擺在一起，感覺比較像？",
        "options": [
            {"id": "high", "text": "黑髮黑眼、膚色白皙，對比很強", "scores": {"winter": 2}},
            {"id": "soft", "text": "整體柔和、霧霧的，沒有強烈對比", "scores": {"summer": 2}},
            {"id": "bright", "text": "淺棕髮、眼睛亮亮的、有透明感", "scores": {"spring": 2}},
            {"id": "deep_warm", "text": "深棕髮、眼神溫暖，有種沉穩感", "scores": {"autumn": 2}},
        ],
    },
    {
        "id": "neutral",
        "question": "穿哪一種基本色，最常被稱讚好看？",
        "options": [
            {"id": "black_white", "text": "純黑、純白", "scores": {"winter": 2}},
            {"id": "ivory_camel", "text": "象牙白、駝色", "scores": {"spring": 2}},
            {"id": "grey_navy", "text": "霧灰、海軍藍", "scores": {"summer": 2}},
            {"id": "brown_khaki", "text": "咖啡色、橄欖卡其", "scores": {"autumn": 2}},
        ],
    },
]

_OPTION_SCORES = {q["id"]: {o["id"]: o["scores"] for o in q["options"]} for q in QUESTIONS}

SEASON_EXPLAIN_ZH = {
    "spring": "春季型（暖・亮）：你適合明亮溫暖的顏色，蜜桃、珊瑚橘、鵝黃、象牙白都能讓氣色像打了光。",
    "summer": "夏季型（冷・柔）：你適合低飽和的冷色，薰衣草、玫瑰粉、霧灰、海軍藍最顯溫柔氣質。",
    "autumn": "秋季型（暖・深）：你適合濃郁的大地色，橄欖綠、芥末黃、鏽紅、咖啡色穿起來最有質感。",
    "winter": "冬季型（冷・艷）：你適合高對比的純色，黑白、正紅、桃紅、寶藍一上身氣場全開。",
}


def score_quiz(answers: dict) -> dict:
    """Sum option scores per season; highest wins, ties broken by SEASONS order. Unknown question or
    option ids are ignored. No usable answers -> personal_color None, confidence 0."""
    totals = {s: 0.0 for s in SEASONS}
    answered = 0
    for qid, oid in (answers or {}).items():
        scores = _OPTION_SCORES.get(qid, {}).get(oid)
        if scores is None:
            continue
        answered += 1
        for s, v in scores.items():
            totals[s] += v
    total = sum(totals.values())
    if answered == 0 or total == 0:
        return {"personal_color": None, "confidence": 0.0, "scores": totals,
                "explanation_zh": "還沒有足夠的答案，回答幾題就能知道你的四季色彩喔！"}
    ranked = sorted(SEASONS, key=lambda s: (-totals[s], SEASONS.index(s)))
    best, second = ranked[0], ranked[1]
    # share of the vote, discounted for unanswered questions and close races
    share = totals[best] / total
    margin = (totals[best] - totals[second]) / max(totals[best], 1e-9)
    coverage = answered / len(QUESTIONS)
    confidence = round(min(1.0, (0.5 * share + 0.5 * margin) * coverage + 0.2 * coverage), 2)
    explanation = SEASON_EXPLAIN_ZH[best]
    if margin < 0.25:
        explanation += f"（你和{_zh(second)}很接近，兩邊的顏色都可以試試看）"
    return {"personal_color": best, "confidence": confidence, "scores": totals,
            "explanation_zh": explanation}


def _zh(season: str) -> str:
    return {"spring": "春季型", "summer": "夏季型", "autumn": "秋季型", "winter": "冬季型"}[season]
