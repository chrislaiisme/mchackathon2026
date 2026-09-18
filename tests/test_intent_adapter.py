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
    # 「粉色」 is a family word, so it expands to the family (Pink, Magenta, Rose, ...) rather
    # than to one value — see test_a_specific_colour_word_is_not_flattened_to_its_family
    assert "Pink" in req.constraints.color.values
    assert req.constraints.occasion.values == ["Smart Casual"]
    # it must land on the channel that is attributed to the user's own sentence, never on
    # feedback (which the card calls 「你上一輪的回饋」)
    assert req.stated_design_steps.get("tailored_fit", 0) > 0
    assert not req.feedback.design_adjust_steps
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


def test_a_card_never_calls_this_round_words_last_round_feedback(monkeypatch):
    """Attribution is the product here: getting the source of a weight wrong is a lie on the card."""
    monkeypatch.setenv("ENGINE02_ENCODER", "hash")
    monkeypatch.setenv("ENGINE02_LLM", "none")
    monkeypatch.setenv("ENGINE02_DEMO", "1")
    from fastapi.testclient import TestClient

    from engine02.api import app

    with TestClient(app) as client:
        b = client.post("/rank", json={"session_id": "a",
                                       "retrieval_text": "面試襯衫，不要有明顯 logo",
                                       "options": {"top_k": 3}}).json()
        text = " ".join(r for it in b["items"] for r in it["reasons"])
        assert "你上一輪的回饋" not in text, text
        shares = [c["need_shares"] for it in b["items"] for c in it["contributions"]]
        assert any("stated_design" in s for s in shares), shares


def test_a_two_season_phrase_keeps_both_seasons():
    """ENGINE 01's own test set contains 「秋冬」; dropping Winter would be silent."""
    from engine02.intent_adapter import intent_to_request

    req, _ = intent_to_request({"item_type": "大衣", "season": "秋冬"}, session_id="t")
    assert set(req.constraints.season.values) == {"Fall", "Winter"}, req.constraints.season.values


def test_a_specific_colour_word_is_not_flattened_to_its_family():
    """「深藍色」 is Navy Blue. Collapsing it to 'Blue' excludes every navy item in the catalog."""
    from pathlib import Path

    from engine02.catalog import Catalog
    from engine02.intent_adapter import intent_to_request

    items = Catalog.load(Path(__file__).resolve().parents[1] / "data" / "catalog" / "kagl").items
    req, _ = intent_to_request({"item_type": "襯衫", "colors": ["深藍色"]},
                               session_id="t", catalog_items=items)
    assert req.constraints.color.values == ["Navy Blue"], req.constraints.color.values

    # a bare family word means the whole family, so it must INCLUDE the navy items
    req2, _ = intent_to_request({"item_type": "襯衫", "colors": ["藍色"]},
                                session_id="t", catalog_items=items)
    assert "Navy Blue" in req2.constraints.color.values, req2.constraints.color.values
    assert len(req2.constraints.color.values) > 1


def test_the_framework_service_layer_runs(monkeypatch):
    """`backend/engine02_retrieval` is the seam the team's framework actually depends on."""
    monkeypatch.setenv("ENGINE02_ENCODER", "hash")
    monkeypatch.setenv("ENGINE02_LLM", "none")
    monkeypatch.setenv("ENGINE02_DEMO", "1")
    from fastapi.testclient import TestClient

    from backend.engine02_retrieval.main import app

    with TestClient(app) as client:
        h = client.get("/health").json()
        assert h["service"] == "engine02_retrieval" and h["n_items"] > 0
        r = client.post("/retrieve", json={"session_id": "fw", "round": 1,
                                           "intent": {"item_type": "襯衫", "colors": ["白色"]}})
        assert r.status_code == 200, r.text[:200]
        body = r.json()
        assert body["products"] and 0.0 <= body["match_score"] <= 1.0
        assert body["concept_image"] is None          # backend/generation owns it
        # the full ENGINE 02 API must still answer under the mount
        assert client.get("/engine02/vocabulary").status_code == 200
        assert client.post("/engine02/rank", json={"session_id": "fw",
                                                   "retrieval_text": "shirt"}).status_code == 200


def test_auth_is_optional_and_never_crashes_without_a_secret(monkeypatch):
    """backend/shared/auth.py raises without SESSION_SECRET; importing it eagerly would take the
    whole service down on a machine with no .env."""
    monkeypatch.setenv("ENGINE02_ENCODER", "hash")
    monkeypatch.setenv("ENGINE02_LLM", "none")
    monkeypatch.setenv("ENGINE02_DEMO", "1")
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    from fastapi.testclient import TestClient

    from backend.engine02_retrieval.main import app

    with TestClient(app) as client:
        r = client.post("/retrieve", json={"session_id": "anon", "intent": {"item_type": "襯衫"}},
                        headers={"Authorization": "Bearer not-a-real-token"})
        assert r.status_code == 200
        assert r.json()["engine02"]["authenticated"] is False


