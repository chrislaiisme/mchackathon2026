import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.engine03_feedback.contracts import Engine3Request
from backend.engine03_feedback.attributes import (
    ATTRIBUTE_DEFINITIONS,
    ATTRIBUTE_IDS,
    ENGINE02_AXIS_IDS,
    frontend_attribute_catalog,
)
from backend.engine03_feedback.service import STAR_TO_WEIGHT, process_feedback
from engine02.contracts import FeedbackState
from engine02.intent_adapter import feedback_from_engine03


def request(**overrides) -> Engine3Request:
    payload = {
        "session_id": "s1",
        "round": 1,
        "shown_item_ids": ["A", "B", "C"],
        "item_feedbacks": [
            {
                "item_id": "A",
                "favorited": True,
                "attribute_ratings": [
                    {"attribute": "visual_impact", "stars": 1},
                    {"attribute": "soft_energy", "stars": 5},
                ],
            },
            {
                "item_id": "B",
                "disliked": True,
                "attribute_ratings": [
                    {"attribute": "visual_impact", "stars": 4},
                ],
            },
        ],
    }
    payload.update(overrides)
    return Engine3Request.model_validate(payload)


def test_star_mapping_is_exact():
    assert STAR_TO_WEIGHT == {1: -1.0, 2: -0.5, 3: 0.0, 4: 0.5, 5: 1.0}


def test_frontend_attributes_are_explicit_and_match_engine02_default_axes():
    resource = Path("engine02/resources/kansei_v1_literature.json")
    engine02_ids = {item["id"] for item in json.loads(resource.read_text(encoding="utf-8"))["design_elements"]}
    assert ENGINE02_AXIS_IDS == engine02_ids
    assert ATTRIBUTE_IDS == {"visual_impact", "polished_formality", "soft_energy"}
    assert len(ATTRIBUTE_DEFINITIONS) == 3
    assert all(definition.label_zh and definition.prompt_zh and definition.effect_zh
               for definition in ATTRIBUTE_DEFINITIONS)
    assert all(generic not in ATTRIBUTE_IDS for generic in {"color", "fit", "material", "style"})
    assert frontend_attribute_catalog()["rating_scale"]["5"] == 1.0


def test_one_batch_contains_every_item_and_averages_attribute_weights():
    result = process_feedback(request())
    assert result.engine02_feedback.chosen_item_ids == ["A"]
    assert result.engine02_feedback.rejected_item_ids == ["B"]
    assert [item.model_dump() for item in result.engine02_feedback.choice_history] == [{
        "shown_item_ids": ["A", "B", "C"],
        "chosen_item_id": "A",
        "rejected_item_ids": ["B"],
    }]
    assert result.window_rounds == [1]
    assert result.engine02_feedback.design_weight_delta == {
        "dark_tone": 0.125,
        "bright_color": -0.125,
        "matte_fabric": 0.125,
        "glossy_fabric": -0.125,
        "visible_logo": -0.25,
        "minimal_design": 0.125,
        "bold_pattern": -0.125,
        "soft_knit": 1.0,
        "athletic_style": 1.0,
    }
    assert len(result.attribute_evidence) == 3
    assert {item.round for item in result.attribute_evidence} == {1}


def test_output_is_real_engine02_feedback_state_input():
    wire = process_feedback(request()).engine02_feedback.model_dump()
    state = FeedbackState.model_validate(wire)
    assert state.chosen_item_ids == ["A"]
    assert state.rejected_item_ids == ["B"]
    assert state.design_weight_delta["soft_knit"] == 1.0
    assert state.design_weight_delta["visible_logo"] == -0.25

    adapted, unusable = feedback_from_engine03(wire)
    assert adapted == wire
    assert unusable == []


def test_neutral_rating_is_audited_but_not_sent_as_delta():
    body = request(item_feedbacks=[{
        "item_id": "C",
        "attribute_ratings": [{"attribute": "polished_formality", "stars": 3}],
    }])
    result = process_feedback(body)
    assert result.engine02_feedback.design_weight_delta == {}
    assert result.attribute_evidence[0].weight == 0.0


