"""backend/engine01_intent/style_me.py 的單元測試——mock engine02_client／llm_client，
驗證三條路徑：complete_look 成功、退回 intent_rank＋LLM 理由、兩者都拿不到商品。
"""

from __future__ import annotations

from unittest.mock import patch

from backend.engine01_intent import style_me
from backend.shared.schemas import Intent, ProductCard, RetrievalResult, UserProfile

_PROFILE = UserProfile(
    sub="user123",
    email="test@example.com",
    onboarding_completed=True,
    created_at="2026-09-19T00:00:00+00:00",
)


def _card(product_id: str) -> ProductCard:
    return ProductCard(
        product_id=product_id,
        image_url=f"https://example.com/{product_id}.jpg",
        title=product_id,
        score=0.9,
        reason="測試用",
    )


def test_complete_look_success_is_used_directly():
    with patch(
        "backend.engine01_intent.style_me.engine02_client.complete_look",
        return_value=[_card("bottom1")],
    ) as mock_complete_look, patch(
        "backend.engine01_intent.style_me.engine02_client.intent_rank"
    ) as mock_intent_rank, patch(
        "backend.engine01_intent.style_me.llm_client.generate_freeform_text"
    ) as mock_llm:
        result = style_me.build_styled_complement(
            "s1", 1, ["我想要黑色外套"], Intent(colors=["黑色"]), _PROFILE, "top1", "top",
        )

    mock_complete_look.assert_called_once_with("top1", "bottom", k=1)
    mock_intent_rank.assert_not_called()  # complete_look 成功就不用退回備援
    mock_llm.assert_not_called()
    assert result == ("bottom", _card("bottom1"))


def test_falls_back_to_intent_rank_and_llm_reason_when_complete_look_fails():
    with patch(
        "backend.engine01_intent.style_me.engine02_client.complete_look", return_value=None
    ), patch(
        "backend.engine01_intent.style_me.engine02_client.intent_rank",
        return_value=RetrievalResult(session_id="s1", round=1, products=[_card("bottom2")], match_score=0.5),
    ) as mock_intent_rank, patch(
        "backend.engine01_intent.style_me.llm_client.generate_freeform_text",
        return_value="深藍色跟黑色是同色系，穿起來很和諧",
    ) as mock_llm:
        result = style_me.build_styled_complement(
            "s1", 1, ["我想要黑色外套"], Intent(colors=["黑色"]), _PROFILE, "generated-top-id", "top",
        )

    mock_intent_rank.assert_called_once()
    mock_llm.assert_called_once()
    assert result is not None
    zone, complement = result
    assert zone == "bottom"
    assert complement.product_id == "bottom2"
    assert complement.reason == "深藍色跟黑色是同色系，穿起來很和諧"
    assert complement.explanation_source == "llm_fallback"


def test_llm_failure_still_returns_a_generic_reason():
    with patch(
        "backend.engine01_intent.style_me.engine02_client.complete_look", return_value=None
    ), patch(
        "backend.engine01_intent.style_me.engine02_client.intent_rank",
        return_value=RetrievalResult(session_id="s1", round=1, products=[_card("bottom3")], match_score=0.5),
    ), patch(
        "backend.engine01_intent.style_me.llm_client.generate_freeform_text", return_value=None
    ):
        result = style_me.build_styled_complement(
            "s1", 1, [], Intent(), _PROFILE, "generated-top-id", "top",
        )

    assert result is not None
    _, complement = result
    assert complement.reason  # 不是空字串
    assert complement.explanation_source == "llm_fallback"


def test_returns_none_when_no_candidates_at_all():
    with patch(
        "backend.engine01_intent.style_me.engine02_client.complete_look", return_value=None
    ), patch(
        "backend.engine01_intent.style_me.engine02_client.intent_rank", return_value=None
    ):
        result = style_me.build_styled_complement(
            "s1", 1, [], Intent(), _PROFILE, "top1", "top",
        )

    assert result is None
