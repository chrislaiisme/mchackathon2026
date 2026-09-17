"""OpenAI structured-output client for ENGINE01.

Requires OPENAI_API_KEY (see CLAUDE.md "P0 action item" if unset). Uses the
openai SDK's Pydantic-native structured output (`.parse()`), so the JSON
schema handed to the model is generated straight from the shared schemas
instead of being hand-written.
"""

from __future__ import annotations

import os

from openai import OpenAI
from pydantic import BaseModel, Field

from backend.engine01_intent.prompts import INTENT_SYSTEM_PROMPT
from backend.shared.schemas import ClarifyingQuestion, Intent

_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


class IntentExtraction(BaseModel):
    intent: Intent
    clarifying_questions: list[ClarifyingQuestion] = Field(default_factory=list)


def _client() -> OpenAI:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Copy .env.example to .env and fill it in "
            "(see CLAUDE.md 'P0 action item')."
        )
    return OpenAI(api_key=api_key)


def extract_intent(message: str, current_intent: Intent) -> IntentExtraction:
    """Merge `message` into `current_intent` and return the updated intent
    plus any clarifying questions, via a single structured-output call."""
    response = _client().beta.chat.completions.parse(
        model=_MODEL,
        messages=[
            {"role": "system", "content": INTENT_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"目前累積的結構化意圖（JSON）：\n{current_intent.model_dump_json()}\n\n"
                    f"使用者這一輪新說的話：\n{message}"
                ),
            },
        ],
        response_format=IntentExtraction,
    )
    parsed = response.choices[0].message.parsed
    if parsed is None:
        raise RuntimeError("OpenAI did not return a parsed structured response.")
    return parsed
