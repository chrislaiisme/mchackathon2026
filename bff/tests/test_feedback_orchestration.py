import pytest

from bff import main
from bff.images.concept import _cells_payload


@pytest.fixture(autouse=True)
def clear_sessions():
    main._SESSIONS.clear()
    yield
    main._SESSIONS.clear()


def test_feedback_reuses_engine1_intent_and_calls_engine2_once(monkeypatch):
    calls: list[tuple[str, dict]] = []

    def fake_post(url, payload, headers=None):
        calls.append((url, payload))
        if url.endswith("/intent"):
            return {
                "session_id": "s1",
                "round": 1,
                "intent": {"item_type": "上衣", "occasion": "面試"},
                "clarifying_questions": [],
            }
        if url.endswith("/feedback"):
            assert payload["shown_item_ids"] == ["A", "B"]
            assert payload["shown_generated_item_ids"] == []
            assert payload["previous_rounds"] == []
            return {
                "session_id": "s1",
                "round": 1,
                "engine02_feedback": {
                    "chosen_item_ids": ["A"],
                    "rejected_item_ids": ["B"],
                    "choice_history": [{
                        "shown_item_ids": ["A", "B"],
                        "chosen_item_id": "A",
                        "rejected_item_ids": ["B"],
                    }],
                    "design_weight_delta": {"formal_style": -0.5},
                },
                "attribute_evidence": [],
            }
        if url.endswith("/retrieve"):
            products = [
                {"product_id": "A", "title": "A"},
                {"product_id": "B", "title": "B"},
            ] if payload["round"] == 1 else [{"product_id": "C", "title": "C"}]
            return {"session_id": "s1", "round": payload["round"], "products": products}
        raise AssertionError(url)

    monkeypatch.setattr(main, "_post", fake_post)

    first = main.run_round(main.RoundRequest(message="面試上衣"))
    assert first["intent"] == {"item_type": "上衣", "occasion": "面試"}
    assert main._SESSIONS["s1"].shown_item_ids == ["A", "B"]

    before_feedback = len(calls)
    second = main.feedback(main.FeedbackRequest(
        session_id="s1",
        round=1,
        item_feedbacks=[
            {"item_id": "A", "favorited": True,
             "attribute_ratings": [{"attribute": "polished_formality", "stars": 2}]},
            {"item_id": "B", "disliked": True},
        ],
    ))

    feedback_calls = calls[before_feedback:]
    assert len([call for call in feedback_calls if call[0].endswith("/feedback")]) == 1
    engine2_calls = [call for call in feedback_calls if call[0].endswith("/retrieve")]
    assert len(engine2_calls) == 1
    engine2_payload = engine2_calls[0][1]
    assert engine2_payload["intent"] == {"item_type": "上衣", "occasion": "面試"}
    assert engine2_payload["message"] is None
    assert engine2_payload["round"] == 2
    assert engine2_payload["feedback"] == {
        "chosen_item_ids": ["A"],
        "rejected_item_ids": ["B"],
        "choice_history": [{
            "shown_item_ids": ["A", "B"],
            "chosen_item_id": "A",
            "rejected_item_ids": ["B"],
        }],
        "design_weight_delta": {"formal_style": -0.5},
    }
    assert second["round"] == 2
    assert main._SESSIONS["s1"].shown_item_ids == ["C"]
    assert main._SESSIONS["s1"].feedback_rounds == [{
        "round": 1,
        "shown_item_ids": ["A", "B"],
        "shown_generated_item_ids": [],
        "item_feedbacks": [
            {"item_id": "A", "source": "catalog", "favorited": True,
             "attribute_ratings": [{"attribute": "polished_formality", "stars": 2}]},
            {"item_id": "B", "source": "catalog", "disliked": True},
        ],
        "outfit_feedbacks": [],
    }]


def test_feedback_rejects_stale_round(monkeypatch):
    main._SESSIONS["s1"] = main.Session(
        session_id="s1", round=2, intent={"item_type": "上衣"}, shown_item_ids=["A"])
    with pytest.raises(main.HTTPException) as exc:
        main.feedback(main.FeedbackRequest(
            session_id="s1", round=1,
            item_feedbacks=[{"item_id": "A", "favorited": True}],
        ))
    assert exc.value.status_code == 409


