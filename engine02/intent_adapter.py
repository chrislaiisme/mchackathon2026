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

import re
from typing import Any

from .contracts import (BudgetSlot, Engine02Options, Engine02Request, Engine02Response,
                        HardConstraints, Slot, SlotState)

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
    # ENGINE 01 is prompted in Chinese, but a user may still type an English word and the LLM
    # passes it through. ASCII phrases are matched on word boundaries so "informal" is not "formal".
    ("slim", "tailored_fit", 1), ("fitted", "tailored_fit", 1), ("loose", "relaxed_fit", 1),
    ("baggy", "relaxed_fit", 1), ("plain", "minimal_design", 1), ("minimal", "minimal_design", 1),
    ("simple", "minimal_design", 1), ("pattern", "bold_pattern", 1), ("printed", "bold_pattern", 1),
    ("striped", "bold_pattern", 1), ("collar", "crisp_collar", 1), ("collared", "crisp_collar", 1),
    ("knit", "soft_knit", 1), ("cotton", "soft_knit", 1), ("wool", "soft_knit", 1),
    ("glossy", "glossy_fabric", 1), ("satin", "glossy_fabric", 1), ("matte", "matte_fabric", 1),
    ("formal", "formal_style", 1), ("business", "formal_style", 1), ("casual", "casual_style", 1),
    ("sporty", "athletic_style", 1), ("athletic", "athletic_style", 1), ("dark", "dark_tone", 1),
    ("bright", "bright_color", 1), ("colorful", "bright_color", 1), ("logo", "visible_logo", 1),
    ("structured", "structured_shoulders", 1),
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


# Chinese colour words that name a specific catalog value, not just a family. Without these,
# 「深藍色」 collapses to the family canonical "Blue" and the 195 Navy Blue items are excluded.
ZH_COLOR_EXACT: dict[str, str] = {
    "深藍": "Navy Blue", "藏青": "Navy Blue", "海軍藍": "Navy Blue", "丹寧": "Navy Blue",
    "湖水藍": "Turquoise Blue", "土耳其藍": "Turquoise Blue", "藍綠": "Teal",
    "深灰": "Charcoal", "炭灰": "Charcoal", "麻灰": "Grey Melange", "銀": "Silver",
    "酒紅": "Burgundy", "暗紅": "Maroon", "磚紅": "Rust",
    "墨綠": "Olive", "軍綠": "Olive", "草綠": "Lime Green", "湖綠": "Sea Green",
    "米白": "Off White", "乳白": "Cream", "象牙": "Cream",
    "芥末": "Mustard", "金": "Gold", "銅": "Copper", "古銅": "Bronze",
    "咖啡": "Coffee Brown", "卡其": "Khaki", "駝": "Tan", "裸": "Nude", "膚": "Skin",
    "薰衣草": "Lavender", "桃紅": "Magenta", "玫瑰": "Rose", "蜜桃": "Peach", "藕": "Mauve",
}


def _zh_lookup(value: str | None, table: dict[str, str]) -> str | None:
    """Longest key first, so 「正式場合」 wins over 「正式」."""
    hits = _zh_lookup_all(value, table)
    return hits[0] if hits else None


def _zh_lookup_all(value: str | None, table: dict[str, str]) -> list[str]:
    """Every distinct value named in the phrase, longest key first.

    「秋冬」 names two seasons; returning only the longest match dropped Winter entirely, and
    ENGINE 01's own test set contains exactly that string.
    """
    if not value:
        return []
    v = str(value).strip().lower()
    out: list[str] = []
    for key in sorted(table, key=len, reverse=True):
        if key.lower() in v and table[key] not in out:
            out.append(table[key])
    return out