def test_rejects_unshown_items_and_unknown_attributes():
    with pytest.raises(ValidationError, match="not shown"):
        request(item_feedbacks=[{"item_id": "Z", "favorited": True}])
    with pytest.raises(ValidationError, match="unknown ENGINE 02 attributes"):
        request(item_feedbacks=[{
            "item_id": "A",
            "attribute_ratings": [{"attribute": "not-real", "stars": 5}],
        }])


def test_rejects_conflicting_or_empty_item_feedback():
    with pytest.raises(ValidationError, match="both favorited and disliked"):
        request(item_feedbacks=[{"item_id": "A", "favorited": True, "disliked": True}])
    with pytest.raises(ValidationError, match="at least one explicit action"):
        request(item_feedbacks=[{"item_id": "A"}])


def test_combines_previous_three_rounds_and_current_round():
    body = request(
        round=4,
        shown_item_ids=["D"],
        item_feedbacks=[{
            "item_id": "D",
            "favorited": True,
            "attribute_ratings": [{"attribute": "soft_energy", "stars": 5}],
        }],
        previous_rounds=[
            {
                "round": 1,
                "shown_item_ids": ["A"],
                "item_feedbacks": [{
                    "item_id": "A",
                    "favorited": True,
                    "attribute_ratings": [{"attribute": "soft_energy", "stars": 1}],
                }],
            },
            {
                "round": 2,
                "shown_item_ids": ["B"],
                "item_feedbacks": [{"item_id": "B", "disliked": True}],
            },
            {
                "round": 3,
                "shown_item_ids": ["C"],
                "item_feedbacks": [{"item_id": "C", "favorited": True}],
            },
        ],
    )

    result = process_feedback(body)

    assert result.window_rounds == [1, 2, 3, 4]
    assert result.engine02_feedback.chosen_item_ids == ["A", "C", "D"]
    assert result.engine02_feedback.rejected_item_ids == ["B"]
    assert len(result.engine02_feedback.choice_history) == 4
    # Round 1 (-1) and round 4 (+1) cancel; neutral aggregate is omitted.
    assert result.engine02_feedback.design_weight_delta == {}
    assert [(item.round, item.weight) for item in result.attribute_evidence] == [(1, -1.0), (4, 1.0)]


def test_rejects_more_than_three_previous_rounds():
    previous = [{
        "round": number,
        "shown_item_ids": [f"item-{number}"],
        "item_feedbacks": [{"item_id": f"item-{number}", "favorited": True}],
    } for number in range(1, 5)]
    with pytest.raises(ValidationError, match="at most 3 items"):
        request(round=5, previous_rounds=previous)


def test_generated_feedback_becomes_design_delta_not_catalog_ids():
    body = request(
        shown_item_ids=["A"],
        shown_generated_item_ids=["generated:s1:r1:cell-2"],
        item_feedbacks=[{
            "item_id": "generated:s1:r1:cell-2",
            "source": "generated",
            "favorited": True,
            "design_attributes": {"fit": "loose", "pattern": "solid", "length": "midi"},
        }],
    )

    result = process_feedback(body)

    assert result.engine02_feedback.chosen_item_ids == []
    assert result.engine02_feedback.rejected_item_ids == []
    assert result.engine02_feedback.design_weight_delta == {
        "relaxed_fit": 0.5,
        "tailored_fit": -0.5,
        "minimal_design": 0.5,
        "bold_pattern": -0.5,
    }
    assert result.engine02_feedback.choice_history == []
    evidence = result.generated_attribute_evidence
    assert [(item.field, bool(item.mapped_axes)) for item in evidence] == [
        ("fit", True), ("pattern", True), ("length", False),
    ]


