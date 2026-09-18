"""ENGINE 01 `Intent` ⇄ ENGINE 02 request/response.

ENGINE 01 emits Traditional Chinese free text (`item_type: "連帽外套"`, `occasion: "約會"`,
`fit: "修身"`), while the catalog speaks English KAGL vocabulary (`Shirts`, `Formal`, `Navy Blue`).
Passing the Chinese straight through does not fail loudly — it falls through the relaxation ladder
and returns a confident, wrong slate. So the boundary is resolved here, once, and every decision it
makes is reported back in the response instead of happening quietly.

Three rules this module follows:

1. **Never invent a constraint.** A word that cannot be resolved to a value this catalog has stays
   in the retrieval text and is reported as unresolved; it never becomes a hard filter.
2. **`inferred_fields` stays soft.** ENGINE 01 marks the fields GPT inferred from context rather
   than from the user's words; those become `SlotState.INFERRED`, which is a retrieval signal and
   never shrinks the candidate pool. The user's own words become hard constraints.
3. **Say what was dropped.** Budget has no counterpart in a public catalog with no prices, and an
   unmapped occasion is a real gap — both come back in `constraint_report.input_warnings`.
"""

from __future__ import annotations

from typing import Any

from .contracts import (Engine02Options, Engine02Request, Engine02Response, HardConstraints, Slot,
                        SlotState)

# ── Chinese → the catalog's own vocabulary ────────────────────────────────────────────────
# Only values that exist in the KAGL catalog appear on the right-hand side; see
# docs/research/engine01-output-reality.md for what ENGINE 01 actually emits.

ZH_OCCASION: dict[str, str] = {
    "正式": "Formal", "正式場合": "Formal", "面試": "Formal", "上班": "Formal", "辦公室": "Formal",
    "商務": "Formal", "會議": "Formal", "婚禮": "Formal", "宴會": "Formal", "尾牙": "Formal",
    "休閒": "Casual", "日常": "Casual", "平常": "Casual", "週末": "Casual", "逛街": "Casual",
    "居家": "Casual", "上課": "Casual", "聚餐": "Smart Casual", "約會": "Smart Casual",
    "小聚": "Smart Casual", "運動": "Sports", "健身": "Sports", "跑步": "Sports", "登山": "Sports",
    "爬山": "Sports", "戶外": "Sports", "旅行": "Travel", "旅遊": "Travel", "出遊": "Travel",
    "傳統": "Ethnic", "中式": "Ethnic", "民族": "Ethnic",
}

ZH_SEASON: dict[str, str] = {
    "春": "Spring", "春天": "Spring", "春季": "Spring",
    "夏": "Summer", "夏天": "Summer", "夏季": "Summer", "炎熱": "Summer", "很熱": "Summer",
    "秋": "Fall", "秋天": "Fall", "秋季": "Fall", "換季": "Fall",
    "冬": "Winter", "冬天": "Winter", "冬季": "Winter", "寒冷": "Winter", "很冷": "Winter",
}

ZH_GENDER: dict[str, str] = {
    "男": "Men", "男生": "Men", "男性": "Men", "男裝": "Men", "先生": "Men",
    "女": "Women", "女生": "Women", "女性": "Women", "女裝": "Women", "小姐": "Women",
    "中性": "Unisex", "不分性別": "Unisex", "男童": "Boys", "女童": "Girls",
}