def design_steps_from_words(words: list[str], steps: int = 2) -> tuple[dict[str, int], list[str]]:
    """Words the user chose themselves → steps on design axes, plus the English words for the caption.

    An explicitly stated preference is treated as `steps` (default 2, the same magnitude as an
    explicit rejection in §3.35) rather than the single step of a thumbs-down, because the user said
    it out loud rather than nudging a control.
    """
    from .negation import ZH_CUES

    out: dict[str, int] = {}
    caption: list[str] = []
    for w in words:
        low = str(w).strip().lower()
        if not low:
            continue
        # ENGINE 01 puts whole phrases in style_keywords, negations included: 「不要太正式」 is a
        # request for LESS formal. Scoring it as +formal is the worst kind of bug here — it moves
        # the ranking the opposite way from what the user said, with a confident explanation.
        negated = any(cue in low for cue in ZH_CUES) or any(
            cue in low for cue in ("no ", "not ", "without", "avoid", "less"))
        for phrase, element, sign in DESIGN_PHRASES:
            pl = phrase.lower()
            # word boundaries for ASCII so "informal" is not "formal"; Chinese has no
            # word boundaries, so those phrases match as substrings
            boundary = chr(92) + "b"
            hit = (bool(re.search(boundary + re.escape(pl) + boundary, low))
                   if pl.isascii() else pl in low)
            if hit:
                direction = -sign if negated else sign
                out[element] = out.get(element, 0) + direction * steps
                en = ELEMENT_EN.get(element)
                # a negated word must not go into the caption either: the encoder would retrieve
                # exactly what the user rejected (NegBench, ICML 2025)
                if en and not negated and en not in caption:
                    caption.append(en)
                break
    return out, caption


def catalog_family_values(family: str, items=None) -> list[str]:
    """Every colour value a catalog actually has in a family, or the KAGL defaults without one."""
    from .attribute_fill import COLOR_FAMILIES, color_family

    known = list(COLOR_FAMILIES.get(family, ()))
    if items is None or "color" not in getattr(items, "columns", []):
        return known
    have = [str(v) for v in items["color"].dropna().unique() if color_family(v) == family]
    return have or known


