"""ENGINE 03 ↔ ENGINE 02 handshake: reference implementation of one feedback round.

ENGINE 03's job (PRD M8) is to turn a free-text reply plus clicks into a **closed set of
operations**; ENGINE 02's job is to apply them deterministically so that the same feedback always
produces the same next request.  That mapping was described in prose in
`docs/engine02-design.md` §4.2 but never implemented, so each engine owner would have written
their own — and the first mismatch would only show up during the demo.  This module is the single
implementation both sides can call, plus the rules that are easy to get wrong:

1. **Never send weight numbers.**  `adjust(element, ±1)` sends *steps*; ENGINE 02 multiplies by
   `KanseiTable.step_size` (0.25) and clips to ±`max_steps` (3).  Steps accumulate across rounds,
   the clip is applied to the accumulated total, and the ledger records both.
2. **`exclude` is permanent.**  It goes to `constraints.excluded_values`, which the relaxation
   ladder never touches, and the excluded value is also removed from the positive slot so the
   query text stops asking for it.
3. **A critique target is a `required_value`, not a relaxable slot value** — the ladder silently
   dropped 46% of colour critiques before that existed (docs/research/recsys-composed.md).
4. **`reference_item_id` / `critique` are single-round.**  They describe "this one, but …" about a
   card that was just shown, so they are cleared before the next round unless restated; the
   *effect* survives as a `required_value`.
5. **Choices accumulate as history, not as weights.**  Every round appends a `ChoiceRecord`
   (what was shown, what was picked, what was rejected); `Engine02Service` fits the Bayesian
   pairwise-logistic posterior (T7) and shrinks it by n/(n+1) (T7b).  ENGINE 03 must *not*
   pre-compute `design_weight_delta` unless it wants to override that.
6. **Choice likelihoods use the returned `design_scores`.**  `S(i|n) = Σ_d K[n,d]·c(i,d)` —
   `need_likelihood` here uses the card's own `design_scores`, never a recomputed c(i,d).
7. **Need probabilities are ENGINE 01/03's**, updated by PRD formula ④
   (`log p(n) += λ·log L(e|n)`, then renormalise); :func:`update_needs` is that formula so both
   engines use the same one, and the ledger shows the before/after per need.

`FeedbackRound.ops` is exactly the PRD M8 output schema, so ENGINE 03's structured-output
`json_schema` can be generated from it (`FeedbackRound.model_json_schema()`).
"""

from __future__ import annotations

import json
import math
from typing import Annotated, Any, Literal, Sequence

from pydantic import BaseModel, Field

from .contracts import (
    ChoiceRecord,
    Critique,
    Engine02Request,
    Engine02Response,
    NeedProbability,
    RankedItem,
    Slot,
    SlotState,
)

# attributes ENGINE 03 may constrain; must be catalog columns (see GET /vocabulary)
ATTRIBUTES = ("category", "subcategory", "color", "occasion", "season", "gender")
SLOT_ATTRIBUTES = ("category", "color", "occasion", "season", "gender")


# ---------------------------------------------------------------------------
# PRD M8 operation set (the only thing the LLM is allowed to output)
# ---------------------------------------------------------------------------
class ExcludeOp(BaseModel):
    op: Literal["exclude"] = "exclude"
    attribute: Literal["category", "subcategory", "color", "occasion", "season", "gender"]
    value: str
    quote: str | None = None  # the user words this came from (for the ledger)


class RequireOp(BaseModel):
    op: Literal["require"] = "require"
    attribute: Literal["category", "subcategory", "color", "occasion", "season", "gender"]
    value: str
    quote: str | None = None


class AdjustOp(BaseModel):
    """adjust(設計要素, +1/−1) — one step at a time, no weight numbers."""

    op: Literal["adjust"] = "adjust"
    element: str  # a design-element id from GET /kansei
    step: Literal[-1, 1] = 1
    quote: str | None = None


class ChoiceOp(BaseModel):
    op: Literal["choice"] = "choice"
    shown_item_ids: list[str] = Field(default_factory=list)
    chosen_item_id: str | None = None
    rejected_item_ids: list[str] = Field(default_factory=list)


