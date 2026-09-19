import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.engine03_feedback.contracts import Engine3Request
from backend.engine03_feedback.service import process_feedback


EXAMPLE = Path(__file__).parents[1] / "examples" / "click_only_request.json"


def load_example() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def test_click_only_feedback_is_deterministic() -> None:
    result = process_feedback(Engine3Request.model_validate(load_example()))

    assert result.contract_version == "0.2.0"
    assert result.engine02_feedback.session_id == "demo-interview"
    assert result.engine02_feedback.round == 1
    assert result.engine02_feedback.utterance is None
    assert len(result.engine02_feedback.ops) == 1
    choice = result.engine02_feedback.ops[0]
    assert choice.op == "choice"
    assert choice.shown_item_ids == ["14716", "14731"]
    assert choice.chosen_item_id == "14731"
    assert choice.rejected_item_ids == ["14716"]
    assert result.rejected_ops == []


def test_scores_map_to_steps_with_neutral_band() -> None:
    payload = load_example()
    payload["interaction"] = {}
    payload["attribute_scores"] = [
        {"element": "formal_style", "score": 0.2},
        {"element": "soft_knit", "score": 0.8},
        {"element": "dark_tone", "score": 0.5},
    ]
    payload["allowed_design_elements"].append("dark_tone")

    result = process_feedback(Engine3Request.model_validate(payload))
    assert [op.model_dump(mode="json") for op in result.engine02_feedback.ops] == [
        {"op": "adjust", "element": "formal_style", "step": -1, "quote": None},
        {"op": "adjust", "element": "soft_knit", "step": 1, "quote": None},
    ]


def test_unknown_score_element_is_rejected_not_silently_dropped() -> None:
    payload = load_example()
    payload["interaction"] = {}
    payload["attribute_scores"] = [{"element": "invented_axis", "score": 0.9}]

    result = process_feedback(Engine3Request.model_validate(payload))
    assert result.engine02_feedback.ops == []
    assert "unknown design element" in result.rejected_ops[0].reason


def test_context_must_match_top_level_session_and_round() -> None:
    payload = load_example()
    payload["engine02_response"]["round"] = 2

    with pytest.raises(ValidationError, match="round must match"):
        Engine3Request.model_validate(payload)


def test_chosen_item_cannot_also_be_rejected() -> None:
    payload = load_example()
    payload["interaction"]["rejected_item_ids"] = ["14731"]

    with pytest.raises(ValidationError, match="chosen item cannot"):
        Engine3Request.model_validate(payload)


def test_unknown_choice_item_rejects_whole_choice_operation() -> None:
    payload = load_example()
    payload["interaction"]["chosen_item_id"] = "not-shown"
    payload["interaction"]["rejected_item_ids"] = []

    result = process_feedback(Engine3Request.model_validate(payload))
    assert result.engine02_feedback.ops == []
    assert "not shown" in result.rejected_ops[0].reason


def test_anchor_may_come_from_wardrobe_or_earlier_round() -> None:
    payload = load_example()
    payload["interaction"] = {
        "anchor_item_ids": ["wardrobe-top-1"],
        "replace_anchors": True,
    }

    result = process_feedback(Engine3Request.model_validate(payload))
    anchor = result.engine02_feedback.ops[0]
    assert anchor.op == "anchor"
    assert anchor.item_ids == ["wardrobe-top-1"]
    assert anchor.replace is True