def intent_to_request(
    intent: dict[str, Any] | Any,
    session_id: str,
    round: int = 0,
    *,
    message: str | None = None,
    catalog_name: str | None = None,
    catalog_items=None,
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
            exact = next((ZH_COLOR_EXACT[k] for k in sorted(ZH_COLOR_EXACT, key=len, reverse=True)
                          if k.lower() in low), None)
            if exact:
                widened.append(exact)          # 「深藍色」 is Navy Blue, not "some blue"
                continue
            fam = next((COLOR_ZH[k] for k in sorted(COLOR_ZH, key=len, reverse=True)
                        if k.lower() in low), None)
            if fam:
                # a bare family word means the whole family: 「藍色」 must not exclude Navy Blue
                widened += list(catalog_family_values(fam, catalog_items))
                continue
            widened.append(raw)
        colors = list(dict.fromkeys(widened))
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
        hits = _zh_lookup_all(str(raw), table)
        if hits:
            setattr(c, slot_name, Slot(state=state(field), values=hits))
            caption += [h.lower() for h in hits]
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

    # -- budget. This used to be turned straight into a "cannot be applied" warning, which was
    # right while every catalog had a null price column and wrong the moment one did not: a
    # budget that is never assigned can never work. Whether it is usable is the catalog's
    # question, and build_mask answers it (reporting `budget_unavailable` when there are no
    # prices, filtering properly when there are).
    lo, hi = data.get("budget_min"), data.get("budget_max")
    if lo is not None or hi is not None:
        c.budget = BudgetSlot(state=state("budget_max" if hi is not None else "budget_min"),
                              min_price=float(lo) if lo is not None else None,
                              max_price=float(hi) if hi is not None else None,
                              currency=str(data.get("currency") or "TWD"))
        priced = False
        if catalog_items is not None and "price" in getattr(catalog_items, "columns", []):
            import pandas as pd

            priced = bool(pd.to_numeric(catalog_items["price"], errors="coerce").notna().any())
        if not priced:
            unresolved.append(
                f"預算 {lo}–{hi} 這個商品庫無法套用：它沒有價格資料。"
                "其餘條件照常，回應的 constraint_report 會標示 budget_unavailable"
            )

    # ENGINE 03 may send its own FeedbackInput shape (attribute scores + free text) or ours;
    # feedback_from_engine03 passes ours through untouched
    fb, fb_unusable = feedback_from_engine03(feedback, items=catalog_items)
    unresolved += fb_unusable
    for attr, vals in (fb.pop("_excluded_values", None) or {}).items():
        cur = c.excluded_values.setdefault(attr, [])
        cur.extend(v for v in vals if v not in cur)
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

    steps = dict(req.feedback.design_adjust_steps or {})
    for d, v in (req.stated_design_steps or {}).items():   # what the user said in this sentence
        steps[d] = steps.get(d, 0) + v
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
    relaxed = list(resp.constraint_report.relaxed)
    return {"match_score": round(score, 4), "n_items": len(pos), "requirements": reqs,
            # the rate is computed on what SURVIVED the filter, so a relaxed constraint makes a
            # high number misleading unless the screen says what was relaxed
            "relaxed": relaxed,
            "caveat": ("本輪為了湊足結果放寬了條件，滿足率是對放寬後的條件算的：" + "、".join(relaxed))
                      if relaxed else "",
            "definition": ("使用者說出口的要求（硬條件值＋指名的設計要素軸）在這批卡片上被滿足的比例；"
                           "它會下降——加了商品庫給不出來的要求就會掉。這不是「喜歡的機率」。")}


def response_to_retrieval_result(engine, req: Engine02Request, resp: Engine02Response,
                                 *, image_base: str | None = None, arm: str | None = None,
                                 prev_req: Engine02Request | None = None) -> dict:
    """`Engine02Response` → the team's `RetrievalResult` shape, without throwing the evidence away.

    `ProductCard.reason` is a single string, so it gets the card's strongest reason; the full
    additive decomposition travels alongside in `engine02` so the panel that shows "why" still has
    everything, and `concept_image` is left to backend/generation/ (null is a valid answer here).
    """
    import os

    # The frontend runs on another origin (:5173 vs :8002), so a relative /images/<id> resolves
    # against the frontend and 404s. ENGINE02_PUBLIC_BASE makes it absolute for deployment.
    base = image_base if image_base is not None else (
        os.environ.get("ENGINE02_PUBLIC_BASE", "").rstrip("/") + "/images")
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
            # 「可購買」 is a scored criterion, so the price has to reach the card rather than
            # being dropped at this boundary
            if "price" in items.columns:
                import pandas as pd

                v = pd.to_numeric(row.get("price"), errors="coerce")
                if pd.notna(v):
                    cur = str(row.get("currency") or "").strip()
                    attrs["price"] = f"{float(v):.0f}" if float(v) >= 100 else f"{float(v):.2f}"
                    if cur and cur.lower() not in ("nan", "none"):
                        attrs["currency"] = cur
                    if "price_estimated" in items.columns and bool(row.get("price_estimated")):
                        attrs["price_estimated"] = "true"      # show 「估計價」, not a price tag
                        if str(row.get("price_basis") or "").strip():
                            attrs["price_basis"] = str(row["price_basis"])
        products.append({
            "product_id": it.item_id,
            "image_url": f"{base}/{it.item_id}",
            "title": it.title,
            "attributes": attrs,
            "score": round(float(it.score), 4),
            # the full fact-checked sentence, not just its first clause: `explanation` is the
            # template sentence, or the LLM paraphrase that passed the fact check
            "reason": (it.explanation or (it.reasons[0] if it.reasons else "")),
            "reason_contributions": [
                {"term": c.term, "group": c.group, "contribution": round(float(c.contribution), 4),
                 "cited": bool(c.cited)} for c in it.contributions],
            "explanation_source": getattr(it, "explanation_source", None),
        })

    ms = match_score(engine, req, resp, arm=arm)
    if prev_req is not None:
        # Moving goalposts: round N's intent has already been changed by round N-1's feedback, so
        # "new intent vs new slate" can rise purely because the intent got easier. Scoring THIS
        # slate against the PREVIOUS intent is the control, and if only the first number rises we
        # have to say so rather than let the 62% → 89% story tell itself.
        ms["vs_previous_intent"] = match_score(engine, prev_req, resp, arm=arm)["match_score"]
        ms["goalpost_note"] = ("只有『用本輪意圖評』上升、『用上一輪意圖評』沒上升，"
                               "代表分數上升來自意圖變寬鬆，不是結果變好")
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
            # the stylist-voiced reasons arrive later: POST {this service}/explain/rewrite
            # (under /engine02 on the /retrieve services) with this session id
            "rewrite": {"session_id": resp.session_id, "endpoint": "/explain/rewrite"},
        },
    }


# ── ENGINE 03 → ENGINE 02 ─────────────────────────────────────────────────────────────────
# Their declared feedback shape (backend/shared/schemas.py::FeedbackInput) is attribute scores
# plus free text; ours is a ledger of what was shown, chosen and excluded. This converts one to
# the other so round 2 does not need either side to rewrite its contract.

