"""Wire contracts for ENGINE 03.

ENGINE 03 receives one batch for a recommendation round. It never receives
natural language and deliberately does not model outfit feedback yet.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .attributes import ATTRIBUTE_IDS


CONTRACT_VERSION = "0.5.0"


class AttributeRating(BaseModel):
    """A 1-5 rating for one ENGINE 02 design-element id."""

    attribute: str = Field(min_length=1)
    stars: int = Field(ge=1, le=5)


class ItemFeedback(BaseModel):
    """All explicit feedback for one item; omitted fields mean no action."""

    item_id: str = Field(min_length=1)
    source: Literal["catalog", "generated"] = "catalog"
    favorited: bool = False
    disliked: bool = False
    attribute_ratings: list[AttributeRating] = Field(default_factory=list)
    # Supplied by the trusted BFF from the generation manifest, never trusted from the browser.
    design_attributes: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_actions(self) -> "ItemFeedback":
        if self.favorited and self.disliked:
            raise ValueError("an item cannot be both favorited and disliked")
        if not self.favorited and not self.disliked and not self.attribute_ratings:
            raise ValueError("item_feedback must contain at least one explicit action")
        if self.source == "catalog" and self.design_attributes:
            raise ValueError("catalog feedback must not contain generated design_attributes")
        if self.source == "generated" and (self.favorited or self.disliked) and not self.design_attributes:
            raise ValueError("generated favorite/dislike requires trusted design_attributes")
        attributes = [rating.attribute for rating in self.attribute_ratings]
        if len(attributes) != len(set(attributes)):
            raise ValueError("an attribute may be rated only once per item")
        return self


class FeedbackRound(BaseModel):
    """One completed recommendation round supplied by the BFF."""

    round: int = Field(ge=1)
    shown_item_ids: list[str] = Field(default_factory=list)
    shown_generated_item_ids: list[str] = Field(default_factory=list)
    item_feedbacks: list[ItemFeedback] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_round(self) -> "Engine3Request":
        if len(self.shown_item_ids) != len(set(self.shown_item_ids)):
            raise ValueError("shown_item_ids must not contain duplicates")
        if len(self.shown_generated_item_ids) != len(set(self.shown_generated_item_ids)):
            raise ValueError("shown_generated_item_ids must not contain duplicates")
        if not self.shown_item_ids and not self.shown_generated_item_ids:
            raise ValueError("a feedback round must contain shown catalog or generated items")
        item_ids = [feedback.item_id for feedback in self.item_feedbacks]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("each item may appear only once in item_feedbacks")
        unknown_catalog = sorted({
            feedback.item_id for feedback in self.item_feedbacks
            if feedback.source == "catalog" and feedback.item_id not in self.shown_item_ids
        })
        unknown_generated = sorted({
            feedback.item_id for feedback in self.item_feedbacks
            if feedback.source == "generated" and feedback.item_id not in self.shown_generated_item_ids
        })
        if unknown_catalog or unknown_generated:
            raise ValueError(
                "feedback item ids were not shown this round: "
                f"catalog={unknown_catalog}, generated={unknown_generated}"
            )
        unknown_attributes = sorted({
            rating.attribute
            for feedback in self.item_feedbacks
            for rating in feedback.attribute_ratings
            if rating.attribute not in ATTRIBUTE_IDS
        })
        if unknown_attributes:
            raise ValueError(f"unknown ENGINE 02 attributes: {unknown_attributes}")
        return self


class Engine3Request(FeedbackRound):
    session_id: str = Field(min_length=1)
    previous_rounds: list[FeedbackRound] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def validate_history(self) -> "Engine3Request":
        rounds = [item.round for item in self.previous_rounds]
        if len(rounds) != len(set(rounds)):
            raise ValueError("previous_rounds must not contain duplicate rounds")
        if rounds != sorted(rounds):
            raise ValueError("previous_rounds must be ordered oldest to newest")
        if any(round_number >= self.round for round_number in rounds):
            raise ValueError("previous_rounds must be older than the current round")
        return self


class AttributeEvidence(BaseModel):
    """Auditable per-item conversion before values are combined per attribute."""

    round: int
    item_id: str
    source: Literal["catalog", "generated"]
    attribute: str
    stars: int
    weight: float


class GeneratedAttributeEvidence(BaseModel):
    round: int
    item_id: str
    action: Literal["favorite", "dislike"]
    field: str
    value: str
    mapped_axes: dict[str, float] = Field(default_factory=dict)


class ChoiceRecord(BaseModel):
    shown_item_ids: list[str]
    chosen_item_id: str | None = None
    rejected_item_ids: list[str] = Field(default_factory=list)


class Engine02Feedback(BaseModel):
    """The actual subset of engine02.contracts.FeedbackState produced here."""

    chosen_item_ids: list[str] = Field(default_factory=list)
    rejected_item_ids: list[str] = Field(default_factory=list)
    choice_history: list[ChoiceRecord] = Field(default_factory=list)
    design_weight_delta: dict[str, float] = Field(default_factory=dict)


class Engine3Response(BaseModel):
    contract_version: str = CONTRACT_VERSION
    session_id: str
    round: int
    window_rounds: list[int]
    engine02_feedback: Engine02Feedback
    attribute_evidence: list[AttributeEvidence] = Field(default_factory=list)
    generated_attribute_evidence: list[GeneratedAttributeEvidence] = Field(default_factory=list)
