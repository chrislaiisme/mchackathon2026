"""I/O contract of ENGINE 02.

Input  = session state produced by ENGINE 01 (hard constraints + need probabilities)
         plus the parts of ENGINE 03's ledger that affect ranking (Δβ, exclusions,
         chosen / rejected items, anchor items).
Output = ranked cards whose score decomposition *is* the explanation, plus the
         per-item design-element scores c(i,d) that ENGINE 03 needs for its choice
         likelihood S(i|n) = Σ_d K[n,d]·c(i,d).

Field names follow the team PRD (HackMD, sections 6.2–6.4). Anything the PRD leaves
open is marked "proposed" and must be confirmed with the ENGINE 01 / 03 owners.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

CONTRACT_VERSION = "0.1.0"


# ---------------------------------------------------------------------------
# Input from ENGINE 01
# ---------------------------------------------------------------------------


class SlotState(str, Enum):
    """PRD M1: every slot is in one of four states."""

    UNMENTIONED = "unmentioned"  # 未提及
    VALUE = "value"  # 有值（使用者明說）
    DONT_CARE = "dont_care"  # 不在意
    INFERRED = "inferred"  # 系統推論


class Slot(BaseModel):
    state: SlotState = SlotState.UNMENTIONED
    values: list[str] = Field(default_factory=list)
    # Stated values are hard filters; inferred values are soft preferences only.
    hard: bool | None = None

    def is_hard(self) -> bool:
        if self.hard is not None:
            return self.hard
        return self.state == SlotState.VALUE


class BudgetSlot(BaseModel):
    state: SlotState = SlotState.UNMENTIONED
    max_price: float | None = None
    min_price: float | None = None
    currency: str | None = None
    hard: bool | None = None

    def is_hard(self) -> bool:
        if self.hard is not None:
            return self.hard
        return self.state == SlotState.VALUE


class HardConstraints(BaseModel):
    """Slots extracted by ENGINE 01 (M1). Values should already be normalised to the
    catalog vocabulary (see engine02/resources/vocabulary.json)."""

    category: Slot = Field(default_factory=Slot)
    color: Slot = Field(default_factory=Slot)
    occasion: Slot = Field(default_factory=Slot)
    season: Slot = Field(default_factory=Slot)
    gender: Slot = Field(default_factory=Slot)
    style_keywords: Slot = Field(default_factory=Slot)
    budget: BudgetSlot = Field(default_factory=BudgetSlot)
    # exclude(屬性, 值) from ENGINE 03 lands here, e.g. {"color": ["black"]}
    excluded_values: dict[str, list[str]] = Field(default_factory=dict)


class NeedProbability(BaseModel):
    """PRD M2 output p(n)."""

    need_id: str  # must exist in the Kansei table, e.g. "trustworthy"
    label: str | None = None  # display text, e.g. "被信任"
    prob: float = Field(ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Input from ENGINE 03 (ledger parts that change ranking)
# ---------------------------------------------------------------------------


class FeedbackState(BaseModel):
    # adjust(設計要素, ±1) accumulated by ENGINE 03 → Δβ_d (in steps; E2 maps steps to weight)
    design_adjust_steps: dict[str, int] = Field(default_factory=dict)
    # choice / critique on concrete items
    chosen_item_ids: list[str] = Field(default_factory=list)  # Rocchio positives
    rejected_item_ids: list[str] = Field(default_factory=list)  # Rocchio negatives
    excluded_item_ids: list[str] = Field(default_factory=list)  # never show again
    # items the user wants to wear WITH the recommendation → enables compatibility term
    anchor_item_ids: list[str] = Field(default_factory=list)
    # proposed: embedding of the generated concept image (generation branch), optional
    concept_image_embedding: list[float] | None = None


class Engine02Options(BaseModel):
    top_k: int = 5
    n_candidates: int = 50
    arm: str = "full"  # ablation arm name, see engine02/config.py
    explain_with_llm: bool = True
    counterfactual_check: bool = True


class Engine02Request(BaseModel):
    contract_version: str = CONTRACT_VERSION
    session_id: str
    round: int = 1
    # original user sentence(s) of this session, newest last
    utterances: list[str] = Field(default_factory=list)
    # proposed: short English caption written by ENGINE 01 for the text encoder / BM25
    # (catalog text is English, users speak Chinese). No negations — those go to
    # constraints.excluded_values. If absent, ENGINE 02 builds one from the slots.
    retrieval_text: str | None = None
    constraints: HardConstraints = Field(default_factory=HardConstraints)
    needs: list[NeedProbability] = Field(default_factory=list)
    feedback: FeedbackState = Field(default_factory=FeedbackState)
    options: Engine02Options = Field(default_factory=Engine02Options)


# ---------------------------------------------------------------------------
# Output to ENGINE 03 / frontend
# ---------------------------------------------------------------------------

TermGroup = Literal["dense", "bm25", "compat", "trend", "design", "penalty", "rerank"]


class Contribution(BaseModel):
    term: str  # e.g. "dense", "design:structured_shoulders"
    group: TermGroup
    raw: float  # raw feature value before normalisation
    normalized: float  # z-scored within candidates
    weight: float
    contribution: float  # weight * normalized; all contributions sum to score
    # which needs this term serves, p(n)·K[n,d]·c(i,d) share (design terms only)
    need_shares: dict[str, float] = Field(default_factory=dict)
    # counterfactual necessity (PRD M7): rank after zeroing this term
    rank_without: int | None = None
    necessary: bool | None = None  # True if removing it drops item out of top-k
    # contrastive: this term's contribution minus that of the first item below the cut
    diff_vs_cutoff: float | None = None
    # member of the minimal set of terms that alone keeps the item above the cut
    sufficient: bool | None = None
    cited: bool = False  # used as a reason on the card


class RankedItem(BaseModel):
    item_id: str
    rank: int
    title: str
    image_path: str
    category: str | None = None
    color: str | None = None
    price: float | None = None
    score: float
    contributions: list[Contribution]
    need_contributions: dict[str, float] = Field(default_factory=dict)
    # c(i,d) for every design element — ENGINE 03 uses it for S(i|n)
    design_scores: dict[str, float] = Field(default_factory=dict)
    margin_vs_cutoff: float | None = None  # score gap to the rank k+1 item
    reason_mode: str = "sufficient"
    reasons: list[str] = Field(default_factory=list)  # template sentences, verified
    explanation: str = ""
    explanation_source: Literal["llm", "template"] = "template"


class ConstraintReport(BaseModel):
    applied: dict[str, list[str]] = Field(default_factory=dict)
    relaxed: list[str] = Field(default_factory=list)  # in the order they were relaxed
    n_catalog: int = 0
    n_after_filter: int = 0


class RoundMetrics(BaseModel):
    """PRD §7 rule-based metrics — computed from item attributes, never from the score."""

    hard_constraint_satisfaction: float | None = None
    excluded_value_hits: int = 0
    feedback_violations: int = 0


class Engine02Response(BaseModel):
    contract_version: str = CONTRACT_VERSION
    session_id: str
    round: int
    arm: str
    items: list[RankedItem]
    constraint_report: ConstraintReport
    metrics: RoundMetrics
    kansei_version: str
    encoder: str
    # proposed: query vector used this round, so ENGINE 03 can apply Rocchio next round
    query_embedding: list[float] | None = None
    timings_ms: dict[str, float] = Field(default_factory=dict)
