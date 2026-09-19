"""backend/engine01_intent/recommend.py 的單元測試——mock engine02_client，
不打真的 ENGINE02，也不碰真的檔案系統／網路（參考圖解析另外測）。
"""

from __future__ import annotations

from unittest.mock import patch

from backend.engine01_intent import recommend
from backend.shared.schemas import Intent, ProductCard, RetrievalResult, UserProfile

_PROFILE = UserProfile(
    sub="user123",
    email="test@example.com",
    gender="女",
    style_preferences=["簡約"],
    onboarding_completed=True,
    created_at="2026-09-19T00:00:00+00:00",
)


def _card(product_id: str, category: str) -> ProductCard:
    return ProductCard(
        product_id=product_id,
        image_url=f"https://example.com/{product_id}.jpg",
        title=product_id,
        attributes={"category": category},
        score=0.9,
        reason="測試用",
    )


def _result(products: list[ProductCard]) -> RetrievalResult:
    return RetrievalResult(session_id="s1", round=1, products=products, match_score=0.8)


def test_outfit_requested_calls_engine02_twice_and_marks_both_zones_requested():
    intent = Intent(outfit_requested=True, colors=["黑色"])

    with patch(
        "backend.engine01_intent.recommend.engine02_client.intent_rank",
        side_effect=[_result([_card("top1", "top")]), _result([_card("bottom1", "bottom")])],
    ) as mock_intent_rank:
        result = recommend.build_zoned_recommendation(
            intent, "s1", 1, ["我想要一套黑色的"], None, _PROFILE
        )

    assert mock_intent_rank.call_count == 2
    assert result.outfit_requested is True
    zones_by_name = {slate.zone: slate for slate in result.zones}
    assert zones_by_name["top"].requested is True
    assert zones_by_name["bottom"].requested is True
    assert zones_by_name["top"].products[0].product_id == "top1"
    assert zones_by_name["bottom"].products[0].product_id == "bottom1"


def test_single_item_non_dress_marks_one_requested_one_default():
    intent = Intent(item_type="外套", colors=["黑色"])

    with patch(
        "backend.engine01_intent.recommend.engine02_client.intent_rank",
        side_effect=[_result([_card("outer1", "outerwear")]), _result([_card("bottom1", "bottom")])],
    ) as mock_intent_rank:
        result = recommend.build_zoned_recommendation(
            intent, "s1", 1, ["我想要一件黑色外套"], None, _PROFILE
        )

    assert mock_intent_rank.call_count == 2
    assert result.outfit_requested is False
    zones_by_name = {slate.zone: slate for slate in result.zones}
    # outerwear 依 zones.zone_of() 歸上衣區
    assert zones_by_name["top"].requested is True
    assert zones_by_name["top"].products[0].product_id == "outer1"
    assert zones_by_name["bottom"].requested is False
    assert zones_by_name["bottom"].products[0].product_id == "bottom1"


def test_dress_leaves_bottom_zone_empty_without_calling_engine02_again():
    intent = Intent(item_type="洋裝", colors=["粉色"])

    with patch(
        "backend.engine01_intent.recommend.engine02_client.intent_rank",
        return_value=_result([_card("dress1", "dress")]),
    ) as mock_intent_rank:
        result = recommend.build_zoned_recommendation(
            intent, "s1", 1, ["我想要一件粉色洋裝"], None, _PROFILE
        )

    assert mock_intent_rank.call_count == 1  # 下身區不會再多打一次
    zones_by_name = {slate.zone: slate for slate in result.zones}
    assert zones_by_name["top"].requested is True
    assert zones_by_name["top"].products[0].product_id == "dress1"
    assert zones_by_name["bottom"].requested is False
    assert zones_by_name["bottom"].products == []


def test_engine02_failure_returns_empty_products_not_an_exception():
    intent = Intent(item_type="外套")

    with patch(
        "backend.engine01_intent.recommend.engine02_client.intent_rank", return_value=None
    ):
        result = recommend.build_zoned_recommendation(
            intent, "s1", 1, ["我想要一件外套"], None, _PROFILE
        )

    for slate in result.zones:
        assert slate.products == []


def test_reference_image_uses_visual_search():
    intent = Intent(colors=["黑色"])

    with patch(
        "backend.engine01_intent.recommend._resolve_image_bytes", return_value=b"fake-bytes"
    ), patch(
        "backend.engine01_intent.recommend.engine02_client.visual_search",
        return_value=[_card("visual1", "top")],
    ) as mock_visual_search, patch(
        "backend.engine01_intent.recommend.engine02_client.intent_rank",
        return_value=_result([_card("bottom1", "bottom")]),
    ):
        result = recommend.build_zoned_recommendation(
            intent, "s1", 1, ["幫我找這張圖的衣服"], "/files/user123/abc.jpg", _PROFILE
        )

    mock_visual_search.assert_called_once()
    zones_by_name = {slate.zone: slate for slate in result.zones}
    assert zones_by_name["top"].requested is True
    assert zones_by_name["top"].products[0].product_id == "visual1"


def test_style_keywords_fallback_uses_profile_without_mutating_session_intent():
    intent = Intent(item_type="外套")  # style_keywords 這輪是空的
    assert intent.style_keywords == []

    with patch(
        "backend.engine01_intent.recommend.engine02_client.intent_rank", return_value=_result([])
    ) as mock_intent_rank:
        recommend.build_zoned_recommendation(intent, "s1", 1, ["我想要一件外套"], None, _PROFILE)

    first_call_intent = mock_intent_rank.call_args_list[0].args[0]
    assert first_call_intent.style_keywords == _PROFILE.style_preferences
    # 原本 session 存的 intent 本身不能被動到
    assert intent.style_keywords == []


def test_gender_is_passed_to_intent_rank():
    intent = Intent(item_type="外套")

    with patch(
        "backend.engine01_intent.recommend.engine02_client.intent_rank", return_value=_result([])
    ) as mock_intent_rank:
        recommend.build_zoned_recommendation(intent, "s1", 1, ["我想要一件外套"], None, _PROFILE)

    assert mock_intent_rank.call_args_list[0].kwargs["gender"] == "女"