class FeelingOp(BaseModel):
    """feeling(原句) — ENGINE 03 supplies either the updated p(n) or the log-likelihoods of
    PRD formula ④; ENGINE 02 never invents need probabilities itself."""

    op: Literal["feeling"] = "feeling"
    quote: str
    need_log_likelihood: dict[str, float] = Field(default_factory=dict)  # log L(e|n)
    lam: float = 1.0  # λ_e
    needs_override: list[NeedProbability] | None = None


class CritiqueOp(BaseModel):
    """「這件但換成 X」 on a shown card (composed retrieval)."""

    op: Literal["critique"] = "critique"
    reference_item_id: str
    attribute: Literal["color", "occasion", "category", "subcategory", "season"] | None = None
    to_value: str | None = None
    direction: Literal["more_formal", "more_casual", "sportier"] | None = None
    quote: str | None = None


class AnchorOp(BaseModel):
    """「要搭我的這件」 — the only thing that switches the compatibility term on."""

    op: Literal["anchor"] = "anchor"
    item_ids: list[str] = Field(default_factory=list)
    replace: bool = False


class ExcludeItemOp(BaseModel):
    op: Literal["exclude_item"] = "exclude_item"
    item_ids: list[str] = Field(default_factory=list)


Op = Annotated[
    ExcludeOp | RequireOp | AdjustOp | ChoiceOp | FeelingOp | CritiqueOp | AnchorOp | ExcludeItemOp,
    Field(discriminator="op"),
]


class FeedbackRound(BaseModel):
    """One round of ENGINE 03 output. `FeedbackRound.model_json_schema()` is the structured-output
    schema for M8; the LLM cannot emit anything outside this set."""

    session_id: str
    round: int  # the round the feedback is *about* (the round whose cards were shown)
    utterance: str | None = None
    ops: list[Op] = Field(default_factory=list)


class LedgerEntry(BaseModel):
    """PRD「帳本」row: one piece of evidence and exactly what it changed."""

    op: str
    quote: str | None = None
    target: str | None = None
    before: Any = None
    after: Any = None
    note: str | None = None


class HandshakeResult(BaseModel):
    request: Engine02Request
    ledger: list[LedgerEntry] = Field(default_factory=list)
    rejected_ops: list[dict[str, Any]] = Field(default_factory=list)  # op + reason, never silently dropped


# ---------------------------------------------------------------------------
# PRD formula ④
# ---------------------------------------------------------------------------
def update_needs(needs: Sequence[NeedProbability], log_likelihood: dict[str, float],
                 lam: float = 1.0, floor: float = 1e-6) -> list[NeedProbability]:
    """log p(n) ← log p(n) + λ·log L(e|n), then renormalise (PRD formula ④).

    Needs absent from `log_likelihood` keep their log-probability, so the update is a reweighting,
    not a reset. `floor` keeps a need from collapsing to exactly 0 (it can come back next round).
    """
    if not needs:
        return []
    logs = {n.need_id: math.log(max(n.prob, floor)) + lam * float(log_likelihood.get(n.need_id, 0.0))
            for n in needs}
    m = max(logs.values())
    exp = {k: math.exp(v - m) for k, v in logs.items()}
    z = sum(exp.values()) or 1.0
    return [NeedProbability(need_id=n.need_id, label=n.label, prob=min(1.0, max(0.0, exp[n.need_id] / z)))
            for n in needs]


def need_likelihood(item_a: RankedItem, item_b: RankedItem, kansei, need_id: str,
                    alpha: float = 1.0) -> float:
    """σ(α·(S(A|n) − S(B|n))) with S(i|n) = Σ_d K[n,d]·c(i,d) taken from the cards' own
    `design_scores` (PRD §6.4 choice likelihood). ENGINE 03 should call this instead of
    recomputing c(i,d) — it cannot then drift from what ENGINE 02 actually ranked with."""
    if need_id not in kansei.need_ids:
        raise KeyError(f"unknown need_id {need_id!r}")
    i = kansei.need_ids.index(need_id)
    row = {e.id: float(kansei.K[i, j]) for j, e in enumerate(kansei.elements)}

    def s(it: RankedItem) -> float:
        return sum(row.get(d, 0.0) * v for d, v in it.design_scores.items())

    return 1.0 / (1.0 + math.exp(-alpha * (s(item_a) - s(item_b))))


# ---------------------------------------------------------------------------
# the handshake itself
# ---------------------------------------------------------------------------
def _remove_value(slot: Slot, value: str) -> bool:
    lv = value.lower()
    keep = [v for v in slot.values if str(v).lower() != lv]
    if len(keep) != len(slot.values):
        slot.values = keep
        if not keep and slot.state == SlotState.VALUE:
            slot.state = SlotState.UNMENTIONED
        return True
    return False


