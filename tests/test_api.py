import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "catalog" / "kagl" / "items.parquet"


@pytest.mark.skipif(not CATALOG.exists(), reason="needs data/catalog/kagl (scripts/prepare_catalog.py)")
def test_api_rank_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("ENGINE02_ENCODER", "hash")
    monkeypatch.setenv("ENGINE02_LLM", "none")
    from fastapi.testclient import TestClient

    from engine02.api import app

    with TestClient(app) as client:
        h = client.get("/health").json()
        assert h["status"] == "ok" and h["n_items"] > 0
        vocab = client.get("/vocabulary").json()
        assert "Shirts" in vocab["subcategory"]
        k = client.get("/kansei").json()
        need = next(iter(k["needs"]))
        body = {
            "session_id": "demo",
            "retrieval_text": "men navy blue shirts for formal",
            "constraints": {"category": {"state": "value", "values": ["top"]},
                            "gender": {"state": "value", "values": ["Men"]}},
            "needs": [{"need_id": need, "prob": 0.7}],
        }
        r = client.post("/rank", json=body)
        assert r.status_code == 200, r.text
        data = r.json()
        assert len(data["items"]) == 5
        for it in data["items"]:
            assert abs(sum(c["contribution"] for c in it["contributions"]) - it["score"]) < 1e-6
        assert client.get(f"/images/{data['items'][0]['item_id']}").status_code == 200
        assert client.post("/rank", json={**body, "options": {"arm": "nope"}}).status_code == 400
        assert data["diversification"]["method"] == "dpp"
        assert client.get("/health").json()["kansei_version"] == "kansei_v1_literature"
        look = client.post("/complete-look", json={"anchor_item_ids": [data["items"][0]["item_id"]], "k": 3})
        assert look.status_code == 200, look.text
        assert look.json()["method"] == "similarity" and look.json()["slates"]


@pytest.mark.skipif(not CATALOG.exists(), reason="needs data/catalog/kagl (scripts/prepare_catalog.py)")
def test_api_view_panels_and_helpers(tmp_path, monkeypatch):
    """The §7 panels, the concept-image neighbours and the supply side go out over HTTP."""
    monkeypatch.setenv("ENGINE02_ENCODER", "hash")
    monkeypatch.setenv("ENGINE02_LLM", "none")
    monkeypatch.setenv("ENGINE02_TRENDS", "1")
    from fastapi.testclient import TestClient

    from engine02.api import app

    with TestClient(app) as client:
        need = next(iter(client.get("/kansei").json()["needs"]))
        body = {"session_id": "demo", "retrieval_text": "men navy blue shirts for formal",
                "constraints": {"category": {"state": "value", "values": ["top"]}},
                "needs": [{"need_id": need, "prob": 0.7}]}
        v = client.post("/view", json={"request": body})
        assert v.status_code == 200, v.text
        out = v.json()
        assert out["view"]["session_id"] == "demo"
        assert out["view"]["diversity"]["k"] == len(out["response"]["items"])
        assert out["view"]["round_diff"] is None  # no previous round given
        assert "trend_badges" in out  # display only

        # a second round: the diff panel must appear
        v2 = client.post("/view", json={"request": {**body, "round": 1}, "prev_request": body,
                                        "prev_response": out["response"]})
        assert v2.status_code == 200, v2.text
        assert v2.json()["view"]["round_diff"] is not None

        sup = client.get("/needs/supply", params={"threshold": 0.5}).json()
        assert need in sup["supply"] and 0.0 <= sup["supply"][need] <= 1.0
        assert client.get("/needs/supply", params={"arm": "nope"}).status_code == 400

        dim = len(client.get(f"/items/{out['response']['items'][0]['item_id']}").json()["design_scores"])
        assert dim > 0
        emb = client.post("/concept-image/nearest", json={"embedding": [0.0], "k": 3})
        assert emb.status_code == 400  # wrong dimensionality is caught, not silently broadcast

        tr = client.get("/trends").json()
        assert tr["loaded"] and tr["used_in_ranking"] is False and tr["keywords"]
