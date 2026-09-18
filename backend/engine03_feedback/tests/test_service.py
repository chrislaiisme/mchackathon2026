import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.engine03_feedback.contracts import Engine3Request
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
