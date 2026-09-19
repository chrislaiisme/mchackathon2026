"""ENGINE 03 I/O contracts.

ENGINE 01 types are imported from the integration framework's shared schema.
ENGINE 02's contract-0.1.0 feedback operations are mirrored here until the
engine02-research branch is merged into the framework.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.shared.schemas import FeedbackInput, Intent


CONTRACT_VERSION = "0.1.0"
AttributeName = Literal["category", "subcategory", "color", "occasion", "season", "gender"]
CritiqueAttribute = Literal["color", "occasion", "category", "subcategory", "season"]


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

    contract_version: str = CONTRACT_VERSION
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

    contract_version: str = CONTRACT_VERSION
    session_id: str
    round: int
    items: list[RankedItemContext] = Field(default_factory=list)
    query_embedding: list[float] | None = None


class UserInteraction(ContractModel):
    """Explicit UI actions; these are authoritative and never inferred by the LLM."""

    chosen_item_id: str | None = None
    rejected_item_ids: list[str] = Field(default_factory=list)
    excluded_item_ids: list[str] = Field(default_factory=list)
    anchor_item_ids: list[str] = Field(default_factory=list)
    replace_anchors: bool = False


class Engine3Request(ContractModel):
    # Snapshot used to produce the cards currently on screen.
    current_intent: Intent
    # Full candidate Intent returned by ENGINE 01 after it merges the recommended-feedback text
    # into `current_intent`. ENGINE 03 compares the two; it does not re-extract language from zero.
    feedback_intent: Intent | None = None
    feedback_inputs: list[FeedbackInput] = Field(default_factory=list)
    engine02_request: Engine02RequestContext
    engine02_response: Engine02ResponseContext
    interaction: UserInteraction = Field(default_factory=UserInteraction)
    allowed_design_elements: list[str] = Field(default_factory=list)
    allowed_attribute_values: dict[str, list[str]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_handoff(self) -> "Engine3Request":
        session_id = self.engine02_response.session_id
        round_number = self.engine02_response.round
        if self.engine02_request.session_id != session_id:
            raise ValueError("ENGINE 02 request/response session_id must match")
        if self.engine02_request.round != round_number:
            raise ValueError("ENGINE 02 request/response round must match")

        seen_targets: set[str] = set()
        for feedback in self.feedback_inputs:
            if feedback.session_id != session_id or feedback.round != round_number:
                raise ValueError("every FeedbackInput must match ENGINE 02 session_id and round")
            if feedback.target in seen_targets:
                raise ValueError(f"duplicate FeedbackInput target: {feedback.target}")
            seen_targets.add(feedback.target)
            for score in feedback.attribute_scores:
                if not 0.0 <= score.score <= 1.0:
                    raise ValueError("FeedbackInput attribute score must be between 0 and 1")
            # A score or click without the user's words is too ambiguous to turn into a semantic
            # adjustment. Product clicks live in `interaction`, so every FeedbackInput is an
            # explicit written critique and must carry its own explanation.
            if not (feedback.free_text or "").strip():
                raise ValueError("every FeedbackInput must include non-empty free_text")

        has_feedback = any(
            feedback.free_text
            or feedback.selected_option_id
            or feedback.attribute_scores
            for feedback in self.feedback_inputs
        )
        has_interaction = bool(self.interaction.model_dump(exclude_defaults=True))
        if not has_feedback and not has_interaction:
            raise ValueError("provide at least one FeedbackInput value or explicit UI interaction")
        has_recommended_text = any(
            feedback.target == "recommended" for feedback in self.feedback_inputs
        )
        if has_recommended_text and self.feedback_intent is None:
            raise ValueError(
                "recommended feedback requires feedback_intent produced by ENGINE 01"
            )
        return self


# ENGINE 02 contract 0.1.0 operation set -----------------------------------


class ExcludeOp(ContractModel):
    op: Literal["exclude"] = "exclude"
    attribute: AttributeName
    value: str
    quote: str | None = None


class RequireOp(ContractModel):
    op: Literal["require"] = "require"
    attribute: AttributeName
    value: str
    quote: str | None = None


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


class FeelingOp(ContractModel):
    op: Literal["feeling"] = "feeling"
    quote: str
    need_log_likelihood: dict[str, float] = Field(default_factory=dict)
    lam: float = 1.0
    needs_override: list[NeedProbability] | None = None


class CritiqueOp(ContractModel):
    op: Literal["critique"] = "critique"
    reference_item_id: str
    attribute: CritiqueAttribute | None = None
    to_value: str | None = None
    direction: Literal["more_formal", "more_casual", "sportier"] | None = None
    quote: str | None = None


class AnchorOp(ContractModel):
    op: Literal["anchor"] = "anchor"
    item_ids: list[str] = Field(default_factory=list)
    replace: bool = False


class ExcludeItemOp(ContractModel):
    op: Literal["exclude_item"] = "exclude_item"
    item_ids: list[str] = Field(default_factory=list)


FeedbackOp = Annotated[
    ExcludeOp | RequireOp | AdjustOp | ChoiceOp | FeelingOp | CritiqueOp | AnchorOp | ExcludeItemOp,
    Field(discriminator="op"),
]


class FeedbackRound(ContractModel):
    """Exact payload accepted by engine02.handshake.apply_round()."""

    session_id: str
    round: int
    utterance: str | None = None
    ops: list[FeedbackOp] = Field(default_factory=list)


class Engine3Decision(ContractModel):
    """Structured LLM output before deterministic validation and UI merge."""

    reasoning: str
    ops: list[FeedbackOp] = Field(default_factory=list)
    updated_intent: Intent


class GenerationAdjustment(ContractModel):
    """A generation-only nudge. It must never be forwarded to ENGINE 02."""

    attribute: str
    direction: Literal[-1, 1]
    strength: float = Field(default=1.0, ge=0.0, le=1.0)
    reason: str | None = None


class GenerationDecision(ContractModel):
    reasoning: str
    generation_prompt: str
    adjustments: list[GenerationAdjustment] = Field(default_factory=list)


class RejectedOperation(ContractModel):
    operation: dict[str, Any]
    reason: str


class Engine3Response(ContractModel):
    contract_version: str = CONTRACT_VERSION
    reasoning: str
    engine02_feedback: FeedbackRound
    updated_intent: Intent
    generation_prompt: str | None = None
    generation_adjustments: list[GenerationAdjustment] = Field(default_factory=list)
    rejected_ops: list[RejectedOperation] = Field(default_factory=list)
