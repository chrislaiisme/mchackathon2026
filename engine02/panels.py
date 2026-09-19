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
    n_est = sum(1 for it in resp.items if getattr(it, "price_estimated", False))
    if n_est:
        caveats.append(f"{n_est} 件商品的價格是估計價（非實際標價，畫面需標示「估計價」）")
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


# ---------------------------------------------------------------------------
# named facets: the same ranking, read three ways (§3.31)
# ---------------------------------------------------------------------------


class FacetGroup(BaseModel):
    label: str                      # e.g. 「偏正式感」
    n: int
    mean_z: float                   # mean of the axis, in catalog z units
    categories: dict[str, int] = Field(default_factory=dict)
    item_ids: list[str] = Field(default_factory=list)
    examples: list[dict[str, Any]] = Field(default_factory=list)


class FacetPanel(BaseModel):
    """One design axis that splits the result list into named readings.

    Deliberately **not** a reranker. The ranking, the scores and every contribution are exactly
    what /rank returned; this only *reads* the same list along one already-validated axis (§3.3),
    so no retrieval number in this document changes and the panel cannot be wrong about the score.
    """

    axis: str = ""
    axis_label: str = ""
    high_label: str = ""
    low_label: str = ""
    eta_squared: float = 0.0        # how much of the axis' spread the split explains
    corr_with_score: float = 0.0    # |r| with the ranking score: high = the axis just restates it
    category_confound: float = 0.0  # Cramér's V vs category: high = the axis is sorting handbags
                                    # from shirts, not reading the query two ways
    n_pool: int = 0
    groups: list[FacetGroup] = Field(default_factory=list)
    note: str = ""
    considered: list[dict[str, Any]] = Field(default_factory=list)


def _kmeans_1d(x: np.ndarray, k: int, iters: int = 20) -> np.ndarray:
    """Deterministic 1-D k-means. Returns labels ordered by centre (0 = lowest).

    In one dimension a k-means assignment is fully described by the k−1 midpoints between the
    centres, so an iteration is a `searchsorted` on the sorted values plus segment means from a
    prefix sum — no per-point distance matrix. The arrays here are ~50 long and this runs once per
    candidate axis, so numpy call overhead, not arithmetic, is what had to go.
    """
    xs = np.sort(np.asarray(x, dtype=np.float64))
    n = len(xs)
    if k <= 1 or n == 0:
        return np.zeros(len(x), dtype=int)
    csum = np.concatenate([[0.0], np.cumsum(xs)])
    c = xs[(((np.arange(k) + 0.5) / k) * (n - 1)).astype(int)].astype(np.float64)
    prev = None
    for _ in range(iters):
        b = np.searchsorted(xs, (c[:-1] + c[1:]) / 2.0)
        if prev is not None and np.array_equal(b, prev):
            break
        prev = b
        edges = np.concatenate([[0], b, [n]])
        counts = np.diff(edges)
        sums = csum[edges[1:]] - csum[edges[:-1]]
        c = np.sort(np.where(counts > 0, sums / np.maximum(counts, 1), c))
    return np.searchsorted((c[:-1] + c[1:]) / 2.0, np.asarray(x, dtype=np.float64))


def _cramers_v(labels: np.ndarray, groups: Sequence[str]) -> float:
    """Association between the facet split and the item category, on 0..1.

    A design axis can look beautifully separable and be measuring nothing but "handbag vs shirt".
    That is a category listing, not a reading of the query, so it is penalised rather than shown.
    """
    cats = sorted(set(groups))
    if len(cats) < 2 or labels.max() < 1:
        return 0.0
    idx = {c: i for i, c in enumerate(cats)}
    codes = np.fromiter((idx[c] for c in groups), dtype=np.int64, count=len(groups))
    k = int(labels.max()) + 1
    obs = np.bincount(labels.astype(np.int64) * len(cats) + codes,
                      minlength=k * len(cats)).reshape(k, len(cats)).astype(np.float64)
    n = obs.sum()
    if n <= 0:
        return 0.0
    exp = np.outer(obs.sum(1), obs.sum(0)) / n
    chi2 = float(((obs - exp) ** 2 / np.where(exp > 0, exp, 1.0)).sum())
    denom = n * (min(obs.shape) - 1)
    return float(np.sqrt(chi2 / denom)) if denom > 0 else 0.0