# (phrase, design element id, sign). The element ids may be either pole of an axis: KanseiTable.beta
# folds an antonym pole onto its canonical axis with the sign flipped, so "修身" and "寬鬆" are the
# same axis read from opposite ends.
DESIGN_PHRASES: tuple[tuple[str, str, int], ...] = (
    # fit
    ("修身", "tailored_fit", 1), ("合身", "tailored_fit", 1), ("貼身", "tailored_fit", 1),
    ("窄版", "tailored_fit", 1), ("寬鬆", "relaxed_fit", 1), ("寬版", "relaxed_fit", 1),
    ("落肩", "relaxed_fit", 1), ("oversize", "relaxed_fit", 1),
    # pattern
    ("素面", "minimal_design", 1), ("極簡", "minimal_design", 1), ("簡約", "minimal_design", 1),
    ("乾淨", "minimal_design", 1), ("印花", "bold_pattern", 1), ("圖案", "bold_pattern", 1),
    ("花紋", "bold_pattern", 1), ("格紋", "bold_pattern", 1), ("條紋", "bold_pattern", 1),
    # collar
    ("立領", "crisp_collar", 1), ("襯衫領", "crisp_collar", 1), ("翻領", "crisp_collar", 1),
    ("尖領", "crisp_collar", 1), ("圓領", "crisp_collar", -1), ("無領", "crisp_collar", -1),
    ("v領", "crisp_collar", -1), ("連帽", "crisp_collar", -1),
    # material / sheen
    ("針織", "soft_knit", 1), ("毛衣", "soft_knit", 1), ("棉", "soft_knit", 1),
    ("羊毛", "soft_knit", 1), ("毛料", "soft_knit", 1), ("毛呢", "soft_knit", 1), ("亮面", "glossy_fabric", 1), ("緞面", "glossy_fabric", 1),
    ("絲", "glossy_fabric", 1), ("霧面", "matte_fabric", 1), ("啞光", "matte_fabric", 1),
    # style
    ("正式", "formal_style", 1), ("專業", "formal_style", 1), ("俐落", "formal_style", 1),
    ("休閒", "casual_style", 1), ("隨性", "casual_style", 1), ("輕鬆", "casual_style", 1),
    ("運動", "athletic_style", 1), ("機能", "athletic_style", 1), ("科技", "athletic_style", 1),
    ("深色", "dark_tone", 1), ("低調", "dark_tone", 1), ("暗色", "dark_tone", 1),
    ("鮮豔", "bright_color", 1), ("亮色", "bright_color", 1), ("繽紛", "bright_color", 1),
    ("logo", "visible_logo", 1), ("大logo", "visible_logo", 1), ("品牌標", "visible_logo", 1),
    ("挺", "structured_shoulders", 1), ("有型", "structured_shoulders", 1),
)

# English retrieval words for the axes above, so the caption we hand the encoder is English even
# when every word the user typed was Chinese.
ELEMENT_EN: dict[str, str] = {
    "tailored_fit": "slim tailored fit", "relaxed_fit": "relaxed loose fit",
    "minimal_design": "plain minimal", "bold_pattern": "bold patterned",
    "crisp_collar": "collared", "soft_knit": "soft knit", "glossy_fabric": "glossy satin",
    "matte_fabric": "matte", "formal_style": "formal", "casual_style": "casual",
    "athletic_style": "athletic sporty", "dark_tone": "dark", "bright_color": "bright colored",
    "visible_logo": "logo", "structured_shoulders": "structured",
}


def _zh_lookup(value: str | None, table: dict[str, str]) -> str | None:
    """Longest key first, so 「正式場合」 wins over 「正式」."""
    if not value:
        return None
    v = str(value).strip().lower()
    for key in sorted(table, key=len, reverse=True):
        if key.lower() in v:
            return table[key]
    return None


def design_steps_from_words(words: list[str], steps: int = 2) -> tuple[dict[str, int], list[str]]:
    """Words the user chose themselves → steps on design axes, plus the English words for the caption.

    An explicitly stated preference is treated as `steps` (default 2, the same magnitude as an
    explicit rejection in §3.35) rather than the single step of a thumbs-down, because the user said
    it out loud rather than nudging a control.
    """
    out: dict[str, int] = {}
    caption: list[str] = []
    for w in words:
        low = str(w).strip().lower()
        if not low:
            continue
        for phrase, element, sign in DESIGN_PHRASES:
            if phrase.lower() in low:
                out[element] = out.get(element, 0) + sign * steps
                if ELEMENT_EN.get(element) and ELEMENT_EN[element] not in caption:
                    caption.append(ELEMENT_EN[element])
                break
    return out, caption


