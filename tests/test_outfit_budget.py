"""「幫我準備一套正式場合的服裝，預算 3,000 元」 — the brief's own example sentence.

The budget is for the whole outfit. A per-item filter at 3,000 returns four garments costing
3,000 each, and 20% of the score is 「搭配是否完整可購買」.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "catalog" / "kagl" / "items.parquet"

SLOTS = {
    "top": [("t1", "白襯衫", 1200, 3.1), ("t2", "特價襯衫", 400, 2.2), ("t3", "設計師襯衫", 2600, 3.4)],
    "bottom": [("b1", "西裝褲", 1500, 2.9), ("b2", "基本款長褲", 600, 2.1)],
    "shoes": [("s1", "皮鞋", 1800, 2.8), ("s2", "簡約球鞋", 900, 2.4), ("s3", "未標價", None, 2.9)],
}


def test_the_budget_is_for_the_whole_outfit():
    from engine02.outfit_budget import plan_outfit

    plan = plan_outfit(SLOTS, 3000).as_dict()
    assert plan["complete"] and plan["total_price"] <= 3000
    assert len(plan["items"]) == 3, plan
    assert plan["remaining"] == pytest.approx(3000 - plan["total_price"])


def test_it_maximises_the_ranking_score_not_cheapness():
    from engine02.outfit_budget import plan_outfit

    generous = plan_outfit(SLOTS, 3000).as_dict()
    tight = plan_outfit(SLOTS, 2000).as_dict()
    # with room, it keeps the better-scoring top; with less, it trades down
    assert generous["total_price"] > tight["total_price"]
    tops = {p["slot"]: p["title"] for p in generous["items"]}
    assert tops["top"] == "白襯衫"
    assert {p["slot"]: p["title"] for p in tight["items"]}["top"] == "特價襯衫"


def test_an_impossible_budget_says_so_instead_of_dropping_a_slot():
    from engine02.outfit_budget import plan_outfit

    plan = plan_outfit(SLOTS, 1500).as_dict()
    assert plan["complete"] is False
    assert not plan["items"]
    # and it says how far off the user is, using the real cheapest combination
    assert "1900" in plan["note"], plan["note"]


def test_an_unpriced_item_is_never_treated_as_free():
    from engine02.outfit_budget import plan_outfit

    plan = plan_outfit(SLOTS, 3000).as_dict()
    assert plan["unpriced_skipped"] == 1
    assert "未標價" not in [p["title"] for p in plan["items"]]


def test_no_budget_means_best_score_per_slot():
    from engine02.outfit_budget import plan_outfit

    plan = plan_outfit(SLOTS, None).as_dict()
    assert {p["title"] for p in plan["items"]} == {"設計師襯衫", "西裝褲", "皮鞋"}
    assert plan["budget"] is None and plan["remaining"] is None


@pytest.mark.skipif(not CATALOG.exists(), reason="needs data/catalog/kagl")
def test_complete_look_items_carry_a_quantified_reason(monkeypatch):
    """The one screen that is literally about 「為什麼這樣搭」 must say it, with numbers."""
    monkeypatch.setenv("ENGINE02_ENCODER", "hash")
    monkeypatch.setenv("ENGINE02_LLM", "none")
    monkeypatch.setenv("ENGINE02_DEMO", "1")
    from fastapi.testclient import TestClient

    from engine02.api import app

    with TestClient(app) as client:
        anchor = client.post("/rank", json={"session_id": "o", "retrieval_text": "white shirt",
                                            "options": {"top_k": 1}}).json()["items"][0]["item_id"]
        b = client.post("/complete-look", json={"anchor_item_ids": [anchor], "n_categories": 2,
                                                "k": 3}).json()
        for slate in b["slates"]:
            for it in slate["items"]:
                assert it["reason"], it
                # every clause has to carry a number, not an adjective
                assert any(ch.isdigit() for ch in it["reason"]), it["reason"]
                assert "NPMI" in it["reason"]


@pytest.mark.skipif(not CATALOG.exists(), reason="needs data/catalog/kagl")
def test_a_budget_on_a_priceless_catalog_does_not_cost_the_user_their_colour(monkeypatch):
    """`ok = ~isnan(price)` emptied the pool, and the ladder then relaxed colour, season and
    occasion — which all come BEFORE budget:drop — to recover from a constraint that never
    applied."""
    monkeypatch.setenv("ENGINE02_ENCODER", "hash")
    monkeypatch.setenv("ENGINE02_LLM", "none")
    monkeypatch.setenv("ENGINE02_DEMO", "1")
    from fastapi.testclient import TestClient

    from engine02.api import app

    with TestClient(app) as client:
        b = client.post("/rank", json={
            "session_id": "b", "retrieval_text": "formal shirt",
            "constraints": {"category": "tops", "color": ["White"],
                            "budget": {"state": "value", "max_price": 3000}},
            "options": {"top_k": 5}}).json()
        rep = b["constraint_report"]
        assert b["items"], "a budget on a priceless catalog must not empty the result"
        assert not rep["relaxed"], rep["relaxed"]
        assert rep["applied"].get("color") == ["White"]
        assert "budget_unavailable" in rep["applied"]
        assert any("預算" in w for w in rep["input_warnings"]), rep["input_warnings"]


FIXTURE = ROOT / "data" / "catalog" / "kagl_priced_fixture" / "items.parquet"


@pytest.mark.skipif(not FIXTURE.exists(),
                    reason="run scripts/make_priced_fixture.py (synthetic prices, tests only)")
def test_a_budget_actually_filters_when_the_catalog_has_prices(monkeypatch):
    """The adapter used to turn a budget straight into a warning, so it could never work."""
    monkeypatch.setenv("ENGINE02_CATALOG", "data/catalog/kagl_priced_fixture")
    monkeypatch.setenv("ENGINE02_ENCODER", "hash")
    monkeypatch.setenv("ENGINE02_LLM", "none")
    monkeypatch.setenv("ENGINE02_DEMO", "1")
    from fastapi.testclient import TestClient

    from engine02.api import app

    with TestClient(app) as client:
        b = client.post("/intent/rank", json={
            "session_id": "p", "message": "預算 1500 的上衣",
            "intent": {"item_type": "上衣", "budget_max": 1500}}).json()
        rep = b["engine02"]["constraint_report"]
        assert rep["applied"].get("budget"), rep["applied"]
        assert not rep["relaxed"], rep["relaxed"]
        assert b["products"], "a reachable budget must still return cards"
        # the price has to reach the card: 「可購買」 is a scored criterion
        prices = [float(p["attributes"]["price"]) for p in b["products"]]
        assert prices and all(p <= 1500 for p in prices), prices


@pytest.mark.skipif(not FIXTURE.exists(), reason="needs the priced fixture")
def test_an_unreachable_budget_relaxes_visibly_rather_than_returning_nothing(monkeypatch):
    monkeypatch.setenv("ENGINE02_CATALOG", "data/catalog/kagl_priced_fixture")
    monkeypatch.setenv("ENGINE02_ENCODER", "hash")
    monkeypatch.setenv("ENGINE02_LLM", "none")
    monkeypatch.setenv("ENGINE02_DEMO", "1")
    from fastapi.testclient import TestClient

    from engine02.api import app

    with TestClient(app) as client:
        b = client.post("/intent/rank", json={
            "session_id": "p", "message": "預算 100 的上衣",
            "intent": {"item_type": "上衣", "budget_max": 100}}).json()
        rep = b["engine02"]["constraint_report"]
        assert b["products"], "an impossible budget must not blank the screen"
        assert any("budget" in r for r in rep["relaxed"]), rep["relaxed"]