def test_a_negated_style_keyword_moves_the_ranking_the_right_way():
    """ENGINE 01 puts whole phrases in style_keywords: 「不要太正式」 asks for LESS formal.

    Scoring it as +formal would move the ranking the opposite way from what the user said, and
    then explain that confidently — the worst failure mode this project has.
    """
    from engine02.intent_adapter import intent_to_request

    neg, _ = intent_to_request({"item_type": "襯衫", "style_keywords": ["不要太正式"]}, session_id="t")
    pos, _ = intent_to_request({"item_type": "襯衫", "style_keywords": ["正式"]}, session_id="t")
    assert neg.stated_design_steps["formal_style"] < 0 < pos.stated_design_steps["formal_style"]
    # and the rejected word must not reach the encoder either (NegBench: CLIP is near chance on it)
    assert "formal" not in (neg.retrieval_text or "").lower().split()


def test_english_keywords_match_on_word_boundaries():
    from engine02.intent_adapter import intent_to_request

    a, _ = intent_to_request({"item_type": "襯衫", "style_keywords": ["slim fit", "plain"]},
                             session_id="t")
    assert a.stated_design_steps.get("tailored_fit", 0) > 0
    assert a.stated_design_steps.get("minimal_design", 0) > 0

    b, _ = intent_to_request({"item_type": "襯衫", "style_keywords": ["avoid bold pattern"]},
                             session_id="t")
    assert b.stated_design_steps.get("bold_pattern", 0) < 0

    c, _ = intent_to_request({"item_type": "襯衫", "style_keywords": ["informal"]}, session_id="t")
    assert "formal_style" not in c.stated_design_steps, c.stated_design_steps


def test_engine03_feedback_shape_is_accepted_and_enforced(monkeypatch):
    """ENGINE 03 declares attribute scores + free text; we keep a ledger. Round 2 must not need
    either side to rewrite its contract, and 「不要黑色」 typed into a feedback box must bite."""
    monkeypatch.setenv("ENGINE02_ENCODER", "hash")
    monkeypatch.setenv("ENGINE02_LLM", "none")
    monkeypatch.setenv("ENGINE02_DEMO", "1")
    from fastapi.testclient import TestClient

    from backend.engine02_retrieval.main import app

    with TestClient(app) as client:
        intent = {"item_type": "襯衫", "occasion": "上班"}
        client.post("/retrieve", json={"session_id": "loop", "round": 1, "intent": intent})
        r2 = client.post("/retrieve", json={
            "session_id": "loop", "round": 2, "intent": intent, "prev_intent": intent,
            "feedback": {"session_id": "loop", "round": 1, "target": "recommended",
                         "attribute_scores": [{"attribute": "正式感", "score": -1},
                                              {"attribute": "香味", "score": 1}],
                         "free_text": "太像上班族了，不要黑色"}}).json()
        colors = [str(p["attributes"].get("color", "")).lower() for p in r2["products"]]
        assert "black" not in colors, colors
        assert r2["engine02"]["metrics"]["excluded_value_hits"] == 0
        # an attribute we have no axis for is reported, not silently swallowed
        assert any("香味" in u for u in r2["engine02"]["unresolved_from_intent"])
        # the goalpost control is present once prev_intent is supplied
        assert "vs_previous_intent" in r2["engine02"]["match_score_detail"]


def test_our_own_feedback_shape_still_passes_through(monkeypatch):
    monkeypatch.setenv("ENGINE02_ENCODER", "hash")
    monkeypatch.setenv("ENGINE02_LLM", "none")
    monkeypatch.setenv("ENGINE02_DEMO", "1")
    from fastapi.testclient import TestClient

    from backend.engine02_retrieval.main import app

    with TestClient(app) as client:
        first = client.post("/retrieve", json={"session_id": "p", "intent": {"item_type": "襯衫"}}).json()
        shown = [p["product_id"] for p in first["products"]]
        r = client.post("/retrieve", json={
            "session_id": "p", "round": 2, "intent": {"item_type": "襯衫"},
            "feedback": {"choice_history": [{"shown_item_ids": shown, "chosen_item_id": shown[0]}],
                         "excluded_item_ids": [shown[1]]}}).json()
        ids = [p["product_id"] for p in r["products"]]
        assert shown[1] not in ids, "an excluded item came back"