def facet_slices(engine, arm, item_ids: Sequence[str], scores: Sequence[float] | None = None,
                 n_groups: int = 3, min_group: int = 2, examples: int = 2) -> FacetPanel:
    """Split a ranked list into named readings along the design axis that separates it best.

    The axis is chosen to be **informative about something the score does not already say**:
    spread inside the result list, times (1 − |correlation with the ranking score|). An axis that
    merely restates the ranking makes a facet that tells the user nothing.

    Measured cost on a 50-item pool, 44k catalog, 15 axes: **2.7 ms** (hash encoder, this machine).
    It is a separate call from /rank, so it does not enter the 12.8 ms ranking budget (§3.21).
    """
    from .config import ARMS

    arm_cfg = ARMS[arm] if isinstance(arm, str) else arm
    ids = [str(i) for i in item_ids]
    pos = [p for p in (engine.catalog.pos(i) for i in ids) if p is not None]
    if len(pos) < n_groups * min_group:
        return FacetPanel(n_pool=len(pos), note="結果太少，不切分面")
    c = engine.design_matrix(arm_cfg)
    elements = engine.kansei.elements
    # antonym partners, so a group can be named by the pole it sits on rather than by "低"
    folded = dict(getattr(engine.kansei, "folded", {}) or {})
    partner = {v: k for k, v in folded.items()}
    label_of = {e.id: e.label for e in elements}

    sub = np.asarray(c[pos], dtype=np.float64)
    # the catalog-wide mean/std do not depend on the query; recomputing them per request cost
    # 10 ms on a 44k catalog, which is most of a /rank (§3.21)
    cache = getattr(engine, "_facet_stats", None)
    if cache is None:
        cache = engine._facet_stats = {}
    key = id(c)
    if key not in cache:
        sd0 = c.std(axis=0)
        keep = cache.get("category_column")
        cache.clear()  # one catalog, one arm at a time; never let this grow
        if keep is not None:
            cache["category_column"] = keep
        cache[key] = (c.mean(axis=0), np.where(sd0 > 1e-9, sd0, 1.0))
    mu, sd = cache[key]
    z = (sub - mu) / sd                                    # catalog z units, the same scale the cards use
    s = np.asarray(scores, dtype=np.float64)[: len(pos)] if scores is not None else None

    # materialising a 44k object column per request cost ~7 ms; the column does not change
    cat_col = cache.get("category_column")
    if cat_col is None:
        col_src = engine.catalog.items["category"] if "category" in engine.catalog.items.columns else None
        cat_col = cache["category_column"] = (col_src.astype(str).to_numpy() if col_src is not None
                                              else np.zeros(len(engine.catalog.items), dtype="<U1"))
    cats = [str(x) for x in cat_col[pos]]

    def split(col: np.ndarray, k: int) -> tuple[np.ndarray, int]:
        """Split into k groups, shrinking k while a group is too small or two groups sit on top
        of each other (k-means centroids collapse on ties, and two groups with the same mean are
        not two readings of anything)."""
        lab = _kmeans_1d(col, k)
        while k > 2:
            means = [col[lab == g].mean() if (lab == g).any() else np.nan for g in range(k)]
            tiny = min(int((lab == g).sum()) for g in range(k)) < min_group
            collapsed = any(abs(means[i + 1] - means[i]) < 0.05 for i in range(k - 1))
            if not (tiny or collapsed):
                break
            k -= 1
            lab = _kmeans_1d(col, k)
        return lab, k

    cand = [(j, e) for j, e in enumerate(elements) if e.id not in folded]
    # every candidate axis is scored against the same pool, so the two per-axis statistics are one
    # vectorised pass instead of 11 tiny numpy calls each (that overhead was the whole cost)
    spreads = z[:, [j for j, _ in cand]].std(axis=0)
    corrs = np.zeros(len(cand))
    if s is not None and s.std() > 1e-9:
        zz = z[:, [j for j, _ in cand]]
        zc = zz - zz.mean(axis=0)
        sc_ = s - s.mean()
        denom = np.sqrt((zc ** 2).sum(axis=0) * (sc_ ** 2).sum())
        corrs = np.abs(np.where(denom > 1e-12, (zc * sc_[:, None]).sum(axis=0) / np.where(denom > 1e-12, denom, 1.0), 0.0))

    # Splitting every axis to score it costs a k-means per axis. Spread and correlation are free
    # (already vectorised above) and bound the gain from above, since confound and balance are both
    # <= 1 — so shortlist on that bound and only split the few axes that could still win.
    order = np.argsort(-(spreads * (1.0 - corrs)))
    shortlist = set(order[:max(3, n_groups)].tolist())

    considered = []
    best = None
    for jj, (j, e) in enumerate(cand):
        if jj not in shortlist:
            continue
        col = z[:, j]
        spread = float(spreads[jj])
        r = float(corrs[jj])
        lab_j, k_j = split(col, n_groups)
        v = _cramers_v(lab_j, cats)
        # A 49/1 split is a single outlier wearing a facet's clothes: perfectly separable and
        # useless to read. Balance is the smallest group against an even share of the pool.
        sizes = [int((lab_j == g).sum()) for g in range(k_j)]
        balance = min(sizes) / (len(pos) / k_j)
        gain = spread * (1.0 - r) * (1.0 - v) * balance
        considered.append({"axis": e.id, "label": e.label, "spread_z": round(spread, 3),
                           "corr_with_score": round(r, 3), "category_confound": round(v, 3),
                           "balance": round(balance, 3), "gain": round(gain, 3)})
        if best is None or gain > best[0]:
            best = (gain, j, e, col, r, v, lab_j, k_j)
    considered.sort(key=lambda d: -d["gain"])
    if best is None:
        return FacetPanel(n_pool=len(pos), note="沒有可用的設計要素軸")

    _, j, e, col, r, v, lab, k = best

    grand = col.mean()
    ss_between = sum(int((lab == g).sum()) * (col[lab == g].mean() - grand) ** 2 for g in range(k))
    ss_total = float(((col - grand) ** 2).sum()) or 1e-9
    high, low = label_of[e.id], label_of.get(partner.get(e.id, ""), f"不強調{e.label}")
    names = ([f"偏{low}", f"偏{high}"] if k == 2 else [f"偏{low}", "中間", f"偏{high}"])

    items = engine.catalog.items
    groups: list[FacetGroup] = []
    for g in range(k):
        idx = [i for i in range(len(pos)) if lab[i] == g]
        idx.sort(key=(lambda i: -float(s[i])) if s is not None else (lambda i: i))
        cat_counts: dict[str, int] = {}
        for i in idx:
            cat_counts[cats[i]] = cat_counts.get(cats[i], 0) + 1
        groups.append(FacetGroup(
            label=names[g], n=len(idx), mean_z=round(float(col[idx].mean()), 3),
            categories=dict(sorted(cat_counts.items(), key=lambda kv: -kv[1])),
            item_ids=[ids[i] for i in idx],
            examples=[{"item_id": ids[i], "title": str(items.at[int(pos[i]), "title"]),
                       "axis_z": round(float(col[i]), 3)} for i in idx[:examples]],
        ))
    return FacetPanel(
        axis=e.id, axis_label=e.label, high_label=high, low_label=low,
        eta_squared=round(float(ss_between / ss_total), 4), corr_with_score=round(r, 3),
        category_confound=round(v, 3),
        n_pool=len(pos), groups=groups, considered=considered[:5],
        note=(f"同一份排序，沿「{e.label}」這條軸讀成 {k} 群；排序、分數與每一項貢獻都沒有改變。"
              f"這條軸與分數的相關性只有 {r:.2f}，所以它講的是分數沒講的事；"
              + (f"但它與品類的關聯度是 {v:.2f}，意思是這個切分有一部分其實是在分品類，請照這個數字打折看待。"
                 if v >= 0.5 else f"與品類的關聯度只有 {v:.2f}，所以它不是在分品類。")),
    )