def test_generated_dislike_reverses_mapped_direction_and_ratings_still_apply():
    body = request(
        shown_item_ids=[],
        shown_generated_item_ids=["generated:s1:r1:cell-1"],
        item_feedbacks=[{
            "item_id": "generated:s1:r1:cell-1",
            "source": "generated",
            "disliked": True,
            "design_attributes": {"material": "satin"},
            "attribute_ratings": [{"attribute": "soft_energy", "stars": 5}],
        }],
    )

    result = process_feedback(body)

    assert result.engine02_feedback.design_weight_delta == {
        "glossy_fabric": -0.5,
        "matte_fabric": 0.5,
        "soft_knit": 1.0,
        "athletic_style": 1.0,
    }
    assert result.attribute_evidence[0].source == "generated"


def test_generated_feedback_requires_shown_id_and_design_metadata():
    with pytest.raises(ValidationError, match="trusted design_attributes"):
        request(
            shown_generated_item_ids=["generated:s1:r1:cell-1"],
            item_feedbacks=[{
                "item_id": "generated:s1:r1:cell-1",
                "source": "generated",
                "favorited": True,
            }],
        )
    with pytest.raises(ValidationError, match="not shown"):
        request(item_feedbacks=[{
            "item_id": "generated:s1:r1:cell-9",
            "source": "generated",
            "favorited": True,
            "design_attributes": {"fit": "loose"},
        }])


def test_catalog_outfit_favorite_sends_both_items_without_fake_choice_record():
    body = request(
        shown_item_ids=["top-A", "bottom-B"],
        item_feedbacks=[],
        outfit_feedbacks=[{
            "outfit_id": "look-1",
            "favorited": True,
            "items": [
                {"zone": "top", "source": "catalog", "item_id": "top-A"},
                {"zone": "bottom", "source": "catalog", "item_id": "bottom-B"},
            ],
        }],
    )

    result = process_feedback(body)

    assert result.engine02_feedback.chosen_item_ids == ["top-A", "bottom-B"]
    assert result.engine02_feedback.design_weight_delta == {}
    assert result.engine02_feedback.choice_history == []
    assert result.outfit_evidence[0].model_dump() == {
        "round": 1,
        "outfit_id": "look-1",
        "catalog_item_ids": ["top-A", "bottom-B"],
        "generated_item_ids": [],
    }


def test_mixed_outfit_maps_generated_member_and_preserves_pair_evidence():
    generated_id = "generated:s1:r1:cell-2"
    body = request(
        shown_item_ids=["top-A"],
        shown_generated_item_ids=[generated_id],
        item_feedbacks=[],
        outfit_feedbacks=[{
            "outfit_id": "look-mixed",
            "favorited": True,
            "items": [
                {"zone": "top", "source": "catalog", "item_id": "top-A"},
                {
                    "zone": "bottom",
                    "source": "generated",
                    "item_id": generated_id,
                    "design_attributes": {"fit": "loose", "pattern": "solid"},
                },
            ],
        }],
    )

    result = process_feedback(body)

    assert result.engine02_feedback.chosen_item_ids == ["top-A"]
    assert generated_id not in result.engine02_feedback.chosen_item_ids
    assert result.engine02_feedback.design_weight_delta == {
        "relaxed_fit": 0.5,
        "tailored_fit": -0.5,
        "minimal_design": 0.5,
        "bold_pattern": -0.5,
    }
    assert result.outfit_evidence[0].catalog_item_ids == ["top-A"]
    assert result.outfit_evidence[0].generated_item_ids == [generated_id]


def test_outfit_requires_one_top_one_bottom_and_shown_items():
    with pytest.raises(ValidationError, match="one top and one bottom"):
        request(
            shown_item_ids=["A", "B"],
            item_feedbacks=[],
            outfit_feedbacks=[{
                "outfit_id": "bad-zones",
                "favorited": True,
                "items": [
                    {"zone": "top", "item_id": "A"},
                    {"zone": "top", "item_id": "B"},
                ],
            }],
        )
    with pytest.raises(ValidationError, match="outfit item ids were not shown"):
        request(
            shown_item_ids=["A"],
            item_feedbacks=[],
            outfit_feedbacks=[{
                "outfit_id": "unshown",
                "favorited": True,
                "items": [
                    {"zone": "top", "item_id": "A"},
                    {"zone": "bottom", "item_id": "missing"},
                ],
            }],
        )
