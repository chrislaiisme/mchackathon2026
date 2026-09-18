"""ENGINE 01 → ENGINE 02: the boundary where Chinese free text meets an English catalog.

The fixtures below are taken verbatim from ENGINE 01's own accuracy suite
(`backend/engine01_intent/tests/test_cases.json` on branch `engine01-intent`), so if ENGINE 01
keeps passing its tests, these are the payloads ENGINE 02 will actually receive on the day.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "catalog" / "kagl" / "items.parquet"
pytestmark = pytest.mark.skipif(not CATALOG.exists(),
                                reason="needs data/catalog/kagl (scripts/prepare_catalog.py)")

# verbatim from ENGINE 01's test_cases.json
E01_CASES = [
    {"message": "我想要一件簡約風格的黑色正式外套",
     "expected_intent": {"item_type": "外套", "colors": ["黑色"], "occasion": "正式場合",
                         "style_keywords": ["簡約"]}},
    {"message": "夏天想找一件透氣一點的白色襯衫，上班穿",
     "expected_intent": {"item_type": "襯衫", "colors": ["白色"], "occasion": "上班",
                         "season": "夏天", "style_keywords": ["透氣"]}},
    {"message": "約會要穿的洋裝，粉色，版型要修身",
     "expected_intent": {"item_type": "洋裝", "colors": ["粉色"], "occasion": "約會",
                         "fit": "修身"}},
    {"message": "圓領的棉質T恤，白色或米色都可以",
     "expected_intent": {"item_type": "T恤", "colors": ["白色", "米色"], "material": "棉",
                         "collar": "圓領"}},
    {"message": "預算大概兩千元以內，想要一件牛仔外套",
     "expected_intent": {"item_type": "牛仔外套", "budget_max": 2000}},
]


def test_every_engine01_case_produces_a_usable_request():
    from engine02.intent_adapter import intent_to_request

    for case in E01_CASES:
        req, unresolved = intent_to_request(case["expected_intent"], session_id="t",
                                            message=case["message"])
        assert req.retrieval_text, f"no retrieval text for {case['message']}"
        # the caption handed to an English encoder must not be mostly Chinese
        han = sum("一" <= ch <= "鿿" for ch in req.retrieval_text)
        assert han <= len(req.retrieval_text) * 0.4, (case["message"], req.retrieval_text)
        assert req.utterances and req.utterances[0] == case["message"]
        assert isinstance(unresolved, list)


def test_chinese_values_become_catalog_values():
    from engine02.intent_adapter import intent_to_request

    req, unresolved = intent_to_request(
        {"item_type": "洋裝", "colors": ["粉色"], "occasion": "約會", "fit": "修身"},
        session_id="t")
    assert req.constraints.category.values, "「洋裝」 must resolve through the taxonomy"
    assert req.constraints.color.values == ["Pink"]
    assert req.constraints.occasion.values == ["Smart Casual"]
    assert req.feedback.design_adjust_steps.get("tailored_fit", 0) > 0
    assert not unresolved


def test_inferred_fields_stay_soft():
    """ENGINE 01 marks what GPT inferred; an inferred slot must not shrink the candidate pool."""
    from engine02.contracts import SlotState
    from engine02.intent_adapter import intent_to_request

    req, _ = intent_to_request({"item_type": "襯衫", "season": "冬天",
                                "inferred_fields": ["season"]}, session_id="t")
    assert req.constraints.season.state == SlotState.INFERRED
    assert not req.constraints.season.is_hard()
    assert req.constraints.category.state == SlotState.VALUE


def test_an_unusable_constraint_is_reported_not_faked():
    from engine02.intent_adapter import intent_to_request

    req, unresolved = intent_to_request({"item_type": "外套", "budget_max": 2000}, session_id="t")
    assert any("預算" in u for u in unresolved), unresolved
    assert req.constraints.budget is None or not getattr(req.constraints.budget, "values", None)

    # an occasion this catalog does not have must not become a hard filter
    req2, unresolved2 = intent_to_request({"item_type": "襯衫", "occasion": "太空漫步"},
                                          session_id="t")
    assert not req2.constraints.occasion.values
    assert any("太空漫步" in u for u in unresolved2), unresolved2


def test_end_to_end_engine01_payload_returns_cards(monkeypatch):
    """The whole boundary: ENGINE 01's Chinese intent in, ranked cards out."""
    monkeypatch.setenv("ENGINE02_ENCODER", "hash")
    monkeypatch.setenv("ENGINE02_LLM", "none")
    monkeypatch.setenv("ENGINE02_DEMO", "1")
    from fastapi.testclient import TestClient

    from engine02.api import app

    with TestClient(app) as client:
        for case in E01_CASES:
            r = client.post("/intent/rank", json={"session_id": "e2e", "round": 0,
                                                  "message": case["message"],
                                                  "intent": case["expected_intent"]})
            assert r.status_code == 200, (case["message"], r.text[:200])
            body = r.json()
            assert body["products"], case["message"]
            for p in body["products"]:
                assert p["product_id"] and p["title"] and p["image_url"]
                assert "score" in p and "reason" in p
            assert 0.0 <= body["match_score"] <= 1.0
            # the explainability must survive the conversion to the team's card shape
            assert body["engine02"]["items"][0]["contributions"]


def test_match_score_can_go_down(monkeypatch):
    """A number that only ever rises is not a match score."""
    monkeypatch.setenv("ENGINE02_ENCODER", "hash")
    monkeypatch.setenv("ENGINE02_LLM", "none")
    monkeypatch.setenv("ENGINE02_DEMO", "1")
    from fastapi.testclient import TestClient

    from engine02.api import app

    with TestClient(app) as client:
        easy = client.post("/intent/rank", json={"session_id": "m", "intent": {"item_type": "襯衫"}}).json()
        # ask for something this catalog cannot deliver alongside the rest
        hard = client.post("/intent/rank", json={"session_id": "m", "intent": {
            "item_type": "襯衫", "colors": ["紫色"], "occasion": "登山", "season": "冬天",
            "fit": "寬鬆", "pattern": "印花"}}).json()
        assert hard["match_score"] <= easy["match_score"], (easy["match_score"], hard["match_score"])
