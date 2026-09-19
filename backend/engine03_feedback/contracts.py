"""ENGINE 03 contracts for structured, non-language feedback.

Natural language belongs to ENGINE 01. ENGINE 03 receives only attribute scores and explicit UI
interactions, then emits the small subset of ENGINE 02 operations those signals can justify.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


CONTRACT_VERSION = "0.2.0"


class ContractModel(BaseModel):
    """Ignore additive sibling-engine fields while keeping required fields strict."""

    model_config = ConfigDict(extra="ignore")


class NeedProbability(ContractModel):
    need_id: str
    label: str | None = None
    prob: float = Field(ge=0.0, le=1.0)


class Slot(ContractModel):
    state: Literal["unmentioned", "value", "dont_care", "inferred"] = "unmentioned"
    values: list[str] = Field(default_factory=list)
    hard: bool | None = None


class BudgetSlot(ContractModel):
    state: Literal["unmentioned", "value", "dont_care", "inferred"] = "unmentioned"
    max_price: float | None = None
    min_price: float | None = None
    currency: str | None = None
    hard: bool | None = None


class HardConstraints(ContractModel):
    category: Slot = Field(default_factory=Slot)
    color: Slot = Field(default_factory=Slot)
    occasion: Slot = Field(default_factory=Slot)
    season: Slot = Field(default_factory=Slot)
    gender: Slot = Field(default_factory=Slot)
    style_keywords: Slot = Field(default_factory=Slot)
    budget: BudgetSlot = Field(default_factory=BudgetSlot)
    excluded_values: dict[str, list[str]] = Field(default_factory=dict)
    required_values: dict[str, list[str]] = Field(default_factory=dict)


class Engine02FeedbackState(ContractModel):
    design_adjust_steps: dict[str, int] = Field(default_factory=dict)
    chosen_item_ids: list[str] = Field(default_factory=list)
    rejected_item_ids: list[str] = Field(default_factory=list)
    excluded_item_ids: list[str] = Field(default_factory=list)
    anchor_item_ids: list[str] = Field(default_factory=list)
    concept_image_embedding: list[float] | None = None
    reference_item_id: str | None = None
    critique: dict[str, Any] | None = None
    choice_history: list[dict[str, Any]] = Field(default_factory=list)
    design_weight_delta: dict[str, float] = Field(default_factory=dict)


class Engine02RequestContext(ContractModel):
    """Relevant Engine02Request subset; the complete payload is accepted."""

    contract_version: str = "0.1.0"
    session_id: str
    round: int = 1
    utterances: list[str] = Field(default_factory=list)
    retrieval_text: str | None = None
    retrieval_text_normalized: bool | None = None
    design_weight_prior: dict[str, float] = Field(default_factory=dict)
    constraints: HardConstraints = Field(default_factory=HardConstraints)
    needs: list[NeedProbability] = Field(default_factory=list)
    feedback: Engine02FeedbackState = Field(default_factory=Engine02FeedbackState)


class RankedItemContext(ContractModel):
    item_id: str
    rank: int
    title: str
    image_path: str | None = None
    category: str | None = None
    color: str | None = None
    price: float | None = None
    score: float
    design_scores: dict[str, float] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)


class Engine02ResponseContext(ContractModel):
    """Relevant Engine02Response subset; the complete payload is accepted."""

    contract_version: str = "0.1.0"
    session_id: str
    round: int
    items: list[RankedItemContext] = Field(default_factory=list)
    query_embedding: list[float] | None = None


class AttributeScore(ContractModel):
    """A direct rating of one ENGINE 02 design-element ID."""

    element: str
    score: float = Field(ge=0.0, le=1.0)


class UserInteraction(ContractModel):
    """Explicit UI actions; scores never infer these states."""

    chosen_item_id: str | None = None
    rejected_item_ids: list[str] = Field(default_factory=list)
    excluded_item_ids: list[str] = Field(default_factory=list)
    anchor_item_ids: list[str] = Field(default_factory=list)
    replace_anchors: bool = False


class Engine3Request(ContractModel):
    session_id: str
    round: int
    attribute_scores: list[AttributeScore] = Field(default_factory=list)
    interaction: UserInteraction = Field(default_factory=UserInteraction)
    engine02_request: Engine02RequestContext
    engine02_response: Engine02ResponseContext
    allowed_design_elements: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_handoff(self) -> "Engine3Request":
        contexts = (self.engine02_request, self.engine02_response)
        if any(context.session_id != self.session_id for context in contexts):
            raise ValueError("session_id must match ENGINE 02 request and response")
        if any(context.round != self.round for context in contexts):
            raise ValueError("round must match ENGINE 02 request and response")

        elements = [score.element for score in self.attribute_scores]
        if len(elements) != len(set(elements)):
            raise ValueError("attribute_scores must contain each element at most once")

        chosen = self.interaction.chosen_item_id
        rejected = set(self.interaction.rejected_item_ids)
        excluded = set(self.interaction.excluded_item_ids)
        if chosen and (chosen in rejected or chosen in excluded):
            raise ValueError("chosen item cannot also be rejected or excluded")
        if rejected & excluded:
            raise ValueError("an item cannot be both rejected and excluded in one request")

        has_interaction = bool(self.interaction.model_dump(exclude_defaults=True))
        if not self.attribute_scores and not has_interaction:
            raise ValueError("provide at least one attribute score or explicit UI interaction")
        return self


class AdjustOp(ContractModel):
    op: Literal["adjust"] = "adjust"
    element: str
    step: Literal[-1, 1]
    quote: str | None = None


class ChoiceOp(ContractModel):
    op: Literal["choice"] = "choice"
    shown_item_ids: list[str] = Field(default_factory=list)
    chosen_item_id: str | None = None
    rejected_item_ids: list[str] = Field(default_factory=list)


class AnchorOp(ContractModel):
    op: Literal["anchor"] = "anchor"
    item_ids: list[str] = Field(default_factory=list)
    replace: bool = False


class ExcludeItemOp(ContractModel):
    op: Literal["exclude_item"] = "exclude_item"
    item_ids: list[str] = Field(default_factory=list)


FeedbackOp = Annotated[
    AdjustOp | ChoiceOp | AnchorOp | ExcludeItemOp,
    Field(discriminator="op"),
]


class FeedbackRound(ContractModel):
    """Payload accepted by engine02.handshake.apply_round()."""

    session_id: str
    round: int
    utterance: None = None
    ops: list[FeedbackOp] = Field(default_factory=list)


class RejectedOperation(ContractModel):
    operation: dict[str, Any]
    reason: str


class Engine3Response(ContractModel):
    contract_version: str = CONTRACT_VERSION
    engine02_feedback: FeedbackRound
    rejected_ops: list[RejectedOperation] = Field(default_factory=list)
