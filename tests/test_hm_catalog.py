"""The GPU-filled H&M catalog: provenance rules, vocabulary, and that the surprise slot can use it.
Skipped when data/catalog/hm_filled is absent (a fresh clone before fetch_catalog_images.py)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
CAT = ROOT / "data" / "catalog" / "hm_filled"
ITEMS = CAT / "items.parquet"
pytestmark = pytest.mark.skipif(not ITEMS.exists(), reason="needs data/catalog/hm_filled (see data/README.md)")


@pytest.fixture(scope="module")
def items():
    return pd.read_parquet(ITEMS)


def test_model_filled_fields_are_marked_and_human_labels_kept(items):
    src = items["attr_source"].map(json.loads)
    # H&M labels colour and gender; those must still say "dataset"
    assert (src.map(lambda s: s.get("gender")) == "dataset").all()
    has_colour = items["color"].notna()
    assert (src[has_colour].map(lambda s: s.get("color")).isin(["dataset", "vlm:Qwen3-VL-8B-Instruct"])).all()
    # every season/occasion value came from the model, and says so
    filled = items["season"].notna()
    assert filled.mean() > 0.9
    assert (src[filled].map(lambda s: s.get("season")).str.startswith("vlm:")).all()


def test_values_are_in_the_catalog_vocabulary(items):
    from engine02.attribute_fill import COLOR_TO_FAMILY
    assert set(items["season"].dropna()) <= {"Spring", "Summer", "Fall", "Winter"}
    assert set(items["occasion"].dropna()) <= {"Casual", "Formal", "Smart Casual", "Sports", "Travel", "Ethnic"}
    assert all(str(c).lower() in COLOR_TO_FAMILY for c in items["color"].dropna())
    assert set(items["boldness"].dropna().astype(int)) <= {0, 1, 2, 3}
    assert set(items["category"]) <= {"top", "bottom", "dress", "outerwear", "shoes", "bag"}


def test_report_lists_every_dropped_item_with_a_reason():
    rep = json.loads((CAT / "vlm_fill_report.json").read_text(encoding="utf-8"))
    assert rep["dropped"]["n"] == len(rep["dropped"]["items"])
    assert all(i["vlm_product"] in {"size_chart", "multipack", "not_apparel"} for i in rep["dropped"]["items"])


@pytest.mark.skipif(not (CAT / "images").exists(), reason="images not fetched yet")
def test_surprise_slot_works_on_this_catalog(monkeypatch):
    monkeypatch.setenv("ENGINE02_CATALOG", str(CAT))
    monkeypatch.setenv("ENGINE02_ENCODER", "hash")
    monkeypatch.setenv("ENGINE02_LLM", "none")
    monkeypatch.setenv("ENGINE02_DEMO", "1")
    from fastapi.testclient import TestClient
    from engine02.api import app
    with TestClient(app) as c:
        r = c.post("/rank", json={"session_id": "t", "retrieval_text": "party dress", "options": {"top_k": 5},
                                  "context": {"surprise": True}}).json()
    s = r["diversification"]["surprise"]
    assert s["requested"] is True
    if s["applied"]:
        card = next(i for i in r["items"] if i["item_id"] == s["item_id"])
        assert card["promoted_by_surprise"] and s["boldness"] >= 2
        assert abs(sum(x["contribution"] for x in card["contributions"]) - card["score"]) < 1e-6
    else:
        assert s["reason_if_not_applied"]
