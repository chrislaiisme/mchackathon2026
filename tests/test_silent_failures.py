"""The three ways a request could look perfect while half of it was thrown away.

An adversarial re-audit (docs/research/completeness-audit-2.md) found that an unknown `need_id`,
an unknown design element and a Chinese colour word all produced HTTP 200 with a faithful score
decomposition — and no sign anywhere that the implicit-need side had been switched off or that the
colour filter had been dropped. These tests exist so that cannot come back silently.
"""

import base64
import io
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "catalog" / "kagl" / "items.parquet"
pytestmark = pytest.mark.skipif(not CATALOG.exists(),
                                reason="needs data/catalog/kagl (scripts/prepare_catalog.py)")


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("ENGINE02_ENCODER", "hash")
    monkeypatch.setenv("ENGINE02_LLM", "none")
    monkeypatch.setenv("ENGINE02_DEMO", "1")
    from fastapi.testclient import TestClient

    from engine02.api import app

    with TestClient(app) as c:
        yield c


def test_unknown_need_id_is_reported(client):
    r = client.post("/rank", json={"session_id": "t", "retrieval_text": "shirt",
                                   "needs": {"trustworthy": 0.6, "no_such_need": 0.9}})
    assert r.status_code == 200
    warnings = r.json()["constraint_report"]["input_warnings"]
    assert any("no_such_need" in w for w in warnings), warnings


def test_unknown_design_element_is_reported(client):
    r = client.post("/rank", json={"session_id": "t", "retrieval_text": "shirt",
                                   "feedback": {"design_adjust_steps": {"no_such_element": 1}}})
    assert r.status_code == 200
    warnings = r.json()["constraint_report"]["input_warnings"]
    assert any("no_such_element" in w for w in warnings), warnings


def test_chinese_colour_is_normalised_and_declared(client):
    r = client.post("/rank", json={"session_id": "t", "retrieval_text": "shirt",
                                   "constraints": {"color": ["藏青"]}})
    assert r.status_code == 200
    body = r.json()
    rep = body["constraint_report"]
    # the colour survives as a real hard constraint instead of falling through the ladder
    assert rep["applied"].get("color"), rep
    assert not rep["relaxed"], rep["relaxed"]
    assert body["metrics"]["hard_constraint_satisfaction"] == 1.0
    # and the rewrite is declared, not done behind the caller's back
    assert any(g["your_words"] == "藏青" for g in rep["grounded_terms"]), rep["grounded_terms"]


def test_visual_search_malformed_constraints_is_422_not_500(client):
    buf = io.BytesIO()
    pytest.importorskip("PIL")
    from PIL import Image

    Image.new("RGB", (8, 8), (30, 40, 90)).save(buf, "PNG")
    img = base64.b64encode(buf.getvalue()).decode()
    r = client.post("/visual-search", json={"image_base64": img, "profile": False,
                                            "constraints": {"category": {"state": "maybe"}}})
    assert r.status_code == 422, r.status_code
    assert "constraints" in str(r.json()).lower()