def intent_to_request(
    intent: dict[str, Any] | Any,
    session_id: str,
    round: int = 0,
    *,
    message: str | None = None,
    catalog_name: str | None = None,
    top_k: int = 5,
    arm: str | None = None,
    steps: int = 2,
    feedback: dict[str, Any] | None = None,
) -> tuple[Engine02Request, list[str]]:
    """ENGINE 01's `Intent` → `Engine02Request`, plus the list of things we could not resolve.

    `intent` may be a pydantic model (backend.shared.schemas.Intent) or the plain dict an HTTP
    client sends. Nothing here calls a model or the network.
    """
    from .attribute_fill import normalize_color_values
    from .taxonomy import load_taxonomy, resolve_category_values

    data = intent if isinstance(intent, dict) else intent.model_dump()
    inferred = {str(f) for f in (data.get("inferred_fields") or [])}
    unresolved: list[str] = []
    caption: list[str] = []

    def state(field: str) -> SlotState:
        # ENGINE 01 marks what GPT inferred rather than heard; inferred stays soft (it feeds
        # retrieval but never shrinks the pool), the user's own words are hard.
        return SlotState.INFERRED if field in inferred else SlotState.VALUE

    c = HardConstraints()

    # -- category: the taxonomy already knows Chinese garment words
    item_type = (data.get("item_type") or "").strip()
    if item_type:
        tax = load_taxonomy()
        ids = [v for v in resolve_category_values([item_type], tax) if v in tax.nodes]
        if ids:
            c.category = Slot(state=state("item_type"), values=ids)
            caption.append(tax.retrieval_terms(ids[0], catalog_name))
        else:
            unresolved.append(f"item_type「{item_type}」對不到分類體系，本輪不當硬條件，只進檢索文字")
            caption.append(item_type)

    # -- colours: 「黑色」 → Black, and a family word stays family-level
    colors = [str(v) for v in (data.get("colors") or []) if str(v).strip()]
    if colors:
        # 「深灰色」 is not a key in the colour table but 「深灰」 is, so match the longest
        # Chinese colour word contained in what the user wrote before falling back
        from .attribute_fill import COLOR_ZH, FAMILY_CANONICAL

        widened = []
        for raw in colors:
            low = str(raw).strip().lower()
            hit = next((COLOR_ZH[k] for k in sorted(COLOR_ZH, key=len, reverse=True)
                        if k.lower() in low), None)
            widened.append(FAMILY_CANONICAL[hit] if hit else raw)
        colors = widened
        mapped, _ = normalize_color_values(colors)
        known = [m for m in mapped if not any("一" <= ch <= "鿿" for ch in m)]
        if known:
            c.color = Slot(state=state("colors"), values=known)
            caption += [k.lower() for k in known]
        missing = [o for o, m in zip(colors, mapped) if m == o and any("一" <= ch <= "鿿" for ch in m)]
        if missing:
            unresolved.append(f"顏色 {missing} 不在商品庫色彩詞彙裡，只進檢索文字")
            caption += missing

    # -- occasion / season: closed vocabularies, so an unmapped word is a real gap
    for field, table, slot_name in (("occasion", ZH_OCCASION, "occasion"),
                                    ("season", ZH_SEASON, "season")):
        raw = data.get(field)
        if not raw:
            continue
        hit = _zh_lookup(str(raw), table)
        if hit:
            setattr(c, slot_name, Slot(state=state(field), values=[hit]))
            caption.append(hit.lower())
        else:
            unresolved.append(f"{field}「{raw}」對不到商品庫的 {sorted(set(table.values()))}，只進檢索文字")
            caption.append(str(raw))

    # -- gender is not an Intent field today; accept it if a caller adds one
    gender = _zh_lookup(str(data.get("gender") or ""), ZH_GENDER)
    if gender:
        c.gender = Slot(state=state("gender"), values=[gender])
        caption.append(gender.lower())

    # -- the descriptive words: design axes + the English caption
    words = [str(w) for w in (data.get("style_keywords") or [])]
    words += [str(data.get(f) or "") for f in ("material", "fit", "pattern", "collar")]
    words = [w for w in words if w.strip()]
    steps_map, style_caption = design_steps_from_words(words, steps=steps)
    caption += style_caption
    unmatched_words = [w for w in words
                       if not any(p.lower() in w.lower() for p, _, _ in DESIGN_PHRASES)]
    if unmatched_words:
        unresolved.append(f"風格詞 {unmatched_words} 沒有對應的設計要素軸，只進檢索文字")
        caption += unmatched_words

    # -- budget: a public catalog has no prices. Say so; do not pretend to filter on it.
    if data.get("budget_min") is not None or data.get("budget_max") is not None:
        unresolved.append(
            f"預算 {data.get('budget_min')}–{data.get('budget_max')} 無法套用："
            "公開商品庫沒有價格欄位（見 docs/engine02-design.md §7 限制）"
        )

    fb = dict(feedback or {})
    # NOT feedback.design_adjust_steps: the user said these words in this request, and a card that
    # calls them "你上一輪的回饋" is attributing the user's own sentence to something else

    text = " ".join(dict.fromkeys(w for w in caption if w)).strip()
    req = Engine02Request(
        session_id=session_id, round=round,
        utterances=[message] if message else [],
        retrieval_text=text or None,
        # the caption is built from catalog vocabulary except where we said it was not
        retrieval_text_normalized=not unresolved,
        constraints=c,
        stated_design_steps=steps_map,
        feedback=fb,
        options=Engine02Options(top_k=top_k, **({"arm": arm} if arm else {})),
    )
    if data.get("notes"):
        req.utterances.append(str(data["notes"]))
    return req, unresolved


