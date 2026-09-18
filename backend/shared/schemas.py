"""Cross-engine data contract.

Source of truth for the JSON shapes flowing between ENGINE01/02/03, the
generation module, and the frontend. See docs/interface-contract.md for the
rationale and example payloads behind each model; keep the two in sync when
either changes.

Draft v1 — written by the ENGINE01 owner to unblock parallel development.
Needs sign-off from ENGINE02/03/frontend owners before it's final.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field

STYLE_PREFERENCE_OPTIONS = ["日系", "韓系", "美式", "歐美", "街頭", "簡約", "正式", "其他"]
AGE_RANGE_OPTIONS = ["18-24", "25-34", "35-44", "45+"]


class UserProfile(BaseModel):
    """Persisted per-user record, created on first Google login. JSON
    file-backed (backend/shared/user_store.py), not a database -- see
    CLAUDE.md "資料庫"."""

    sub: str
    """Google account id (the ID token's `sub` claim) -- primary key."""
    email: str
    name: Optional[str] = None
    picture: Optional[str] = None
    age_range: Optional[str] = None
    style_preferences: list[str] = Field(default_factory=list)
    onboarding_completed: bool = False
    created_at: str
    """ISO 8601 timestamp."""


class ProfileUpdate(BaseModel):
    """Partial update for PUT /profile. Every field is optional so a user
    clicking "skip" can just send onboarding_completed=True with nothing else."""

    age_range: Optional[str] = None
    style_preferences: Optional[list[str]] = None
    onboarding_completed: Optional[bool] = None


class GoogleAuthRequest(BaseModel):
    id_token: str
    """The `credential` JWT returned by Google Identity Services on the frontend."""


class AuthResponse(BaseModel):
    session_token: str
    profile: UserProfile


class Intent(BaseModel):
    """Structured consumer intent extracted from a one-sentence request."""

    item_type: Optional[str] = None
    colors: list[str] = Field(default_factory=list)
    occasion: Optional[str] = None
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    style_keywords: list[str] = Field(default_factory=list)
    material: Optional[str] = None
    season: Optional[str] = None
    fit: Optional[str] = None
    pattern: Optional[str] = None
    collar: Optional[str] = None
    inferred_fields: list[str] = Field(default_factory=list)
    """Names of the fields above that GPT filled in by contextual inference
    (weather, season, etc.) rather than the user stating them. The frontend
    must render these as visibly system-inferred, not as the user's own words."""
    notes: Optional[str] = None


class ClarifyingOption(BaseModel):
    id: str
    label: str


class ClarifyingQuestion(BaseModel):
    field: str
    """Which Intent field this question is trying to fill in."""
    question: str
    options: list[ClarifyingOption]
    allow_free_text: bool = True


class IntentRequest(BaseModel):
    session_id: Optional[str] = None
    """Omit to start a new session."""
    message: str
    reference_image_url: Optional[str] = None


class IntentResponse(BaseModel):
    session_id: str
    round: int
    intent: Intent
    clarifying_questions: list[ClarifyingQuestion] = Field(default_factory=list)


class AttributeScore(BaseModel):
    attribute: str
    score: float
    comment: Optional[str] = None


class FeedbackInput(BaseModel):
    session_id: str
    round: int
    target: Literal["recommended", "generated"]
    attribute_scores: list[AttributeScore] = Field(default_factory=list)
    free_text: Optional[str] = None
    selected_option_id: Optional[str] = None


class WeightAdjustment(BaseModel):
    field: str
    delta: float
    reason: Optional[str] = None


class FeedbackResult(BaseModel):
    session_id: str
    round: int
    updated_intent: Intent
    weight_adjustments: list[WeightAdjustment] = Field(default_factory=list)


class ProductCard(BaseModel):
    product_id: str
    image_url: str
    title: str
    attributes: dict[str, str] = Field(default_factory=dict)
    score: float
    reason: str


class ConceptImage(BaseModel):
    image_url: str
    prompt_used: str
    response_id: Optional[str] = None
    """OpenAI Responses API id, passed as previous_response_id on the next round."""


class RetrievalResult(BaseModel):
    session_id: str
    round: int
    products: list[ProductCard]
    concept_image: ConceptImage
    match_score: float
    """The on-stage "符合度分數" shown before/after feedback (e.g. 62% -> 89%)."""