def test_feedback_attributes_are_proxied(monkeypatch):
    expected = {"rating_scale": {"1": -1.0}, "attributes": [{"id": "dark_tone"}]}
    monkeypatch.setattr(main, "_get", lambda url, headers=None: expected)
    assert main.feedback_attributes(None) == expected


def test_feedback_sends_only_previous_three_rounds_to_engine3(monkeypatch):
    previous_rounds = [{
        "round": number,
        "shown_item_ids": [f"old-{number}"],
        "item_feedbacks": [{"item_id": f"old-{number}", "favorited": True}],
    } for number in range(1, 4)]
    main._SESSIONS["s1"] = main.Session(
        session_id="s1",
        round=4,
        intent={"item_type": "top"},
        shown_item_ids=["current"],
        feedback_rounds=previous_rounds,
    )
    calls: list[tuple[str, dict]] = []

    def fake_post(url, payload, headers=None):
        calls.append((url, payload))
        if url.endswith("/feedback"):
            assert [item["round"] for item in payload["previous_rounds"]] == [1, 2, 3]
            assert payload["round"] == 4
            return {
                "engine02_feedback": {
                    "chosen_item_ids": ["old-1", "old-2", "old-3", "current"],
                    "rejected_item_ids": [],
                    "choice_history": [],
                    "design_weight_delta": {},
                }
            }
        if url.endswith("/retrieve"):
            return {"products": [{"product_id": "next"}]}
        raise AssertionError(url)

    monkeypatch.setattr(main, "_post", fake_post)
    main.feedback(main.FeedbackRequest(
        session_id="s1",
        round=4,
        item_feedbacks=[{"item_id": "current", "favorited": True}],
    ))

    assert [item["round"] for item in main._SESSIONS["s1"].feedback_rounds] == [2, 3, 4]
    engine2_payload = next(payload for url, payload in calls if url.endswith("/retrieve"))
    assert engine2_payload["feedback"]["chosen_item_ids"] == ["old-1", "old-2", "old-3", "current"]


def test_generated_feedback_uses_server_metadata_and_never_sends_generated_id_to_engine2(monkeypatch):
    generated_id = "generated:s1:r1:cell-2"
    main._SESSIONS["s1"] = main.Session(
        session_id="s1",
        round=1,
        intent={"item_type": "top"},
        shown_item_ids=["A"],
        shown_generated_item_ids=[generated_id],
        generated_items={generated_id: {
            "item_id": generated_id,
            "round": 1,
            "image_url": "/generated/cell-2.png",
            "design_attributes": {"fit": "loose"},
        }},
    )
    calls: list[tuple[str, dict]] = []

    def fake_post(url, payload, headers=None):
        calls.append((url, payload))
        if url.endswith("/feedback"):
            item = payload["item_feedbacks"][0]
            assert item["design_attributes"] == {"fit": "loose"}
            assert payload["shown_generated_item_ids"] == [generated_id]
            return {"engine02_feedback": {
                "chosen_item_ids": [],
                "rejected_item_ids": [],
                "choice_history": [],
                "design_weight_delta": {"relaxed_fit": 0.5, "tailored_fit": -0.5},
            }}
        if url.endswith("/retrieve"):
            assert generated_id not in payload["feedback"]["chosen_item_ids"]
            assert generated_id not in payload["feedback"]["rejected_item_ids"]
            return {"products": [{"product_id": "next"}]}
        raise AssertionError(url)

    monkeypatch.setattr(main, "_post", fake_post)
    main.feedback(main.FeedbackRequest(
        session_id="s1",
        round=1,
        item_feedbacks=[{
            "item_id": generated_id,
            "source": "generated",
            "favorited": True,
            "design_attributes": {"fit": "tight"},
        }],
    ))

    assert main._SESSIONS["s1"].shown_generated_item_ids == []