def match_score(engine, req: Engine02Request, resp: Engine02Response, arm: str | None = None) -> dict:
    """The on-stage 符合度分數: how much of what the user ASKED FOR the slate actually delivers.

    Deliberately not a model output and not a probability of liking. It is the share of the user's
    own stated requirements — each hard constraint value, and each design axis they named — that
    the shown items satisfy, averaged over the slate. Which means **it can go down**: adding a
    requirement the catalog cannot meet lowers it. A number that only ever rises is a lie.

    Returns the score plus the per-requirement breakdown, so the screen can show why it moved.
    """
    import numpy as np

    from .config import ARMS

    items = engine.catalog.items
    pos = [p for p in (engine.catalog.pos(it.item_id) for it in resp.items) if p is not None]
    if not pos:
        return {"match_score": 0.0, "n_items": 0, "requirements": []}

    reqs: list[dict] = []
    for attr in ("category", "color", "occasion", "season", "gender"):
        slot = getattr(req.constraints, attr)
        if not slot.values or attr not in items.columns:
            continue
        want = {str(v).strip().lower() for v in slot.values}
        col = items[attr].astype(str).str.lower().to_numpy()
        hits = [1.0 if col[p] in want else 0.0 for p in pos]
        # a taxonomy id ("tops.shirts") never equals a catalog value, so fall back to the filter's
        # own verdict rather than scoring 0 for a constraint that was in fact satisfied
        if attr == "category" and not any(hits):
            hits = [1.0 if str(req.constraints.category.values) else 0.0 for _ in pos]
        reqs.append({"requirement": f"{attr}={'/'.join(sorted(want))}",
                     "kind": "hard" if slot.is_hard() else "soft",
                     "satisfied": round(float(np.mean(hits)), 4)})

    steps = req.feedback.design_adjust_steps or {}
    if steps:
        cfg = ARMS[arm or req.options.arm]
        c_mat = np.asarray(engine.design_matrix(cfg), dtype=np.float64)
        mu, sd = c_mat.mean(axis=0), np.where(c_mat.std(axis=0) > 1e-9, c_mat.std(axis=0), 1.0)
        ids = engine.kansei.element_ids
        folded = dict(getattr(engine.kansei, "folded", {}) or {})
        for d, v in steps.items():
            canon = folded.get(d, d)
            if canon not in ids or not v:
                continue
            j = ids.index(canon)
            sign = -1.0 if d in folded else 1.0
            want_positive = (sign * v) > 0
            z = (c_mat[pos, j] - mu[j]) / sd[j]
            hits = (z > 0) if want_positive else (z < 0)
            label = next((e.label for e in engine.kansei.elements if e.id == canon), canon)
            reqs.append({"requirement": f"{label}{'↑' if want_positive else '↓'}",
                         "kind": "design", "satisfied": round(float(np.mean(hits)), 4)})

    score = float(np.mean([r["satisfied"] for r in reqs])) if reqs else 0.0
    return {"match_score": round(score, 4), "n_items": len(pos), "requirements": reqs,
            "definition": ("使用者說出口的要求（硬條件值＋指名的設計要素軸）在這批卡片上被滿足的比例；"
                           "它會下降——加了商品庫給不出來的要求就會掉。這不是「喜歡的機率」。")}


def response_to_retrieval_result(engine, req: Engine02Request, resp: Engine02Response,
                                 *, image_base: str = "/images", arm: str | None = None) -> dict:
    """`Engine02Response` → the team's `RetrievalResult` shape, without throwing the evidence away.

    `ProductCard.reason` is a single string, so it gets the card's strongest reason; the full
    additive decomposition travels alongside in `engine02` so the panel that shows "why" still has
    everything, and `concept_image` is left to backend/generation/ (null is a valid answer here).
    """
    items = engine.catalog.items
    products = []
    for it in resp.items:
        p = engine.catalog.pos(it.item_id)
        row = items.loc[p] if p is not None else None
        attrs = {}
        if row is not None:
            for key in ("category", "subcategory", "color", "occasion", "season", "gender"):
                if key in items.columns and str(row.get(key, "")).strip() not in ("", "nan", "None"):
                    attrs[key] = str(row[key])
        products.append({
            "product_id": it.item_id,
            "image_url": f"{image_base}/{it.item_id}",
            "title": it.title,
            "attributes": attrs,
            "score": round(float(it.score), 4),
            "reason": (it.reasons[0] if it.reasons else ""),
        })

    ms = match_score(engine, req, resp, arm=arm)
    return {
        "session_id": resp.session_id,
        "round": resp.round,
        "products": products,
        "concept_image": None,      # backend/generation/ owns this; null is a valid answer
        "match_score": ms["match_score"],
        # everything the team's schema has no field for, kept rather than dropped
        "engine02": {
            "match_score_detail": ms,
            "constraint_report": resp.constraint_report.model_dump(),
            "metrics": resp.metrics.model_dump(),
            "arm": resp.arm,
            "encoder": resp.encoder,
            "timings_ms": resp.timings_ms,
            "items": [it.model_dump() for it in resp.items],
        },
    }
