import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.engine03_feedback.contracts import (
    AdjustOp,
    Engine3Decision,
    Engine3Request,
    GenerationAdjustment,
    GenerationDecision,
)
from backend.shared.schemas import Intent
from backend.engine03_feedback.service import process_feedback


EXAMPLE = Path(__file__).parents[1] / "examples" / "click_only_request.json"


def load_example() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def test_click_only_feedback_needs_no_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = process_feedback(Engine3Request.model_validate(load_example()))

    assert result.contract_version == "0.1.0"
    assert result.engine02_feedback.session_id == "demo-interview"
    assert result.engine02_feedback.round == 1
    assert len(result.engine02_feedback.ops) == 1
    choice = result.engine02_feedback.ops[0]
    assert choice.op == "choice"
    assert choice.shown_item_ids == ["14716", "14731"]
    assert choice.chosen_item_id == "14731"
    assert choice.rejected_item_ids == ["14716"]
    assert result.updated_intent.item_type == "top"
    assert result.rejected_ops == []


def test_feedback_input_must_match_engine02_round() -> None:
    payload = load_example()
    payload["feedback_inputs"] = [
        {
            "session_id": "demo-interview",
            "round": 2,
            "target": "recommended",
            "free_text": "不要這麼正式",
        }
    ]
    with pytest.raises(ValidationError, match="session_id and round"):
        Engine3Request.model_validate(payload)


def test_attribute_scores_use_shared_zero_to_one_contract() -> None:
    payload = load_example()
    payload["feedback_inputs"] = [
        {
            "session_id": "demo-interview",
            "round": 1,
            "target": "recommended",
            "attribute_scores": [{"attribute": "fit", "score": 5.0}],
        }
    ]
    with pytest.raises(ValidationError, match="between 0 and 1"):
        Engine3Request.model_validate(payload)


def test_feedback_input_requires_text_but_click_only_does_not() -> None:
    payload = load_example()
    payload["feedback_inputs"] = [
        {
            "session_id": "demo-interview",
            "round": 1,
            "target": "recommended",
            "attribute_scores": [{"attribute": "fit", "score": 0.3}],
        }
    ]
    with pytest.raises(ValidationError, match="non-empty free_text"):
        Engine3Request.model_validate(payload)


def test_generated_feedback_never_becomes_engine02_ops(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = load_example()
    payload["interaction"] = {}
    payload["feedback_inputs"] = [
        {
            "session_id": "demo-interview",
            "round": 1,
            "target": "generated",
            "attribute_scores": [{"attribute": "fit", "score": 0.2}],
            "free_text": "AI 圖太正式，希望輪廓柔和一點",
        }
    ]

    def fake_generation(_request: Engine3Request) -> GenerationDecision:
        return GenerationDecision(
            reasoning="只調整生成圖。",
            generation_prompt="柔和、休閒輪廓的面試上衣",
            adjustments=[
                GenerationAdjustment(
                    attribute="fit", direction=-1, strength=0.6, reason="輪廓太正式"
                )
            ],
        )

    monkeypatch.setattr(
        "backend.engine03_feedback.service._generation_decision", fake_generation
    )
    result = process_feedback(Engine3Request.model_validate(payload))

    assert result.engine02_feedback.ops == []
    assert result.engine02_feedback.utterance is None
    assert result.updated_intent == Intent.model_validate(payload["current_intent"])
    assert result.generation_prompt == "柔和、休閒輪廓的面試上衣"
    assert result.generation_adjustments[0].attribute == "fit"


def test_recommended_adjustment_serializes_as_engine02_feedback_round(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = load_example()
    payload["interaction"] = {}
    payload["feedback_intent"] = {
        **payload["current_intent"],
        "style_keywords": ["可靠", "休閒"],
    }
    payload["feedback_inputs"] = [
        {
            "session_id": "demo-interview",
            "round": 1,
            "target": "recommended",
            "attribute_scores": [{"attribute": "fit", "score": 0.2}],
            "free_text": "推薦商品太正式，希望更休閒",
        }
    ]

    def fake_recommendation(_request: Engine3Request) -> Engine3Decision:
        return Engine3Decision(
            reasoning="降低正式感。",
            ops=[AdjustOp(element="formal_style", step=-1, quote="太正式")],
            updated_intent=Intent.model_validate(payload["current_intent"]),
        )

    monkeypatch.setattr(
        "backend.engine03_feedback.service._model_decision", fake_recommendation
    )
    result = process_feedback(Engine3Request.model_validate(payload))
    wire = result.engine02_feedback.model_dump(mode="json")

    assert result.generation_adjustments == []
    assert wire == {
        "session_id": "demo-interview",
        "round": 1,
        "utterance": "推薦商品太正式，希望更休閒",
        "ops": [
            {
                "op": "adjust",
                "element": "formal_style",
                "step": -1,
                "quote": "太正式",
            }
        ],
    }


def test_recommended_text_requires_engine01_feedback_intent() -> None:
    payload = load_example()
    payload["interaction"] = {}
    payload["feedback_inputs"] = [
        {
            "session_id": "demo-interview",
            "round": 1,
            "target": "recommended",
            "free_text": "希望更休閒",
        }
    ]

    with pytest.raises(ValidationError, match="feedback_intent produced by ENGINE 01"):
        Engine3Request.model_validate(payload)
