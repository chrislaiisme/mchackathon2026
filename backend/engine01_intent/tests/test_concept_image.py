"""backend/engine01_intent/main.py::post_concept_image() 的單元測試——直接呼叫這支
FastAPI route function（繞過 HTTP／依賴注入層，跟這個專案其他測試一樣偏好測純函式），
mock generate_concepts()，驗證三種分支：連身裙、單品＋填充、整套請求。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.engine01_intent import main, session_store
from backend.shared.schemas import Intent, UserProfile

_PROFILE = UserProfile(
    sub="concept-image-test-user",
    email="test@example.com",
    onboarding_completed=True,
    created_at="2026-09-19T00:00:00+00:00",
)


def _new_session(intent: Intent) -> session_store.SessionState:
    state = session_store.get_or_create(_PROFILE.sub, None)
    state.intent = intent
    session_store.save(_PROFILE.sub, state)
    return state


def _fake_generate_concepts(session_id, round, intent_dict, *, cells, model, dry_run):
    # session_id 帶著 __top／__bottom 尾綴，用它反推是哪一區被呼叫，這樣可以
    # 用回傳內容確認「哪一區真的呼叫了生成」而不是只看有沒有呼叫。
    zone = session_id.rsplit("__", 1)[-1]
    return {"cells": [{"prompt_fragment": f"{zone}:{intent_dict.get('item_type')}"}], "prompt_used": "", "grid_image": None}


def test_dress_only_generates_one_zone_and_leaves_the_other_empty():
    state = _new_session(Intent(item_type="連身裙", colors=["黑色"]))

    with patch("backend.engine01_intent.main.generate_concepts", side_effect=_fake_generate_concepts) as mock_gen:
        result = main.post_concept_image(
            main.ConceptImageRequest(session_id=state.session_id, dry_run=True), _PROFILE
        )

    mock_gen.assert_called_once()  # 只呼叫一次——另一區完全沒進生成管線
    assert result["zones"]["top"]["cells"][0]["prompt_fragment"] == "top:連身裙"
    assert result["zones"]["bottom"]["cells"] == []


def test_single_item_generates_both_zones_with_requested_zone_keeping_its_item_type():
    state = _new_session(Intent(item_type="白襯衫", colors=["白色"]))

    with patch("backend.engine01_intent.main.generate_concepts", side_effect=_fake_generate_concepts) as mock_gen:
        result = main.post_concept_image(
            main.ConceptImageRequest(session_id=state.session_id, dry_run=True), _PROFILE
        )

    assert mock_gen.call_count == 2  # 兩區都真的生成
    assert result["zones"]["top"]["cells"][0]["prompt_fragment"] == "top:白襯衫"
    # 填充區（bottom）的 item_type 被換成代表性品項，不是使用者原話。
    assert result["zones"]["bottom"]["cells"][0]["prompt_fragment"] == "bottom:褲子"


def test_single_item_bottom_zone_keeps_its_item_type_too():
    state = _new_session(Intent(item_type="牛仔褲"))

    with patch("backend.engine01_intent.main.generate_concepts", side_effect=_fake_generate_concepts):
        result = main.post_concept_image(
            main.ConceptImageRequest(session_id=state.session_id, dry_run=True), _PROFILE
        )

    assert result["zones"]["bottom"]["cells"][0]["prompt_fragment"] == "bottom:牛仔褲"
    assert result["zones"]["top"]["cells"][0]["prompt_fragment"] == "top:上衣"


def test_outfit_requested_generates_both_zones_with_default_categories():
    state = _new_session(Intent(outfit_requested=True))

    with patch("backend.engine01_intent.main.generate_concepts", side_effect=_fake_generate_concepts) as mock_gen:
        result = main.post_concept_image(
            main.ConceptImageRequest(session_id=state.session_id, dry_run=True), _PROFILE
        )

    assert mock_gen.call_count == 2
    assert result["zones"]["top"]["cells"][0]["prompt_fragment"] == "top:上衣"
    assert result["zones"]["bottom"]["cells"][0]["prompt_fragment"] == "bottom:褲子"


def test_neither_item_type_nor_outfit_requested_returns_409():
    state = _new_session(Intent())

    with pytest.raises(main.HTTPException) as exc_info:
        main.post_concept_image(main.ConceptImageRequest(session_id=state.session_id, dry_run=True), _PROFILE)

    assert exc_info.value.status_code == 409
