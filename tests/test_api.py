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


@pytest.mark.skipif(not CATALOG.exists(), reason="needs data/catalog/kagl (scripts/prepare_catalog.py)")
def test_demo_mode_refuses_llm_paraphrase(monkeypatch):
    """A live demo cannot afford a network call per card; the server decides, not the client."""
    monkeypatch.setenv("ENGINE02_ENCODER", "hash")
    monkeypatch.setenv("ENGINE02_LLM", "none")
    monkeypatch.setenv("ENGINE02_DEMO", "1")
    import importlib

    import engine02.api as api

    importlib.reload(api)
    from fastapi.testclient import TestClient

    with TestClient(api.app) as client:
        assert client.get("/health").json()["demo_mode"] is True
        r = client.post("/rank", json={"session_id": "d", "retrieval_text": "navy shirt",
                                       "options": {"top_k": 3, "explain_with_llm": True}})
        assert r.status_code == 200
        assert {it["explanation_source"] for it in r.json()["items"]} == {"template"}
    monkeypatch.delenv("ENGINE02_DEMO")
    importlib.reload(api)


def test_llm_budget_gives_up_after_one_failure():
    """Cards after a failure must not each wait for their own timeout."""
    from engine02.explain import LlmBudget

    calls = []

    def flaky(prompt: str) -> str:
        calls.append(prompt)
        raise TimeoutError("network gone")

    b = LlmBudget(flaky, total_s=5.0)
    with pytest.raises(TimeoutError):
        b("first")
    with pytest.raises(TimeoutError):
        b("second")
    assert len(calls) == 1, "the second card should not have called out again"


@pytest.mark.skipif(not CATALOG.exists(), reason="needs data/catalog/kagl (scripts/prepare_catalog.py)")
def test_visual_search_profiles_and_retrieves(monkeypatch, tmp_path):
    """A photo in, a design-element profile and ranked cards out — same encoder, no new model."""
    import base64

    monkeypatch.setenv("ENGINE02_ENCODER", "hash")
    monkeypatch.setenv("ENGINE02_LLM", "none")
    from fastapi.testclient import TestClient
    from PIL import Image

    from engine02.api import app

    img = tmp_path / "shot.png"
    Image.new("RGB", (64, 64), (20, 30, 90)).save(img)
    b64 = base64.b64encode(img.read_bytes()).decode()

    with TestClient(app) as client:
        r = client.post("/visual-search", json={"image_base64": b64, "top_k": 4})
        assert r.status_code == 200, r.text
        d = r.json()
        assert len(d["response"]["items"]) == 4
        assert d["profile"] and {"element", "label", "z", "percentile"} <= set(d["profile"][0])
        assert all(0.0 <= p["percentile"] <= 1.0 for p in d["profile"])
        assert abs(d["profile"][0]["z"]) >= abs(d["profile"][-1]["z"]), "sorted by how unusual it is"
        # a data: URL prefix is tolerated, junk is a 400 rather than a 500
        assert client.post("/visual-search", json={"image_base64": f"data:image/png;base64,{b64}"}
                           ).status_code == 200
        assert client.post("/visual-search", json={"image_base64": "not base64!!"}).status_code == 400
        assert client.post("/visual-search", json={"image_base64": ""}).status_code == 400


@pytest.mark.skipif(not CATALOG.exists(), reason="needs data/catalog/kagl (scripts/prepare_catalog.py)")
def test_visual_search_normalises_real_world_uploads(monkeypatch, tmp_path):
    """Phone photos and screenshots: rotation, transparency, CMYK and oversize must not silently
    change the embedding (or hang the demo)."""
    import base64
    import io

    monkeypatch.setenv("ENGINE02_ENCODER", "hash")
    monkeypatch.setenv("ENGINE02_LLM", "none")
    from fastapi.testclient import TestClient
    from PIL import Image

    from engine02.api import app

    def b64(im, fmt="PNG"):
        buf = io.BytesIO()
        im.save(buf, format=fmt)
        return base64.b64encode(buf.getvalue()).decode()

    rgba = Image.new("RGBA", (80, 60), (200, 40, 40, 0))       # fully transparent
    cmyk = Image.new("CMYK", (80, 60), (0, 0, 0, 0))
    wide = Image.new("RGB", (2400, 1800), (10, 80, 160))        # larger than the 1600 cap

    with TestClient(app) as client:
        for name, payload in (("rgba", b64(rgba)), ("cmyk", b64(cmyk, "JPEG")), ("wide", b64(wide))):
            r = client.post("/visual-search", json={"image_base64": payload, "top_k": 3})
            assert r.status_code == 200, f"{name}: {r.text[:200]}"
            assert len(r.json()["response"]["items"]) == 3

        # not an image at all → 400 with a reason, not a 500
        junk = base64.b64encode(b"this is a text file, not a picture").decode()
        bad = client.post("/visual-search", json={"image_base64": junk})
        assert bad.status_code == 400 and "could not read the image" in bad.json()["detail"]

        # oversize is refused before decoding
        monkeypatch.setenv("ENGINE02_MAX_UPLOAD_MB", "0")
        import importlib

        import engine02.api as api

        importlib.reload(api)
        with TestClient(api.app) as c2:
            assert c2.post("/visual-search", json={"image_base64": b64(wide)}).status_code == 413
    monkeypatch.delenv("ENGINE02_MAX_UPLOAD_MB")