def apply_round(prev_req: Engine02Request, prev_resp: Engine02Response | None, fb: FeedbackRound,
                kansei=None, max_steps: int = 3, gain: int = 2) -> HandshakeResult:
    """Build the next `Engine02Request` from the previous one plus one round of ENGINE 03 ops.

    Pure function: `prev_req` is not mutated. Unknown design elements / attributes are reported in
    `rejected_ops` rather than dropped, so a mismatch between the engines is visible immediately.
    """
    req = prev_req.model_copy(deep=True)
    req.round = (prev_resp.round if prev_resp is not None else prev_req.round) + 1
    # single-round fields (rule 4)
    req.feedback.reference_item_id = None
    req.feedback.critique = None
    # recomputed by the service from choice_history (rule 5)
    req.feedback.design_weight_delta = {}
    if fb.utterance:
        req.utterances = list(req.utterances) + [fb.utterance]

    element_ids = set(kansei.element_ids) | set(getattr(kansei, "folded", {})) if kansei is not None else None
    ledger: list[LedgerEntry] = []
    rejected: list[dict[str, Any]] = []

    for op in fb.ops:
        if isinstance(op, ExcludeOp):
            vals = req.constraints.excluded_values.setdefault(op.attribute, [])
            before = list(vals)
            if op.value not in vals:
                vals.append(op.value)
            dropped = _remove_value(getattr(req.constraints, op.attribute), op.value) \
                if op.attribute in SLOT_ATTRIBUTES else False
            ledger.append(LedgerEntry(op="exclude", quote=op.quote, target=f"{op.attribute}={op.value}",
                                      before=before, after=list(vals),
                                      note="永不放寬" + ("；同時從正向條件移除" if dropped else "")))
        elif isinstance(op, RequireOp):
            vals = req.constraints.required_values.setdefault(op.attribute, [])
            before = list(vals)
            if op.value not in vals:
                vals.append(op.value)
            if op.attribute in SLOT_ATTRIBUTES:
                slot = getattr(req.constraints, op.attribute)
                slot.state = SlotState.VALUE
                if op.value not in slot.values:
                    slot.values = list(slot.values) + [op.value]
            ledger.append(LedgerEntry(op="require", quote=op.quote, target=f"{op.attribute}={op.value}",
                                      before=before, after=list(vals), note="硬條件且永不放寬"))
        elif isinstance(op, AdjustOp):
            if element_ids is not None and op.element not in element_ids:
                rejected.append({"op": op.model_dump(), "reason": f"unknown design element {op.element!r}"})
                continue
            steps = req.feedback.design_adjust_steps
            before = steps.get(op.element, 0)
            # one explicit complaint moves the median slate by -0.019 z at gain 1 and -0.167 z at
            # gain 2 (§3.38, 60 simulated shoppers); ENGINE 03 can only send ±1 so the gain is ours
            after = max(-max_steps, min(max_steps, before + int(op.step) * int(gain)))
            steps[op.element] = after
            note = (f"每步 {getattr(kansei, 'step_size', 0.25)}；一次回饋算 {gain} 步；"
                    f"上限 ±{max_steps}")
            if after == before:
                note += "（已達上限，未變動）"
            ledger.append(LedgerEntry(op="adjust", quote=op.quote, target=op.element,
                                      before=before, after=after, note=note))
        elif isinstance(op, ChoiceOp):
            shown = list(op.shown_item_ids) or ([it.item_id for it in prev_resp.items] if prev_resp else [])
            rec = ChoiceRecord(shown_item_ids=shown, chosen_item_id=op.chosen_item_id,
                               rejected_item_ids=list(op.rejected_item_ids))
            req.feedback.choice_history = list(req.feedback.choice_history) + [rec]
            if op.chosen_item_id:
                req.feedback.chosen_item_ids = list(dict.fromkeys(
                    req.feedback.chosen_item_ids + [op.chosen_item_id]))
            if op.rejected_item_ids:
                req.feedback.rejected_item_ids = list(dict.fromkeys(
                    req.feedback.rejected_item_ids + list(op.rejected_item_ids)))
            ledger.append(LedgerEntry(op="choice", target=op.chosen_item_id,
                                      before=len(req.feedback.choice_history) - 1,
                                      after=len(req.feedback.choice_history),
                                      note="由 Engine02Service 擬合 Bayes 成對 logistic（κ=1 縮減）；"
                                           "Rocchio 正負例同時記錄，但 T5 顯示 Rocchio 不顯著"))
        elif isinstance(op, FeelingOp):
            before = {n.need_id: round(n.prob, 4) for n in req.needs}
            if op.needs_override is not None:
                req.needs = [n.model_copy(deep=True) for n in op.needs_override]
            elif op.need_log_likelihood:
                req.needs = update_needs(req.needs, op.need_log_likelihood, op.lam)
            else:
                rejected.append({"op": op.model_dump(),
                                 "reason": "feeling needs need_log_likelihood or needs_override; "
                                           "ENGINE 02 does not infer p(n)"})
                continue
            after = {n.need_id: round(n.prob, 4) for n in req.needs}
            ledger.append(LedgerEntry(op="feeling", quote=op.quote, target="needs", before=before,
                                      after=after, note="PRD 公式④：log p(n) += λ·log L(e|n) 後正規化"))
        elif isinstance(op, CritiqueOp):
            if op.attribute is None and op.direction is None:
                rejected.append({"op": op.model_dump(), "reason": "critique needs attribute+to_value or direction"})
                continue
            req.feedback.reference_item_id = op.reference_item_id
            req.feedback.critique = Critique(attribute=op.attribute or "occasion", to_value=op.to_value,
                                             direction=op.direction)
            if op.attribute and op.to_value:
                vals = req.constraints.required_values.setdefault(op.attribute, [])
                if op.to_value not in vals:
                    vals.append(op.to_value)
            ledger.append(LedgerEntry(op="critique", quote=op.quote, target=op.reference_item_id,
                                      before=None, after={"attribute": op.attribute, "to_value": op.to_value,
                                                          "direction": op.direction},
                                      note="composed retrieval；目標值寫成 required_value，永不放寬"))
        elif isinstance(op, AnchorOp):
            before = list(req.feedback.anchor_item_ids)
            req.feedback.anchor_item_ids = list(op.item_ids) if op.replace else \
                list(dict.fromkeys(before + list(op.item_ids)))
            ledger.append(LedgerEntry(op="anchor", target=",".join(op.item_ids), before=before,
                                      after=list(req.feedback.anchor_item_ids),
                                      note="有錨點才會計算穿搭相容性"))
        elif isinstance(op, ExcludeItemOp):
            before = list(req.feedback.excluded_item_ids)
            req.feedback.excluded_item_ids = list(dict.fromkeys(before + list(op.item_ids)))
            ledger.append(LedgerEntry(op="exclude_item", target=",".join(op.item_ids), before=before,
                                      after=list(req.feedback.excluded_item_ids), note="不再出現"))
        else:  # pragma: no cover - the discriminated union makes this unreachable
            rejected.append({"op": getattr(op, "model_dump", lambda: {"op": str(op)})(), "reason": "unknown op"})
    return HandshakeResult(request=req, ledger=ledger, rejected_ops=rejected)


# ---------------------------------------------------------------------------
def round_trip(req: Engine02Request) -> Engine02Request:
    """JSON round trip through the wire format (what the HTTP boundary does)."""
    return Engine02Request.model_validate(json.loads(req.model_dump_json()))


def handshake_example(prev_req: Engine02Request, prev_resp: Engine02Response,
                      fb: FeedbackRound, kansei=None) -> dict[str, Any]:
    """A self-contained JSON document of one round, for `docs/contract/` and for the other engine
    owners to diff against their own implementation."""
    res = apply_round(prev_req, prev_resp, fb, kansei=kansei)
    return {
        "contract_version": prev_req.contract_version,
        "round_1_request": json.loads(prev_req.model_dump_json()),
        "round_1_response_items": [
            {"rank": it.rank, "item_id": it.item_id, "title": it.title, "score": round(it.score, 4),
             "cited": [c.term for c in it.contributions if c.cited]}
            for it in prev_resp.items
        ],
        "engine03_feedback": json.loads(fb.model_dump_json()),
        "ledger": [json.loads(e.model_dump_json()) for e in res.ledger],
        "rejected_ops": res.rejected_ops,
        "round_2_request": json.loads(res.request.model_dump_json()),
    }