def test_concept_image_registers_stable_generated_ids(monkeypatch):
    main._SESSIONS["s1"] = main.Session(
        session_id="s1", round=2, intent={"item_type": "top"}, rounds=[{"round": 2}])
    monkeypatch.setattr(main, "generate_concepts", lambda *args, **kwargs: {
        "grid_image": "/generated/grid.png",
        "prompt_used": "prompt",
        "cells": [{
            "index": 1,
            "image_url": "/generated/cell_1.png",
            "design_attributes": {"pattern": "striped"},
        }],
    })

    result = main.concept_image(main.ConceptImageRequest(session_id="s1"))

    generated_id = "generated:s1:r2:cell-1"
    assert result["concepts"]["cells"][0]["generated_item_id"] == generated_id
    assert main._SESSIONS["s1"].shown_generated_item_ids == [generated_id]
    assert main._SESSIONS["s1"].generated_items[generated_id]["design_attributes"] == {
        "pattern": "striped"
    }


def test_generated_cell_uses_only_varied_attributes_as_feedback_evidence():
    cells = _cells_payload({"cells": [{
        "index": 1,
        "keywords": {"occasion": "interview", "fit": "loose", "pattern": "striped"},
        "varied_attribute": "fit,pattern",
    }]}, sliced=False)

    assert cells[0]["design_attributes"] == {"fit": "loose", "pattern": "striped"}
    assert "occasion" not in cells[0]["design_attributes"]


def test_mixed_outfit_uses_trusted_generated_metadata_and_calls_engine2(monkeypatch):
    generated_id = "generated:s1:r2:cell-1"
    main._SESSIONS["s1"] = main.Session(
        session_id="s1",
        round=2,
        intent={"item_type": "套裝", "occasion": "日常"},
        shown_item_ids=["top-A"],
        shown_generated_item_ids=[generated_id],
        generated_items={generated_id: {
            "item_id": generated_id,
            "round": 2,
            "design_attributes": {"fit": "loose", "pattern": "solid"},
        }},
    )
    calls: list[tuple[str, dict]] = []

    def fake_post(url, payload, headers=None):
        calls.append((url, payload))
        if url.endswith("/feedback"):
            assert payload["item_feedbacks"] == []
            outfit = payload["outfit_feedbacks"][0]
            assert outfit["items"][1]["design_attributes"] == {
                "fit": "loose", "pattern": "solid",
            }
            return {
                "engine02_feedback": {
                    "chosen_item_ids": ["top-A"],
                    "rejected_item_ids": [],
                    "choice_history": [],
                    "design_weight_delta": {
                        "relaxed_fit": 0.5,
                        "tailored_fit": -0.5,
                        "minimal_design": 0.5,
                        "bold_pattern": -0.5,
                    },
                },
                "outfit_evidence": [{
                    "round": 2,
                    "outfit_id": "look-1",
                    "catalog_item_ids": ["top-A"],
                    "generated_item_ids": [generated_id],
                }],
            }
        if url.endswith("/retrieve"):
            assert payload["intent"] == {"item_type": "套裝", "occasion": "日常"}
            assert payload["feedback"]["chosen_item_ids"] == ["top-A"]
            assert generated_id not in payload["feedback"]["chosen_item_ids"]
            return {"products": [{"product_id": "next"}]}
        raise AssertionError(url)

    monkeypatch.setattr(main, "_post", fake_post)
    result = main.feedback(main.FeedbackRequest(
        session_id="s1",
        round=2,
        outfit_feedbacks=[{
            "outfit_id": "look-1",
            "favorited": True,
            "items": [
                {"zone": "top", "source": "catalog", "item_id": "top-A"},
                {
                    "zone": "bottom",
                    "source": "generated",
                    "item_id": generated_id,
                    "design_attributes": {"fit": "tight"},
                },
            ],
        }],
    ))

    assert result["outfit_evidence"][0]["outfit_id"] == "look-1"
    assert main._SESSIONS["s1"].feedback_rounds[0]["outfit_feedbacks"][0]["items"][1][
        "design_attributes"
    ] == {"fit": "loose", "pattern": "solid"}
