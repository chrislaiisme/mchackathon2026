"""backend/engine01_intent/main.py::post_feedback() 的單元測試——直接呼叫這支
FastAPI route function（跟 test_concept_image.py 同一套風格），mock
engine03_client.submit_feedback()，驗證驗證規則跟成功路徑的 session 狀態更新。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.engine01_intent import main, session_store
from backend.shared.schemas import (
    FeedbackRequest,
    Intent,
    ItemFeedbackRequest,
    OutfitFeedbackRequest,
    OutfitItemRequest,
    UserProfile,
)


def _outfit(outfit_id: str, top_item_id: str, bottom_item_id: str, *, bottom_source: str = "catalog") -> OutfitFeedbackRequest:
    return OutfitFeedbackRequest(
        outfit_id=outfit_id,
        items=[
            OutfitItemRequest(zone="top", source="catalog", item_id=top_item_id),
            OutfitItemRequest(zone="bottom", source=bottom_source, item_id=bottom_item_id),
        ],
    )

_PROFILE = UserProfile(
    sub="feedback-test-user",
    email="test@example.com",
    onboarding_completed=True,
    created_at="2026-09-19T00:00:00+00:00",
)

_ENGINE02_FEEDBACK = {
    "chosen_item_ids": ["a"],
    "rejected_item_ids": [],
    "choice_history": [],
    "design_weight_delta": {"visual_impact": 0.5},
}


def _new_session_with_shown_items(shown_item_ids: list[str], round_: int = 1) -> session_store.SessionState:
    state = session_store.get_or_create(_PROFILE.sub, None)
    state.intent = Intent()
    state.round = round_
    state.shown_item_ids = shown_item_ids
    session_store.save(_PROFILE.sub, state)
    return state


def test_round_mismatch_returns_409():
    state = _new_session_with_shown_items(["a"], round_=2)
    request = FeedbackRequest(
        session_id=state.session_id, round=1, item_feedbacks=[ItemFeedbackRequest(item_id="a", favorited=True)]
    )

    with pytest.raises(main.HTTPException) as exc_info:
        main.post_feedback(request, _PROFILE, authorization=None)

    assert exc_info.value.status_code == 409


def test_no_items_shown_this_round_returns_409():
    state = _new_session_with_shown_items([], round_=1)
    request = FeedbackRequest(
        session_id=state.session_id, round=1, item_feedbacks=[ItemFeedbackRequest(item_id="a", favorited=True)]
    )

    with pytest.raises(main.HTTPException) as exc_info:
        main.post_feedback(request, _PROFILE, authorization=None)

    assert exc_info.value.status_code == 409


def test_unknown_item_id_returns_422():
    state = _new_session_with_shown_items(["a"], round_=1)
    request = FeedbackRequest(
        session_id=state.session_id,
        round=1,
        item_feedbacks=[ItemFeedbackRequest(item_id="never-shown", favorited=True)],
    )

    with pytest.raises(main.HTTPException) as exc_info:
        main.post_feedback(request, _PROFILE, authorization=None)

    assert exc_info.value.status_code == 422


def test_unknown_outfit_item_id_returns_422():
    state = _new_session_with_shown_items(["a"], round_=1)  # 只展示過 "a"，沒有 "b"
    request = FeedbackRequest(
        session_id=state.session_id,
        round=1,
        outfit_feedbacks=[_outfit("o1", "a", "b")],
    )

    with pytest.raises(main.HTTPException) as exc_info:
        main.post_feedback(request, _PROFILE, authorization=None)

    assert exc_info.value.status_code == 422


def test_all_generated_feedback_returns_422():
    state = _new_session_with_shown_items(["a"], round_=1)
    request = FeedbackRequest(
        session_id=state.session_id,
        round=1,
        item_feedbacks=[ItemFeedbackRequest(item_id="gen-1", source="generated", favorited=True)],
    )

    with pytest.raises(main.HTTPException) as exc_info:
        main.post_feedback(request, _PROFILE, authorization=None)

    assert exc_info.value.status_code == 422


def test_happy_path_stores_pending_feedback_and_trims_history():
    state = _new_session_with_shown_items(["a", "b"], round_=1)
    # 先塞 3 輪舊歷史，確認新的一輪加進去後只留最近 3 筆（裁掉最舊的）。
    state.feedback_rounds = [{"round": -3}, {"round": -2}, {"round": -1}]
    session_store.save(_PROFILE.sub, state)

    request = FeedbackRequest(
        session_id=state.session_id,
        round=1,
        item_feedbacks=[ItemFeedbackRequest(item_id="a", favorited=True)],
        outfit_feedbacks=[_outfit("o1", "a", "b")],
    )

    with patch(
        "backend.engine01_intent.main.engine03_client.submit_feedback",
        return_value={"engine02_feedback": _ENGINE02_FEEDBACK, "attribute_evidence": [{"x": 1}]},
    ) as mock_submit:
        response = main.post_feedback(request, _PROFILE, authorization="Bearer tok")

    assert response.engine02_feedback == _ENGINE02_FEEDBACK
    assert response.attribute_evidence == [{"x": 1}]
    assert response.skipped_generated_item_feedbacks == []

    # Authorization header 有原樣轉發。
    assert mock_submit.call_args.args[3] == "Bearer tok"
    sent_current_round = mock_submit.call_args.args[2]
    assert sent_current_round["item_feedbacks"] == [
        {"item_id": "a", "source": "catalog", "favorited": True, "disliked": False, "attribute_ratings": []}
    ]
    assert sent_current_round["outfit_feedbacks"][0]["items"] == [
        {"zone": "top", "source": "catalog", "item_id": "a"},
        {"zone": "bottom", "source": "catalog", "item_id": "b"},
    ]

    updated_state = session_store.get(_PROFILE.sub, state.session_id)
    assert updated_state.pending_engine02_feedback == _ENGINE02_FEEDBACK
    assert len(updated_state.feedback_rounds) == 3
    assert updated_state.feedback_rounds[0]["round"] == -2  # 最舊的那筆被裁掉了
    assert updated_state.feedback_rounds[-1]["round"] == 1


def test_generated_items_use_trusted_manifest_attributes_when_catalog_items_also_present():
    state = _new_session_with_shown_items(["a"], round_=1)
    generated_id = "generated:test:r1:top:cell-1"
    state.shown_generated_item_ids = [generated_id]
    state.generated_item_design_attributes = {generated_id: {"fit": "loose"}}
    session_store.save(_PROFILE.sub, state)
    request = FeedbackRequest(
        session_id=state.session_id,
        round=1,
        item_feedbacks=[
            ItemFeedbackRequest(item_id="a", favorited=True),
            ItemFeedbackRequest(item_id=generated_id, source="generated", favorited=True),
        ],
    )

    with patch(
        "backend.engine01_intent.main.engine03_client.submit_feedback",
        return_value={"engine02_feedback": _ENGINE02_FEEDBACK},
    ) as mock_submit:
        response = main.post_feedback(request, _PROFILE, authorization=None)

    assert response.skipped_generated_item_feedbacks == []
    sent_current_round = mock_submit.call_args.args[2]
    assert sent_current_round["item_feedbacks"][1] == {
        "item_id": generated_id,
        "source": "generated",
        "favorited": True,
        "disliked": False,
        "attribute_ratings": [],
        "design_attributes": {"fit": "loose"},
    }


def test_mixed_source_outfit_uses_trusted_generated_metadata():
    state = _new_session_with_shown_items(["a"], round_=1)  # 只有 "a" 是資料庫商品
    generated_id = "generated:s1:r1:bottom:cell-2"
    state.shown_generated_item_ids = [generated_id]
    state.generated_item_design_attributes = {generated_id: {"pattern": "solid"}}
    session_store.save(_PROFILE.sub, state)
    request = FeedbackRequest(
        session_id=state.session_id,
        round=1,
        outfit_feedbacks=[_outfit("mixed-outfit", "a", generated_id, bottom_source="generated")],
    )

    with patch(
        "backend.engine01_intent.main.engine03_client.submit_feedback",
        return_value={"engine02_feedback": _ENGINE02_FEEDBACK},
    ) as mock_submit:
        response = main.post_feedback(request, _PROFILE, authorization=None)

    assert response.skipped_generated_outfit_feedbacks == []
    sent_current_round = mock_submit.call_args.args[2]
    assert sent_current_round["outfit_feedbacks"][0]["items"] == [
        {"zone": "top", "source": "catalog", "item_id": "a"},
        {
            "zone": "bottom",
            "source": "generated",
            "item_id": generated_id,
            "design_attributes": {"pattern": "solid"},
        },
    ]


def test_engine03_unreachable_returns_502():
    state = _new_session_with_shown_items(["a"], round_=1)
    request = FeedbackRequest(
        session_id=state.session_id, round=1, item_feedbacks=[ItemFeedbackRequest(item_id="a", favorited=True)]
    )

    with patch("backend.engine01_intent.main.engine03_client.submit_feedback", return_value=None):
        with pytest.raises(main.HTTPException) as exc_info:
            main.post_feedback(request, _PROFILE, authorization=None)

    assert exc_info.value.status_code == 502
