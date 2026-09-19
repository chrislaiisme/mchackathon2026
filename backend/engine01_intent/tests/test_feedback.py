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


def test_generated_items_are_skipped_not_rejected_when_catalog_items_also_present():
    state = _new_session_with_shown_items(["a"], round_=1)
    request = FeedbackRequest(
        session_id=state.session_id,
        round=1,
        item_feedbacks=[
            ItemFeedbackRequest(item_id="a", favorited=True),
            ItemFeedbackRequest(item_id="gen-1", source="generated", favorited=True),
        ],
    )

    with patch(
        "backend.engine01_intent.main.engine03_client.submit_feedback",
        return_value={"engine02_feedback": _ENGINE02_FEEDBACK},
    ):
        response = main.post_feedback(request, _PROFILE, authorization=None)

    assert response.skipped_generated_item_feedbacks == ["gen-1"]


def test_mixed_source_outfit_is_skipped_not_partially_sent():
    # 2026-09-19：整套裡有一件是 source="generated" 就整筆 outfit 跳過，不會只挑
    # 資料庫那一件單獨送出去（半套的整套喜歡語意會失真）——design_attributes
    # 詞彙映射還沒人跟 ENGINE02／生成模組負責人確認過。
    state = _new_session_with_shown_items(["a"], round_=1)  # 只有 "a" 是資料庫商品
    request = FeedbackRequest(
        session_id=state.session_id,
        round=1,
        outfit_feedbacks=[_outfit("mixed-outfit", "a", "generated:s1:r1:cell-2", bottom_source="generated")],
    )

    with pytest.raises(main.HTTPException) as exc_info:
        main.post_feedback(request, _PROFILE, authorization=None)

    # 沒有其他任何回饋可送（catalog_feedbacks 跟 outfit_feedbacks 都是空的），
    # 所以會落到「沒有可送出的回饋」那條 422，不是去查 shown_item_ids 噴錯。
    assert exc_info.value.status_code == 422


def test_mixed_source_outfit_is_reported_when_other_feedback_still_sends():
    state = _new_session_with_shown_items(["a"], round_=1)
    request = FeedbackRequest(
        session_id=state.session_id,
        round=1,
        item_feedbacks=[ItemFeedbackRequest(item_id="a", favorited=True)],
        outfit_feedbacks=[_outfit("mixed-outfit", "a", "generated:s1:r1:cell-2", bottom_source="generated")],
    )

    with patch(
        "backend.engine01_intent.main.engine03_client.submit_feedback",
        return_value={"engine02_feedback": _ENGINE02_FEEDBACK},
    ) as mock_submit:
        response = main.post_feedback(request, _PROFILE, authorization=None)

    assert response.skipped_generated_outfit_feedbacks == ["mixed-outfit"]
    sent_current_round = mock_submit.call_args.args[2]
    assert sent_current_round["outfit_feedbacks"] == []  # 整筆被跳過，不是只送一半


def test_engine03_unreachable_returns_502():
    state = _new_session_with_shown_items(["a"], round_=1)
    request = FeedbackRequest(
        session_id=state.session_id, round=1, item_feedbacks=[ItemFeedbackRequest(item_id="a", favorited=True)]
    )

    with patch("backend.engine01_intent.main.engine03_client.submit_feedback", return_value=None):
        with pytest.raises(main.HTTPException) as exc_info:
            main.post_feedback(request, _PROFILE, authorization=None)

    assert exc_info.value.status_code == 502
