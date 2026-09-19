"""backend/engine01_intent/recommend.py 的單元測試——mock engine02_client，
不打真的 ENGINE02，也不碰真的檔案系統／網路（參考圖解析另外測）。
"""

from __future__ import annotations

from unittest.mock import patch

from backend.engine01_intent import recommend
from backend.shared.schemas import (
    Intent,
    ProductCard,
    RetrievalResult,
    UserProfile,
    ZonedRecommendationResult,
    ZoneSlate,
)

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


def test_resolve_reference_image_only_trusts_user_upload():
    # 2026-09-19 真人測試發現：Pinterest fallback 的圖跟使用者自己上傳的圖
    # 曾經被一視同仁送進 visual_search()，圖片比對結果蓋掉使用者打的文字意圖
    # （打「商務白色襯衫」，上衣區被換成一雙襪子）。這支函式就是那次修正——
    # 只有 user_upload 才放行，pinterest／none 一律當沒有參考圖。
    assert recommend.resolve_reference_image_for_retrieval("/files/user123/abc.jpg", "user_upload") == (
        "/files/user123/abc.jpg"
    )
    assert recommend.resolve_reference_image_for_retrieval("https://pinterest.example/pin.jpg", "pinterest") is None
    assert recommend.resolve_reference_image_for_retrieval(None, "none") is None


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


def test_feedback_and_prev_intent_are_passed_to_every_intent_rank_call():
    # 2026-09-19：接上 ENGINE03 之後，同一輪的 feedback／prev_intent 要原封不動
    # 套用到全部呼叫點——單品情境有兩次（主分區＋代查的另一分區），整套情境
    # 也有兩次（上衣＋下身），不能只套用在其中一次。
    intent = Intent(outfit_requested=True, colors=["黑色"])
    feedback = {"chosen_item_ids": ["a"], "rejected_item_ids": [], "choice_history": [], "design_weight_delta": {}}
    prev_intent = {"item_type": "外套"}

    with patch(
        "backend.engine01_intent.recommend.engine02_client.intent_rank",
        side_effect=[_result([_card("top1", "top")]), _result([_card("bottom1", "bottom")])],
    ) as mock_intent_rank:
        recommend.build_zoned_recommendation(
            intent, "s1", 1, ["我想要一套黑色的"], None, _PROFILE,
            feedback=feedback, prev_intent=prev_intent,
        )

    assert mock_intent_rank.call_count == 2
    for call in mock_intent_rank.call_args_list:
        assert call.kwargs["feedback"] == feedback
        assert call.kwargs["prev_intent"] == prev_intent


def test_match_score_is_populated_on_every_zone_slate():
    # ZoneSlate.match_score 是這次新加的欄位（現場要秀「回饋前 62% → 回饋後
    # 89%」的量化證明），確認每個 zone 真的把 RetrievalResult.match_score 帶出來，
    # 不是停在預設值 0.0。
    intent = Intent(outfit_requested=True, colors=["黑色"])

    def _scored_result(score: float, products: list[ProductCard]) -> RetrievalResult:
        return RetrievalResult(session_id="s1", round=1, products=products, match_score=score)

    with patch(
        "backend.engine01_intent.recommend.engine02_client.intent_rank",
        side_effect=[_scored_result(0.62, [_card("top1", "top")]), _scored_result(0.89, [_card("bottom1", "bottom")])],
    ):
        result = recommend.build_zoned_recommendation(
            intent, "s1", 1, ["我想要一套黑色的"], None, _PROFILE
        )

    zones_by_name = {slate.zone: slate for slate in result.zones}
    assert zones_by_name["top"].match_score == 0.62
    assert zones_by_name["bottom"].match_score == 0.89


def test_dress_zone_leaves_other_zone_match_score_at_default():
    # 連身裙的下身區沒有真的查詢過（is_dress 規則直接留空），match_score
    # 要維持預設值 0.0，不是查詢結果——不能讓一個沒查過的分區看起來像是
    # 「查到了但符合度是 0」。
    intent = Intent(item_type="洋裝")

    with patch(
        "backend.engine01_intent.recommend.engine02_client.intent_rank",
        return_value=RetrievalResult(
            session_id="s1", round=1, products=[_card("dress1", "dress")], match_score=0.7
        ),
    ):
        result = recommend.build_zoned_recommendation(
            intent, "s1", 1, ["我想要一件洋裝"], None, _PROFILE
        )

    zones_by_name = {slate.zone: slate for slate in result.zones}
    assert zones_by_name["top"].match_score == 0.7
    assert zones_by_name["bottom"].match_score == 0.0
    assert zones_by_name["bottom"].products == []


def test_build_profile_context_includes_style_preferences_and_intent_fields():
    # 2026-09-20：改寫推薦理由的 LLM 呼叫原本完全看不到 onboarding 長期偏好跟
    # 這輪結構化 Intent，只能靠原始對話字串籠統判斷語氣——這支函式把兩者組成
    # 一段文字，讓改寫出來的句子能點名使用者自己的偏好。
    intent = Intent(colors=["黑色"], occasion="上班", season="秋天", style_keywords=["簡約", "俐落"])
    context = recommend.build_profile_context(intent, _PROFILE)

    assert "簡約" in context  # 來自 UserProfile.style_preferences
    assert "黑色" in context
    assert "上班" in context
    assert "秋天" in context
    assert "俐落" in context


def test_build_profile_context_omits_empty_fields():
    # 沒有值的欄位不該出現在輸出裡（不要硬湊出一堆空白欄位餵給 LLM）。
    intent = Intent()
    profile = UserProfile(
        sub="u2", email="u2@example.com", onboarding_completed=True, created_at="2026-09-19T00:00:00+00:00"
    )
    context = recommend.build_profile_context(intent, profile)

    assert context == ""


def test_apply_natural_language_reasons_passes_profile_context_through():
    result = ZonedRecommendationResult(
        session_id="s1", round=1, outfit_requested=False,
        zones=[ZoneSlate(zone="top", requested=True, products=[_card("a", "top")])],
    )

    with patch(
        "backend.engine01_intent.recommend.llm_client.rewrite_recommendation_reasons", return_value=None
    ) as mock_rewrite:
        recommend.apply_natural_language_reasons(result, "context text", "profile text")

    assert mock_rewrite.call_args.args[2] == "profile text"