# what the ENGINE 03 `attribute` strings are likely to be, in their words
FEEDBACK_ATTRIBUTE_TO_ELEMENT: dict[str, str] = {
    "顏色": "dark_tone", "色系": "dark_tone", "明度": "dark_tone",
    "版型": "relaxed_fit", "剪裁": "relaxed_fit", "fit": "relaxed_fit",
    "圖案": "bold_pattern", "花紋": "bold_pattern", "pattern": "bold_pattern",
    "領子": "crisp_collar", "collar": "crisp_collar",
    "材質": "soft_knit", "material": "soft_knit",
    "正式感": "formal_style", "風格": "formal_style", "style": "formal_style",
    "logo": "visible_logo", "品牌": "visible_logo",
    "運動": "athletic_style", "機能": "athletic_style",
}


def feedback_from_engine03(payload: dict[str, Any] | None, *, items=None,
                           elements=None, steps: int = 1) -> tuple[dict[str, Any], list[str]]:
    """`FeedbackInput` (theirs) → `FeedbackState` (ours), plus what we could not use.

    An attribute score becomes a step on the matching design axis — one step, not two: a slider
    is a nudge, unlike a sentence the user typed (§3.35). Free text is scanned for negations with
    the same parser the query path uses, so 「不要黑色」 in a feedback box is enforced rather than
    logged. A payload that is already in our shape passes through untouched.
    """
    if not payload:
        return {}, []
    # already ours? (the ledger fields are unmistakable)
    ours = {"choice_history", "chosen_item_ids", "rejected_item_ids", "excluded_item_ids",
            "design_adjust_steps", "design_weight_delta", "anchor_item_ids", "critique",
            "reference_item_id"}
    if set(payload) & ours:
        return dict(payload), []
    if "ops" in payload:
        # ENGINE 03's FeedbackRound. Its ops are the contract we published and
        # engine02/handshake.py implements them exactly; routing them here rather than through
        # apply_round() would silently drop every one of them (see POST /handshake).
        return {}, ["feedback 是 ENGINE 03 的 FeedbackRound（含 ops）："
                    "請改呼叫 POST /handshake 取得下一輪請求，"
                    "或把它先套用後再把 FeedbackState 放進 feedback；本輪不會套用這些 ops"]

    out: dict[str, Any] = {}
    unusable: list[str] = []
    adjust: dict[str, int] = {}
    scores = payload.get("attribute_scores") or []
    # ENGINE 03 documents attribute scores on a 0–1 scale with 0.5 neutral (its own example uses
    # 0.3 to mean 「太正式」), while a signed −1..1 scale is the other obvious reading. Getting this
    # backwards sends the ranking the opposite way with a confident explanation, so infer the
    # convention from the data rather than assuming one.
    signed = any(float(sc.get("score", 0) or 0) < 0 for sc in scores)
    neutral = 0.0 if signed else 0.5
    for sc in scores:
        attr = str(sc.get("attribute", "")).strip()
        try:
            score = float(sc.get("score", 0))
        except (TypeError, ValueError):
            score = neutral
        key = next((v for k, v in FEEDBACK_ATTRIBUTE_TO_ELEMENT.items() if k.lower() in attr.lower()),
                   None)
        if key is None:
            if attr:
                unusable.append(f"attribute_scores 的「{attr}」對不到設計要素軸，本輪忽略")
            continue
        if abs(score - neutral) < 1e-9:       # neutral says nothing; do not invent a direction
            continue
        adjust[key] = adjust.get(key, 0) + (steps if score > neutral else -steps)
    if adjust:
        out["design_adjust_steps"] = adjust

    chosen = payload.get("selected_option_id")
    if chosen:
        out["chosen_item_ids"] = [str(chosen)]

    negations: list[tuple[str, str, str]] = []
    free_text = str(payload.get("free_text") or "").strip()
    if free_text and items is not None:
        from .negation import catalog_vocabulary, expand_color_family, find_negated

        vocab = catalog_vocabulary(items, elements)
        excluded: dict[str, list[str]] = {}
        for attr, value, said in find_negated(free_text, vocab):
            negations.append((attr, value, said))
            if attr == "design_element":
                adjust[value] = adjust.get(value, 0) - steps * 2
                out["design_adjust_steps"] = adjust
            elif attr != "category_id":
                vals = expand_color_family(value, items) if attr == "color" else [value]
                excluded.setdefault(attr, []).extend(v for v in vals if v not in excluded.get(attr, []))
        if excluded:
            out["_excluded_values"] = excluded      # the caller puts this on constraints
    if free_text and items is None:
        unusable.append("free_text 需要商品庫才能解析否定詞（呼叫端未提供 items）")
    return out, unusable
