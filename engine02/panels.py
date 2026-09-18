"""Response **extension** for the PRD §7 screens — built on top of `Engine02Response`.

`Engine02Response` already carries every number the screens need (contributions, need_shares,
design_scores, constraint_report, metrics, diversification). What it does **not** carry is the
few aggregations and cross-round comparisons the PRD asks the UI to show, which the frontend
would otherwise have to re-derive (and could get subtly wrong — e.g. summing need shares over
cards, or diffing two rounds):

=========================== ================================================================
PRD §5 / §7 block           what this module adds
=========================== ================================================================
「你說的 vs 你沒說的」卡      :class:`StatedVsUnstated` — the four slot states split out, plus the
                            needs that are moving the ranking although the user never said them,
                            with the design element each one acts through.
帳本 / 需求面板              :class:`NeedPanel` — per need: p(n), its share of the slate's score,
                            the elements it acts through, and which cards it supports.
兩輪並排＋「改了什麼」        :class:`RoundDiff` — kept / new / dropped items, rank moves, the
                            constraint and feedback diff, the three §7 rule metrics before/after,
                            and per-card reason changes.
放寬／資料來源標示            :class:`Provenance` — relaxation ladder, model-filled attributes,
                            price availability, template-vs-LLM explanation counts, DPP promotions.
設計師看板（M13 供給側）      :func:`need_supply` — Sup(n), the share of the catalog that can serve
                            need n at all; the demand side is ENGINE 03's to aggregate.
生成分支「最接近的 3 件」      :func:`concept_image_neighbors` — PRD §6.5 接回推薦.
=========================== ================================================================

Nothing here re-scores or re-orders anything: every field is a projection of the response that
was already returned, so the explanation stays faithful. :func:`build_view` is pure Python on
the Pydantic models and needs no engine, so the frontend can call it (or the API can wrap it)
without loading the catalog; the two engine-backed helpers at the bottom are separate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np
from pydantic import BaseModel, Field

from .contracts import (
    CONTRACT_VERSION,
    Engine02Request,
    Engine02Response,
    RankedItem,
    SlotState,
)

SLOT_NAMES = ("category", "color", "occasion", "season", "gender", "style_keywords")
# what the filter actually enforces (engine02.constraints.SLOT_COLUMNS). `style_keywords` only
# reaches the retrieval text, and `budget` is dead while the catalog has no prices — the screen
# must not imply they were filtered on.
HARD_FILTER_SLOTS = ("category", "color", "occasion", "season", "gender")
SLOT_LABEL = {"category": "品類", "color": "顏色", "occasion": "場合", "season": "季節",
              "gender": "性別", "style_keywords": "風格關鍵字", "budget": "預算"}


# ---------------------------------------------------------------------------
# 你說的 vs 你沒說的
# ---------------------------------------------------------------------------
class NeedDriver(BaseModel):
    need_id: str
    label: str | None = None
    prob: float
    contribution: float  # Σ over the shown cards of p(n)·K[n,d]·c(i,d)
    share_of_positive: float  # this need's share of all positive contributions on the slate
    top_elements: list[dict[str, Any]] = Field(default_factory=list)  # [{element, label, contribution}]
    supports_items: list[str] = Field(default_factory=list)


class StatedVsUnstated(BaseModel):
    """PRD §5「你說的 vs 你沒說的」. The *said* side is the slot states ENGINE 01 sent;
    the *unsaid* side is the needs that actually moved this slate."""

    stated: dict[str, list[str]] = Field(default_factory=dict)  # state == value → hard filter
    inferred: dict[str, list[str]] = Field(default_factory=dict)  # state == inferred → soft only
    dont_care: list[str] = Field(default_factory=list)
    unmentioned: list[str] = Field(default_factory=list)
    excluded_values: dict[str, list[str]] = Field(default_factory=dict)
    required_values: dict[str, list[str]] = Field(default_factory=dict)
    # stated slots that ENGINE 02 does NOT enforce as a hard filter (style keywords only steer the
    # retrieval text; budget is inert while the catalog has no prices)
    soft_only: list[str] = Field(default_factory=list)
    utterances: list[str] = Field(default_factory=list)
    unstated_drivers: list[NeedDriver] = Field(default_factory=list)
    feedback_driven: float = 0.0  # contribution that comes from ENGINE 03 feedback, not from p(n)
    sentence: str = ""


def _element_phrase(label: str, k_sign: float, contribution: float) -> dict[str, str]:
    """Card wording for one (need, design element) pair.

    A need can be served either by *having* an element (K > 0) or by *avoiding* it (K < 0), and the
    contribution can be positive or negative. Writing 「明顯 logo」 when the reason is in fact
    "this item has no logo, and you don't want one" reads as the opposite of the truth, so the
    direction is always spelled out (docs/engine02-design.md §4.3).
    """
    wanted = "avoid" if k_sign < 0 else "want"
    if contribution >= 0:  # the item is on the right side of this axis
        phrase = f"避開{label}" if wanted == "avoid" else label
    else:  # it is on the wrong side — say so instead of dressing it up
        phrase = f"有{label}（扣分）" if wanted == "avoid" else f"缺少{label}（扣分）"
    return {"direction": "avoids" if wanted == "avoid" else "has", "phrase": phrase}


def _need_labels(resp: Engine02Response, need_labels: dict[str, str] | None) -> dict[str, str]:
    out = dict(need_labels or {})
    out.setdefault("feedback_adjust", "你上一輪的回饋")
    return out


@dataclass
class _Aggregate:
    per_need: dict[str, float]
    per_element: dict[str, dict[str, float]]
    # sign of K[n,d] recovered from the response alone: need_share = p(n)·K[n,d]·c(i,d) and
    # `normalized` is c(i,d), so sign(share/normalized) = sign(K) (p(n) ≥ 0). Needed because the
    # card text must say 「避開〇〇」 for a negative element, never 「〇〇」 (design doc §4.3).
    element_sign: dict[str, dict[str, float]]
    supports: dict[str, list[str]]
    total_pos: float


def _aggregate_needs(items: Sequence[RankedItem]) -> _Aggregate:
    per_need: dict[str, float] = {}
    per_element: dict[str, dict[str, float]] = {}
    element_sign: dict[str, dict[str, float]] = {}
    supports: dict[str, list[str]] = {}
    total_pos = 0.0
    for it in items:
        for cb in it.contributions:
            if cb.contribution > 0:
                total_pos += cb.contribution
            if cb.group != "design":
                continue
            el = cb.term.split(":", 1)[1] if ":" in cb.term else cb.term
            for n, v in cb.need_shares.items():
                per_need[n] = per_need.get(n, 0.0) + v
                per_element.setdefault(n, {})
                per_element[n][el] = per_element[n].get(el, 0.0) + v
                if abs(cb.normalized) > 1e-12:
                    s = element_sign.setdefault(n, {})
                    s[el] = s.get(el, 0.0) + v / cb.normalized
                if v > 0 and it.item_id not in supports.setdefault(n, []):
                    supports[n].append(it.item_id)
    return _Aggregate(per_need, per_element, element_sign, supports, total_pos)


def stated_vs_unstated(req: Engine02Request, resp: Engine02Response,
                       need_labels: dict[str, str] | None = None,
                       element_labels: dict[str, str] | None = None,
                       top_n: int = 3) -> StatedVsUnstated:
    c = req.constraints
    stated, inferred, dont_care, unmentioned = {}, {}, [], []
    for name in SLOT_NAMES:
        slot = getattr(c, name)
        if slot.state == SlotState.VALUE and slot.values:
            stated[name] = list(slot.values)
        elif slot.state == SlotState.INFERRED and slot.values:
            inferred[name] = list(slot.values)
        elif slot.state == SlotState.DONT_CARE:
            dont_care.append(name)
        else:
            unmentioned.append(name)
    if c.budget.state == SlotState.VALUE:
        stated["budget"] = [f"<= {c.budget.max_price}"] if c.budget.max_price is not None else ["set"]
    elif c.budget.state == SlotState.DONT_CARE:
        dont_care.append("budget")
    else:
        unmentioned.append("budget")

    nl = _need_labels(resp, need_labels)
    el = dict(element_labels or {})
    agg = _aggregate_needs(resp.items)
    total_pos = agg.total_pos
    probs = {n.need_id: n.prob for n in req.needs}
    labels_from_req = {n.need_id: n.label for n in req.needs if n.label}
    drivers: list[NeedDriver] = []
    for n, v in sorted(agg.per_need.items(), key=lambda kv: -abs(kv[1])):
        if n == "feedback_adjust":
            continue
        elements = sorted(agg.per_element.get(n, {}).items(), key=lambda kv: -abs(kv[1]))[:top_n]
        signs = agg.element_sign.get(n, {})
        drivers.append(NeedDriver(
            need_id=n, label=labels_from_req.get(n) or nl.get(n), prob=probs.get(n, 0.0),
            contribution=round(v, 4),
            share_of_positive=round(v / total_pos, 4) if total_pos > 0 else 0.0,
            top_elements=[{"element": d, "label": el.get(d, d), "contribution": round(w, 4),
                           **_element_phrase(el.get(d, d), signs.get(d, 0.0), w)}
                          for d, w in elements],
            supports_items=agg.supports.get(n, []),
        ))
    said = "、".join(f"{SLOT_LABEL.get(k, k)}＝{'/'.join(map(str, v))}" for k, v in stated.items())
    top = [d for d in drivers if d.contribution > 0][:2]
    unsaid = "、".join(
        f"「{d.label or d.need_id}」（+{d.contribution:.2f}"
        + (f"，主要靠{d.top_elements[0]['phrase']}" if d.top_elements else "") + "）"
        for d in top
    )
    sentence = ""
    if said or unsaid:
        sentence = (f"你說的是{said or '（沒有明確硬條件）'}；"
                    f"你沒說、但真正在推薦裡加分的是{unsaid or '（本輪沒有需求項加分）'}。")
    return StatedVsUnstated(
        stated=stated, inferred=inferred, dont_care=dont_care, unmentioned=unmentioned,
        excluded_values=dict(c.excluded_values), required_values=dict(c.required_values),
        soft_only=[k for k in (*stated, *inferred) if k not in HARD_FILTER_SLOTS]
        + (["budget"] if "budget" in stated and all(it.price is None for it in resp.items) else []),
        utterances=list(req.utterances), unstated_drivers=drivers,
        feedback_driven=round(agg.per_need.get("feedback_adjust", 0.0), 4), sentence=sentence,
    )


# ---------------------------------------------------------------------------
# per-need panel
# ---------------------------------------------------------------------------
class NeedPanel(BaseModel):
    needs: list[NeedDriver] = Field(default_factory=list)
    total_positive_contribution: float = 0.0
    design_share_of_positive: float = 0.0  # how much of the slate's score the Kansei terms explain
    feedback_share_of_positive: float = 0.0
    # needs the user has but that no shown card serves (gap candidates for the designer board)
    unserved_needs: list[str] = Field(default_factory=list)


def need_panel(req: Engine02Request, resp: Engine02Response, need_labels: dict[str, str] | None = None,
               element_labels: dict[str, str] | None = None) -> NeedPanel:
    svu = stated_vs_unstated(req, resp, need_labels, element_labels)
    agg = _aggregate_needs(resp.items)
    total_pos = agg.total_pos
    design_pos = sum(cb.contribution for it in resp.items for cb in it.contributions
                     if cb.group == "design" and cb.contribution > 0)
    served = {d.need_id for d in svu.unstated_drivers if d.contribution > 0}
    return NeedPanel(
        needs=svu.unstated_drivers,
        total_positive_contribution=round(total_pos, 4),
        design_share_of_positive=round(design_pos / total_pos, 4) if total_pos > 0 else 0.0,
        feedback_share_of_positive=round(max(agg.per_need.get("feedback_adjust", 0.0), 0.0) / total_pos, 4)
        if total_pos > 0 else 0.0,
        unserved_needs=[n.need_id for n in req.needs if n.prob > 0 and n.need_id not in served],
    )


# ---------------------------------------------------------------------------
# two rounds side by side
# ---------------------------------------------------------------------------
class ItemMove(BaseModel):
    item_id: str
    prev_rank: int | None = None
    rank: int | None = None
    delta: int | None = None  # prev_rank - rank (positive = moved up)
    score_delta: float | None = None
    reasons_added: list[str] = Field(default_factory=list)
    reasons_removed: list[str] = Field(default_factory=list)


class RoundDiff(BaseModel):
    """PRD §5「第二輪：與第一輪並排，標出改了什麼＋前後指標」."""

    prev_round: int
    round: int
    kept: list[ItemMove] = Field(default_factory=list)
    new_items: list[str] = Field(default_factory=list)
    dropped_items: list[str] = Field(default_factory=list)
    turnover: float = 0.0  # share of the slate that changed
    constraints_added: dict[str, list[str]] = Field(default_factory=dict)
    constraints_removed: dict[str, list[str]] = Field(default_factory=dict)
    excluded_added: dict[str, list[str]] = Field(default_factory=dict)
    required_added: dict[str, list[str]] = Field(default_factory=dict)
    design_adjust_delta: dict[str, int] = Field(default_factory=dict)
    needs_delta: dict[str, float] = Field(default_factory=dict)
    relaxed_added: list[str] = Field(default_factory=list)
    relaxed_removed: list[str] = Field(default_factory=list)
    # the PRD §7 rule metrics, before → after (never the ranking score itself); the values are
    # numbers plus RoundMetrics.match_policy, which says how the rule check compared values
    metrics_before: dict[str, float | int | str | None] = Field(default_factory=dict)
    metrics_after: dict[str, float | int | str | None] = Field(default_factory=dict)


def _cited(it: RankedItem) -> list[str]:
    return [cb.term for cb in it.contributions if cb.cited]


def _slot_map(req: Engine02Request) -> dict[str, list[str]]:
    out = {}
    for name in HARD_FILTER_SLOTS:
        slot = getattr(req.constraints, name)
        if slot.is_hard() and slot.values:
            out[name] = sorted(str(v) for v in slot.values)
    return out


def _dict_diff(new: dict[str, list[str]], old: dict[str, list[str]]) -> dict[str, list[str]]:
    out = {}
    for k, v in new.items():
        added = sorted(set(v) - set(old.get(k, [])))
        if added:
            out[k] = added
    return out


def round_diff(prev_req: Engine02Request, prev_resp: Engine02Response,
               req: Engine02Request, resp: Engine02Response) -> RoundDiff:
    prev_rank = {it.item_id: it.rank for it in prev_resp.items}
    prev_score = {it.item_id: it.score for it in prev_resp.items}
    prev_cited = {it.item_id: set(_cited(it)) for it in prev_resp.items}
    now = {it.item_id: it for it in resp.items}
    kept = []
    for it in resp.items:
        if it.item_id not in prev_rank:
            continue
        added = sorted(set(_cited(it)) - prev_cited[it.item_id])
        removed = sorted(prev_cited[it.item_id] - set(_cited(it)))
        kept.append(ItemMove(item_id=it.item_id, prev_rank=prev_rank[it.item_id], rank=it.rank,
                             delta=prev_rank[it.item_id] - it.rank,
                             score_delta=round(it.score - prev_score[it.item_id], 4),
                             reasons_added=added, reasons_removed=removed))
    new_items = [i for i in now if i not in prev_rank]
    dropped = [i for i in prev_rank if i not in now]
    pv, nv = _slot_map(prev_req), _slot_map(req)
    pn = {n.need_id: n.prob for n in prev_req.needs}
    nn = {n.need_id: n.prob for n in req.needs}
    pa, na = prev_req.feedback.design_adjust_steps, req.feedback.design_adjust_steps
    return RoundDiff(
        prev_round=prev_resp.round, round=resp.round,
        kept=kept, new_items=new_items, dropped_items=dropped,
        turnover=round(len(new_items) / max(1, len(resp.items)), 4),
        constraints_added=_dict_diff(nv, pv), constraints_removed=_dict_diff(pv, nv),
        excluded_added=_dict_diff(req.constraints.excluded_values, prev_req.constraints.excluded_values),
        required_added=_dict_diff(req.constraints.required_values, prev_req.constraints.required_values),
        design_adjust_delta={d: na.get(d, 0) - pa.get(d, 0) for d in set(na) | set(pa)
                             if na.get(d, 0) != pa.get(d, 0)},
        needs_delta={n: round(nn.get(n, 0.0) - pn.get(n, 0.0), 4) for n in set(nn) | set(pn)
                     if abs(nn.get(n, 0.0) - pn.get(n, 0.0)) > 1e-9},
        relaxed_added=[r for r in resp.constraint_report.relaxed if r not in prev_resp.constraint_report.relaxed],
        relaxed_removed=[r for r in prev_resp.constraint_report.relaxed if r not in resp.constraint_report.relaxed],
        metrics_before=prev_resp.metrics.model_dump(), metrics_after=resp.metrics.model_dump(),
    )


# ---------------------------------------------------------------------------
# provenance / honesty panel
# ---------------------------------------------------------------------------
class Provenance(BaseModel):
    arm: str
    encoder: str
    kansei_version: str
    contract_version: str = CONTRACT_VERSION
    n_catalog: int = 0
    n_after_filter: int = 0
    applied_constraints: dict[str, list[str]] = Field(default_factory=dict)
    relaxed: list[str] = Field(default_factory=list)
    relaxed_human: list[str] = Field(default_factory=list)
    model_filled_attributes: dict[str, list[str]] = Field(default_factory=dict)  # item_id → notes
    price_available: bool = False
    explanation_sources: dict[str, int] = Field(default_factory=dict)
    reason_modes: dict[str, int] = Field(default_factory=dict)
    diversification: dict[str, Any] = Field(default_factory=dict)
    timings_ms: dict[str, float] = Field(default_factory=dict)
    caveats: list[str] = Field(default_factory=list)


def provenance(resp: Engine02Response) -> Provenance:
    notes = {it.item_id: list(it.attribute_notes) for it in resp.items if it.attribute_notes}
    srcs: dict[str, int] = {}
    modes: dict[str, int] = {}
    for it in resp.items:
        srcs[it.explanation_source] = srcs.get(it.explanation_source, 0) + 1
        modes[it.reason_mode] = modes.get(it.reason_mode, 0) + 1
    price_ok = any(it.price is not None for it in resp.items)
    caveats = []
    if not price_ok:
        caveats.append("商品庫無價格資料，預算條件不做過濾（畫面需標示）")
    if notes:
        caveats.append("部分硬條件屬性由模型判讀（見卡片註記），非資料集原值")
    if resp.constraint_report.relaxed:
        caveats.append("為了湊滿結果放寬了條件，滿足率照實計入")
    return Provenance(
        arm=resp.arm, encoder=resp.encoder, kansei_version=resp.kansei_version,
        contract_version=resp.contract_version,
        n_catalog=resp.constraint_report.n_catalog, n_after_filter=resp.constraint_report.n_after_filter,
        applied_constraints=dict(resp.constraint_report.applied),
        relaxed=list(resp.constraint_report.relaxed),
        relaxed_human=[f"放寬了「{r.split(':')[0]}」（{r}）" for r in resp.constraint_report.relaxed],
        model_filled_attributes=notes, price_available=price_ok,
        explanation_sources=srcs, reason_modes=modes,
        diversification=dict(getattr(resp, "diversification", {}) or {}),
        timings_ms=dict(resp.timings_ms), caveats=caveats,
    )


# ---------------------------------------------------------------------------
class SlateDiversity(BaseModel):
    """PRD §9.3 Div@5「前 5 名涵蓋的設計要素類別（版型／色系）」, computed from item attributes by
    rule — never from the ranking score, like the other §7 metrics.

    `engine02/diversify.py` reports ILD / near-duplicate rate / α-NDCG, which are better
    diversity *research* metrics but are not the number the PRD promises on screen.
    """

    k: int = 0
    distinct_categories: int = 0
    distinct_colors: int = 0
    div_at_k: float = 0.0  # mean of the two coverages, each normalised by k
    categories: dict[str, int] = Field(default_factory=dict)
    colors: dict[str, int] = Field(default_factory=dict)
    promoted_by_diversity: list[str] = Field(default_factory=list)


def slate_diversity(resp: Engine02Response, k: int | None = None) -> SlateDiversity:
    items = list(resp.items)[: k or len(resp.items)]
    n = len(items)
    cats: dict[str, int] = {}
    cols: dict[str, int] = {}
    for it in items:
        c = str(it.category) if it.category else "(未分類)"
        cl = str(it.color) if it.color else "(無顏色資料)"
        cats[c] = cats.get(c, 0) + 1
        cols[cl] = cols.get(cl, 0) + 1
    cov = ((len(cats) + len(cols)) / (2 * n)) if n else 0.0
    return SlateDiversity(
        k=n, distinct_categories=len(cats), distinct_colors=len(cols), div_at_k=round(cov, 4),
        categories=cats, colors=cols,
        promoted_by_diversity=[it.item_id for it in items if getattr(it, "promoted_by_diversity", False)],
    )


class Engine02View(BaseModel):
    """Everything the PRD §7 screens need, derived from one (or two) responses."""

    session_id: str
    round: int
    said_vs_unsaid: StatedVsUnstated
    needs: NeedPanel
    diversity: SlateDiversity
    provenance: Provenance
    round_diff: RoundDiff | None = None


def build_view(req: Engine02Request, resp: Engine02Response,
               prev_req: Engine02Request | None = None, prev_resp: Engine02Response | None = None,
               need_labels: dict[str, str] | None = None,
               element_labels: dict[str, str] | None = None) -> Engine02View:
    diff = round_diff(prev_req, prev_resp, req, resp) if (prev_req and prev_resp) else None
    return Engine02View(
        session_id=resp.session_id, round=resp.round,
        said_vs_unsaid=stated_vs_unstated(req, resp, need_labels, element_labels),
        needs=need_panel(req, resp, need_labels, element_labels),
        diversity=slate_diversity(resp, req.options.top_k),
        provenance=provenance(resp), round_diff=diff,
    )


def view_labels(engine) -> dict[str, dict[str, str]]:
    """Label dictionaries for :func:`build_view` (same content as ``GET /kansei``)."""
    return {"need_labels": dict(engine.kansei.needs),
            "element_labels": {e.id: e.label for e in engine.kansei.elements}}


# ---------------------------------------------------------------------------
# engine-backed helpers (need the catalog)
# ---------------------------------------------------------------------------
def need_supply(engine, arm: str | Any = "full", threshold: float = 0.5,
                mask: np.ndarray | None = None) -> dict[str, float]:
    """PRD §6.7 supply side: Sup(n) = share of catalog items with Σ_d K[n,d]·c(i,d) > threshold.

    ENGINE 03 owns the demand side D(場合, n) = Σ_sessions p(n) and the Gap product; this is the
    half that only ENGINE 02 can compute (it needs c(i,d)). c(i,d) is catalog-z-scored, so the
    threshold is in units of "how strongly, relative to this catalog, the item expresses the need".
    """
    from .config import ARMS

    cfg = ARMS[arm] if isinstance(arm, str) else arm
    c = engine.design_matrix(cfg)  # (n_items, n_elements)
    if mask is not None:
        c = c[np.asarray(mask, dtype=bool)]
    if not len(c):
        return {n: 0.0 for n in engine.kansei.need_ids}
    s = c @ engine.kansei.K.T  # (n_items, n_needs)
    return {n: float((s[:, i] > threshold).mean()) for i, n in enumerate(engine.kansei.need_ids)}


class ElementGap(BaseModel):
    """One design element: how much the demand side asked for it vs how much of the catalog has it."""

    element: str
    label: str
    demand: float          # Σ over sessions of β_d, positive and negative kept apart
    demand_share: float    # demand / Σ|demand| over elements, so the scale is readable
    direction: str         # "wanted" (β>0) or "avoided" (β<0)
    supply: float          # share of the catalog expressing the element above the threshold
    gap: float             # |demand_share| · (1 − supply) for wanted, · supply for avoided
    n_items_above: int


class GapReport(BaseModel):
    """PRD §6.7 gap map at design-element level — what a garment maker can act on.

    The demand side is **the queries this server has actually served** (ENGINE 03 owns the real
    aggregation across sessions), so every reading of this panel must state its denominator:
    `n_sessions` is exactly the number of requests behind the numbers, not a market measurement.
    """

    n_sessions: int
    threshold: float
    arm: str
    elements: list[ElementGap] = Field(default_factory=list)
    note: str = "需求側 = 本服務實際收到的查詢，不是市場量測"


def element_gap(engine, sessions: Sequence[tuple[dict[str, float], dict[str, int]]],
                arm: str | Any = "full", threshold: float = 0.5,
                element_labels: dict[str, str] | None = None,
                mask: np.ndarray | None = None) -> GapReport:
    """Demand (β_d aggregated over sessions) against supply (share of catalog with c(i,d) > τ).

    Positive and negative demand are **not** summed together: "everyone wants a crisp collar" and
    "everyone wants to avoid a crisp collar" are different findings, and averaging them into ~0
    would hide both. A wanted element with low supply is an opening; an avoided element with high
    supply is an over-supply the catalog should trim.
    """
    from .config import ARMS

    cfg = ARMS[arm] if isinstance(arm, str) else arm
    labels = element_labels or {e.id: e.label for e in engine.kansei.elements}
    ids = engine.kansei.element_ids
    demand = np.zeros(len(ids))
    for probs, steps in sessions:
        needs_beta, fb_beta = engine.kansei.beta(probs or {}, steps or {})
        demand += needs_beta + fb_beta
    total = float(np.abs(demand).sum())

    c = engine.design_matrix(cfg)
    if mask is not None:  # supply measured on a subset (used by scripts/eval_gap.py)
        c = c[np.asarray(mask, dtype=bool)]
    above = (c > threshold)
    rows = []
    for j, d in enumerate(ids):
        if abs(demand[j]) < 1e-9:
            continue
        share = float(demand[j] / total) if total else 0.0
        supply = float(above[:, j].mean())
        wanted = demand[j] > 0
        rows.append(ElementGap(
            element=d, label=labels.get(d, d), demand=float(demand[j]), demand_share=share,
            direction="wanted" if wanted else "avoided",
            supply=supply, gap=abs(share) * ((1 - supply) if wanted else supply),
            n_items_above=int(above[:, j].sum())))
    rows.sort(key=lambda r: -r.gap)
    return GapReport(n_sessions=len(sessions), threshold=threshold, arm=cfg.name, elements=rows)


class CellGap(BaseModel):
    category: str
    color: str
    requests: int          # how many served queries asked for this cell
    catalog_items: int     # how many catalog items are in it
    items_per_request: float
    gap: float             # requests / (1 + catalog_items), the colourway-level degenerate case


def category_color_gap(engine, cells: Sequence[tuple[str | None, str | None]],
                       top: int = 20) -> list[CellGap]:
    """Requested (category, colour) cells against how many items the catalog has there.

    This is the crudest possible colourway view, and it is the one a manufacturer reads first:
    "they keep asking for navy outerwear and we have four of them".
    """
    from collections import Counter

    items = engine.catalog.items
    counts = Counter((str(a).lower(), str(b).lower()) for a, b in cells if a and b)
    cat_col = items["category"].astype(str).str.lower()
    col_col = items["color"].astype(str).str.lower() if "color" in items.columns else None
    out = []
    for (cat, col), n in counts.most_common():
        have = int(((cat_col == cat) & (col_col == col)).sum()) if col_col is not None else 0
        out.append(CellGap(category=cat, color=col, requests=n, catalog_items=have,
                           items_per_request=round(have / n, 2), gap=round(n / (1 + have), 4)))
    out.sort(key=lambda r: -r.gap)
    return out[:top]


def concept_image_neighbors(engine, embedding: Sequence[float], k: int = 3,
                            mask: np.ndarray | None = None) -> list[dict[str, Any]]:
    """PRD §6.5 接回推薦: the k catalog items closest to a generated concept image.

    Display-only — it deliberately does **not** go through the reranker, so a generated image can
    never be presented as if it had caused a ranked recommendation. For actually folding a concept
    image into retrieval, see ``FeedbackState.concept_image_embedding`` plus
    ``ArmConfig.concept_image_weight`` (default 0; measured in scripts/eval_concept_image.py).
    """
    from .encoders import l2n

    q = l2n(np.asarray(embedding, dtype=np.float64))
    sims = np.asarray(engine.image_emb, dtype=np.float64) @ q
    idx = np.arange(len(sims)) if mask is None else np.flatnonzero(np.asarray(mask, dtype=bool))
    order = idx[np.argsort(-sims[idx], kind="stable")[:k]]
    items = engine.catalog.items
    return [{"item_id": str(items.at[int(p), "item_id"]), "title": str(items.at[int(p), "title"]),
             "image_path": str(items.at[int(p), "image_path"]), "cosine": round(float(sims[int(p)]), 4),
             "source": "concept_image_nearest"} for p in order]
