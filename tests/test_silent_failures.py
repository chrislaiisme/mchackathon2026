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


def test_facets_do_not_change_the_ranking(client):
    """The facet panel is a reading of the list, never a reordering of it."""
    body = {"session_id": "t", "retrieval_text": "a shirt for an interview", "options": {"top_k": 50}}
    ranked = [it["item_id"] for it in client.post("/rank", json=body).json()["items"]]
    f = client.post("/facets", json={"request": body, "n_pool": 50}).json()
    assert f["n_ranked"] == len(ranked)
    panel = f["facets"]
    grouped = [i for g in panel["groups"] for i in g["item_ids"]]
    # every ranked item lands in exactly one group, and no item is invented
    assert sorted(grouped) == sorted(ranked)
    # and the ranking itself is untouched by having asked for facets
    assert [it["item_id"] for it in client.post("/rank", json=body).json()["items"]] == ranked
    assert panel["groups"] and panel["axis"]
    # groups are ordered along the axis, and each is a real group
    means = [g["mean_z"] for g in panel["groups"]]
    assert means == sorted(means)
    assert all(g["n"] >= 1 for g in panel["groups"])


def test_profile_is_a_prior_that_real_feedback_outvotes(client):
    """The pre-query profile must move round 1 and then get out of the way."""
    qs = client.get("/profile/questions?n=3").json()["questions"]
    assert len(qs) == 3 and all(len(q["options"]) == 2 for q in qs)
    axes = {q["axis"] for q in qs}
    assert len(axes) == 3, "three questions must ask about three different axes"
    prof = client.post("/profile", json={"answers": [{"axis": q["axis"], "side": "high"} for q in qs]}).json()
    assert prof["n_answers"] == 3

    base = {"session_id": "p", "retrieval_text": "a shirt for an interview", "options": {"top_k": 5}}
    plain = client.post("/rank", json=base).json()
    with_profile = client.post("/rank", json={**base, "profile": prof}).json()
    assert [i["item_id"] for i in plain["items"]] != [i["item_id"] for i in with_profile["items"]]

    # the weight it carries is kappa0/(kappa0+rounds), so the same profile must weigh less
    # once the user has actually reacted — and the card attributes it to the user, separately
    def profile_weight(body):
        r = client.post("/rank", json=body).json()
        return max((abs(c["need_shares"].get("profile_prior", 0.0))
                    for it in r["items"] for c in it["contributions"]), default=0.0)

    shown = [i["item_id"] for i in with_profile["items"]]
    rounds = {"choice_history": [{"shown_item_ids": shown, "chosen_item_id": shown[0]}] * 3}
    w0 = profile_weight({**base, "profile": prof})
    w3 = profile_weight({**base, "profile": prof, "round": 3, "feedback": rounds})
    assert w0 > 0 and w3 < w0, (w0, w3)


def test_unknown_profile_axis_is_reported(client):
    r = client.post("/rank", json={"session_id": "t", "retrieval_text": "shirt",
                                   "profile": {"weights": {"no_such_axis": 1.0}, "n_answers": 1}})
    assert r.status_code == 200
    assert any("no_such_axis" in w for w in r.json()["constraint_report"]["input_warnings"])


def test_context_is_a_no_op_without_a_file(client, tmp_path, monkeypatch):
    """External context must degrade to nothing, not to an error."""
    monkeypatch.setenv("ENGINE02_CONTEXT", str(tmp_path / "does_not_exist.json"))
    r = client.get("/context")
    assert r.status_code == 200 and r.json()["available"] is False


def test_context_never_shrinks_the_candidate_pool(client):
    """An inferred season is a soft signal: it may change wording, never the hard filter."""
    body = {"session_id": "ctx", "retrieval_text": "something to wear today", "options": {"top_k": 3}}
    plain = client.post("/rank", json=body).json()["constraint_report"]
    with_ctx = client.post("/rank", json={**body, "constraints": {
        "season": {"state": "inferred", "values": ["Winter"]}}}).json()["constraint_report"]
    assert with_ctx["n_after_filter"] == plain["n_after_filter"]
    assert not with_ctx["relaxed"]


def test_a_stated_exclusion_is_enforced_in_the_same_round(client):
    """「不要黑色」 must remove black now, not warn about it and show black anyway."""
    body = {"session_id": "n", "retrieval_text": "a shirt for work, 不要黑色", "options": {"top_k": 5}}
    b = client.post("/rank", json=body).json()
    rep = b["constraint_report"]
    assert rep["honoured_negations"], rep
    assert rep["honoured_negations"][0]["applied_to"] == "color"
    colors = [str(i.get("color") or "").lower() for i in b["items"]]
    assert "black" not in colors, colors
    assert b["items"], "excluding something must not leave the user with nothing"


def test_wanting_something_is_not_mistaken_for_rejecting_it(client):
    """The parser must not fire on 「我想要黑色」 / "a black shirt"."""
    for text in ("a black shirt for work", "我想要黑色襯衫"):
        b = client.post("/rank", json={"session_id": "n", "retrieval_text": text,
                                       "options": {"top_k": 5}}).json()
        assert not b["constraint_report"]["honoured_negations"], (text, b["constraint_report"])


def test_the_control_arm_still_only_warns(client):
    b = client.post("/rank", json={"session_id": "n", "retrieval_text": "a shirt for work, 不要黑色",
                                   "options": {"top_k": 5, "arm": "full_zclip3_noneg"}}).json()
    assert not b["constraint_report"]["honoured_negations"]
    assert any("否定" in w for w in b["constraint_report"]["input_warnings"])


def test_an_exclusion_comes_with_something_instead(client):
    """「不要黑色」 should also say what it cost and what stands in for it."""
    b = client.post("/rank", json={"session_id": "s", "retrieval_text": "a shirt for work, 不要黑色",
                                   "options": {"top_k": 5}}).json()
    subs = b["constraint_report"]["substitutes"]
    assert subs, b["constraint_report"]
    shown = {i["item_id"] for i in b["items"]}
    for s in subs:
        assert s["substitute_item_id"] in shown, "a substitute must be an item we actually showed"
        assert s["excluded_item_id"] not in shown, "the excluded item must not be on screen"

    plain = client.post("/rank", json={"session_id": "s", "retrieval_text": "a shirt for work",
                                       "options": {"top_k": 5}}).json()
    assert not plain["constraint_report"]["substitutes"], "nothing excluded, nothing to substitute"