# ---------------------------------------------------------------------------
# a profile built before the first query (§3.32)
# ---------------------------------------------------------------------------


def profile_questions(engine, arm, n: int = 3, max_corr: float = 0.5) -> list[dict[str, Any]]:
    """n forced choices between two real photographs, one per design axis.

    Axes are taken in order of how much the catalog actually varies along them, skipping any axis
    that correlates above `max_corr` with one already chosen — three questions that all ask the
    same thing measure one thing three times. Each option is a real catalog item at that axis'
    extreme, so the user answers by pointing at a picture rather than by rating an adjective.
    """
    from .config import ARMS

    arm_cfg = ARMS[arm] if isinstance(arm, str) else arm
    c = np.asarray(engine.design_matrix(arm_cfg), dtype=np.float64)
    items = engine.catalog.items
    elements = engine.kansei.elements
    folded = dict(getattr(engine.kansei, "folded", {}) or {})
    partner = {v: k for k, v in folded.items()}
    label_of = {e.id: e.label for e in elements}

    # only clothes can answer a question about how clothes look
    garments = ("top", "tops", "bottom", "bottoms", "dress", "dresses", "outerwear", "apparel")
    if "category" in items.columns:
        cat = items["category"].astype(str).str.lower().to_numpy()
        eligible = np.flatnonzero(np.isin(cat, garments))
    else:
        eligible = np.arange(len(items))

    cand = [j for j, e in enumerate(elements) if e.id not in folded]
    sd = c[:, cand].std(axis=0)
    order = [cand[i] for i in np.argsort(-sd)]
    out: list[dict[str, Any]] = []
    picked: list[int] = []
    for j in order:
        if len(out) >= n:
            break
        if any(abs(float(np.corrcoef(c[:, j], c[:, k])[0, 1])) > max_corr for k in picked):
            continue
        col = c[:, j]
        # The single most extreme item on an axis is usually an artefact — the most "formal" row in
        # a mixed catalog can be a lipstick. Ask with garments only, and use a high percentile
        # rather than the maximum, so the two photos are representative of the poles.
        elig = eligible if eligible.size else np.arange(len(col))
        vals = col[elig]
        lo = int(elig[int(np.argsort(vals)[max(0, int(0.02 * (len(vals) - 1)))])])
        hi = int(elig[int(np.argsort(vals)[min(len(vals) - 1, int(0.98 * (len(vals) - 1)))])])
        if hi == lo or col[hi] - col[lo] < 1e-6:
            continue
        e = elements[j]
        high, low = label_of[e.id], label_of.get(partner.get(e.id, ""), f"不強調{e.label}")

        def card(p: int, side: str, label: str) -> dict[str, Any]:
            return {"side": side, "label": label, "item_id": str(items.at[p, "item_id"]),
                    "title": str(items.at[p, "title"]), "image_path": str(items.at[p, "image_path"]),
                    "axis_z": round(float((col[p] - col.mean()) / (col.std() or 1.0)), 2)}

        out.append({"axis": e.id, "axis_label": e.label, "question": f"這兩件，你比較喜歡哪一件？",
                    "options": [card(lo, "low", low), card(hi, "high", high)]})
        picked.append(j)
    return out


def profile_from_answers(engine, answers: Sequence[dict[str, Any]], kappa0: float = 3.0) -> dict[str, Any]:
    """Forced choices → a prior over design axes, in user-feedback steps.

    One binary answer is at most one bit and there are 11 axes, so three answers cannot even fix
    the sign of half of them. That is the point: this is a prior mean with a bounded equivalent
    sample size (`kappa0`), never a conclusion about the person.
    """
    ids = set(engine.kansei.element_ids)
    weights: dict[str, float] = {}
    used = 0
    for a in answers:
        axis = str(a.get("axis", ""))
        side = str(a.get("side", "")).lower()
        if axis not in ids or side not in ("high", "low"):
            continue
        weights[axis] = weights.get(axis, 0.0) + (1.0 if side == "high" else -1.0)
        used += 1
    return {"weights": weights, "n_answers": used, "kappa0": float(kappa0),
            "note": ("這是先驗平均，不是結論：等效樣本數上限 "
                     f"{kappa0:.0f} 輪，第 {kappa0:.0f} 輪之後你的實際回饋一定壓過它。"
                     "卡片上會標成「你開場挑的偏好」，與你本輪打的字分開列。")}
