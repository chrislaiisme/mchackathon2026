"""Tests for the completeness-audit additions: trend keywords, PRD §7 panels, ENGINE 03 handshake.

Model-free (HashEncoder), so they run on the laptop.
"""

from __future__ import annotations

import json
import math

import pandas as pd
import pytest

from engine02.catalog import Catalog
from engine02.compat import CategoryCooccurrence
from engine02.config import ARMS, FULL
from engine02.contracts import (
    Engine02Options,
    Engine02Request,
    HardConstraints,
    NeedProbability,
    Slot,
    SlotState,
)
from engine02.encoders import HashEncoder
from engine02.handshake import (
    AdjustOp,
    AnchorOp,
    ChoiceOp,
    CritiqueOp,
    ExcludeItemOp,
    ExcludeOp,
    FeedbackRound,
    FeelingOp,
    RequireOp,
    apply_round,
    handshake_example,
    need_likelihood,
    round_trip,
    update_needs,
)
from engine02.panels import (
    build_view,
    concept_image_neighbors,
    need_panel,
    need_supply,
    provenance,
    round_diff,
    stated_vs_unstated,
    view_labels,
)
from engine02.pipeline import Engine02
from engine02.trends import (
    TrendKeywords,
    attach_trends,
    curated_lift_terms,
    derive_trends,
    from_live_fetch,
    load_trends,
    outfit_partner_terms,
    trend_coverage,
)

# (id, title, category, subcategory, color, occasion, outfit_ids)
ROWS = [
    ("1", "navy tailored blazer structured shoulders", "outerwear", "blazer", "Navy Blue", "Formal", ["o1"]),
    ("2", "black formal suit jacket sharp lapel", "outerwear", "blazer", "Black", "Formal", ["o2"]),
    ("3", "grey soft knit oversized sweater", "top", "sweater", "Grey", "Casual", ["o1"]),
    ("4", "white crisp collar shirt cotton", "top", "shirt", "White", "Formal", ["o2"]),
    ("5", "red bold pattern dress pleated", "dress", "dress", "Red", "Casual", None),
    ("6", "blue relaxed denim wide jeans", "bottom", "jeans", "Blue", "Casual", ["o1"]),
    ("7", "navy matte wool coat oversized", "outerwear", "coat", "Navy Blue", "Formal", None),
    ("8", "beige casual linen chinos relaxed", "bottom", "trousers", "Beige", "Casual", None),
    ("9", "black leather ankle boots", "shoes", "boots", "Black", "Casual", ["o2"]),
    ("10", "olive oversized utility jacket", "outerwear", "jacket", "Olive", "Casual", None),
    ("11", "cream linen shirt relaxed", "top", "shirt", "Cream", "Casual", None),
    ("12", "charcoal tailored trousers pleated", "bottom", "trousers", "Charcoal", "Formal", None),
]


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            dict(item_id=i, title=t, description=None, category=c, subcategory=s, color=col,
                 season=None, occasion=occ, gender="Men", price=None,
                 outfit_ids=o, image_path=f"images/{i}.jpg")
            for i, t, c, s, col, occ, o in ROWS
        ]
    )


@pytest.fixture()
def engine(tmp_path):
    cat = Catalog(items=_frame(), root=tmp_path, name="toy")
    enc = HashEncoder(dim=128, captions={f"{i}.jpg": t for i, t, *_ in ROWS})
    cooc = CategoryCooccurrence({"top": {"bottom": 10, "outerwear": 6}, "outerwear": {"bottom": 8}})
    return Engine02(cat, enc, cooccurrence=cooc, cache_dir=tmp_path / "index")


def request(**kw) -> Engine02Request:
    c = HardConstraints(category=Slot(state=SlotState.VALUE, values=["outerwear"]),
                        color=Slot(state=SlotState.INFERRED, values=["Navy Blue"]))
    base = dict(session_id="s", round=1, utterances=["下週面試，不想太正式但要可靠"], constraints=c,
                retrieval_text="navy tailored jacket",
                needs=[NeedProbability(need_id="trustworthy", label="被信任", prob=0.6),
                       NeedProbability(need_id="avoid_tryhard", label="怕顯得用力", prob=0.4)],
                options=Engine02Options(top_k=3, explain_with_llm=False))
    base.update(kw)
    return Engine02Request(**base)


# ---------------------------------------------------------------------------
# trend keywords
# ---------------------------------------------------------------------------
def test_shipped_trend_list_loads_and_is_not_pinterest():
    tk = load_trends()
    assert tk.source == "manual" and tk.terms
    assert any("Pinterest" in n for n in tk.notes), "provenance note about Pinterest terms is required"
    assert tk.keywords(5) == [t.term for t in sorted(tk.terms, key=lambda x: -x.score)][:5]


def test_curated_lift_needs_a_mixed_catalog():
    df = _frame()
    terms = curated_lift_terms(df, top_n=5, min_df=1)
    assert terms and all(t.df >= 1 for t in terms)
    assert all(t.term not in {"jacket", "shirt", "men"} for t in terms), "generic taxonomy words dropped"
    df2 = df.copy()
    df2["outfit_ids"] = None
    with pytest.raises(ValueError):
        curated_lift_terms(df2, min_df=1)


def test_outfit_partner_terms_are_contextual():
    df = _frame()
    terms = outfit_partner_terms(df, ["outerwear"], top_n=10, min_df=1)
    got = {t.term for t in terms}
    assert got, "items sharing an outfit with outerwear should contribute terms"
    assert "blazer" not in got, "the anchor items themselves are not their own partners"


def test_live_trends_cannot_be_persisted(tmp_path):
    tk = from_live_fetch(lambda: ["quiet luxury", "Barrel Jeans"], name="pinterest")
    assert tk.ephemeral and tk.keywords()[0] == "quiet luxury"
    with pytest.raises(PermissionError):
        tk.save(tmp_path / "leak.json")
    ok = derive_trends(_frame(), "curated_lift", catalog="toy", top_n=5, min_df=1)
    assert ok.save(tmp_path / "ok.json").exists()


def test_trend_term_is_dormant_until_attached(engine):
    before = engine.run(request(), "full")
    assert all(cb.group != "trend" for it in before.items for cb in it.contributions)
    words = attach_trends(engine, TrendKeywords(terms=[], source="manual"))
    assert words == [] and all(cb.group != "trend" for it in engine.run(request(), "full").items
                               for cb in it.contributions)
    attach_trends(engine, derive_trends(_frame(), "curated_lift", top_n=10, min_df=1), top_n=10)
    after = engine.run(request(), "full")
    assert any(cb.group == "trend" for it in after.items for cb in it.contributions)
    for it in after.items:  # the additive guarantee must still hold with the extra term
        assert abs(sum(cb.contribution for cb in it.contributions) - it.score) < 1e-6
    cov = trend_coverage(engine)
    assert cov["n_keywords"] == 10 and 0.0 <= cov["nonzero_share"] <= 1.0


def test_trend_clipped_subclass_bounds_the_trend_term(tmp_path):
    from engine02.trends import TrendClippedEngine02

    cat = Catalog(items=_frame(), root=tmp_path, name="toy")
    enc = HashEncoder(dim=128, captions={f"{i}.jpg": t for i, t, *_ in ROWS})
    plain = Engine02(cat, enc, cache_dir=tmp_path / "index")
    clipped = TrendClippedEngine02(cat, enc, cache_dir=tmp_path / "index")
    words = derive_trends(_frame(), "curated_lift", top_n=10, min_df=1)
    attach_trends(plain, words, top_n=10)
    attach_trends(clipped, words, top_n=10)

    def trend_z(e):
        resp = e.run(request(), ARMS["full_zclip3"])
        return [cb.normalized for it in resp.items for cb in it.contributions if cb.group == "trend"]

    zp, zc = trend_z(plain), trend_z(clipped)
    assert zp and zc
    assert max(abs(z) for z in zc) <= 3.0 + 1e-9, "the wrapper must clip the trend z at arm.z_clip"
    assert all(abs(c) <= abs(p) + 1e-9 for p, c in zip(zp, zc))


def test_trend_badges_do_not_touch_the_ranking(engine):
    from engine02.trends import trend_badges

    words = derive_trends(_frame(), "curated_lift", top_n=10, min_df=1)
    base = engine.run(request(), "full")
    badges = trend_badges(engine, base, words.keywords(10))
    assert set(badges) == {it.item_id for it in base.items}
    assert all(b["affects_score"] is False for b in badges.values())
    assert any(b["matched"] for b in badges.values()), "some card should match a keyword"
    after = engine.run(request(), "full")  # badges are read-only: nothing was installed
    assert [it.item_id for it in after.items] == [it.item_id for it in base.items]
    assert all(cb.group != "trend" for it in after.items for cb in it.contributions)


def test_trend_weight_zero_leaves_ranking_unchanged(engine):
    from dataclasses import replace

    base = [it.item_id for it in engine.run(request(), "full").items]
    attach_trends(engine, derive_trends(_frame(), "curated_lift", top_n=10, min_df=1), top_n=10)
    off = replace(FULL, name="full_trend0", w_trend=0.0)
    assert [it.item_id for it in engine.run(request(), off).items] == base


# ---------------------------------------------------------------------------
# PRD §7 panels
# ---------------------------------------------------------------------------
def test_said_vs_unsaid_splits_slot_states(engine):
    req = request()
    resp = engine.run(req, "full")
    svu = stated_vs_unstated(req, resp, **view_labels(engine))
    assert svu.stated["category"] == ["outerwear"]
    assert svu.inferred["color"] == ["Navy Blue"], "inferred values are soft, not stated"
    assert "occasion" in svu.unmentioned and "budget" in svu.unmentioned
    assert svu.sentence and "你沒說" in svu.sentence
    assert svu.soft_only == [], "no style keywords or budget were stated here"
    kw = Slot(state=SlotState.VALUE, values=["quiet luxury"])
    req2 = request(constraints=HardConstraints(
        category=Slot(state=SlotState.VALUE, values=["outerwear"]), style_keywords=kw))
    svu2 = stated_vs_unstated(req2, engine.run(req2, "full"))
    assert svu2.soft_only == ["style_keywords"], "the screen must not imply style keywords were filtered"
    # driver contributions must equal the design need_shares actually on the cards
    total = sum(v for it in resp.items for cb in it.contributions
                if cb.group == "design" for k, v in cb.need_shares.items() if k != "feedback_adjust")
    assert abs(sum(d.contribution for d in svu.unstated_drivers) - total) < 1e-3  # fields are rounded to 4dp


def test_element_phrase_never_reads_backwards():
    from engine02.panels import _element_phrase

    assert _element_phrase("明顯 logo", -1.0, 0.5) == {"direction": "avoids", "phrase": "避開明顯 logo"}
    assert _element_phrase("明顯 logo", -1.0, -0.5)["phrase"] == "有明顯 logo（扣分）"
    assert _element_phrase("肩線挺", 1.0, 0.5) == {"direction": "has", "phrase": "肩線挺"}
    assert _element_phrase("肩線挺", 1.0, -0.5)["phrase"] == "缺少肩線挺（扣分）"


def test_need_panel_shares_are_consistent(engine):
    req = request()
    resp = engine.run(req, "full")
    p = need_panel(req, resp, **view_labels(engine))
    assert p.total_positive_contribution > 0
    assert 0.0 <= p.design_share_of_positive <= 1.0
    labels = {n.need_id for n in req.needs}
    assert set(p.unserved_needs) <= labels


def test_round_diff_reports_what_changed(engine):
    req1 = request()
    resp1 = engine.run(req1, "full")
    fb = FeedbackRound(session_id="s", round=1, utterance="太像上班族，不要黑色",
                       ops=[ExcludeOp(attribute="color", value="Black", quote="不要黑色"),
                            ChoiceOp(shown_item_ids=[it.item_id for it in resp1.items],
                                     chosen_item_id=resp1.items[0].item_id)])
    res = apply_round(req1, resp1, fb, kansei=engine.kansei)
    resp2 = engine.run(res.request, "full")
    d = round_diff(req1, resp1, res.request, resp2)
    assert d.prev_round == 1 and d.round == 2
    assert d.excluded_added == {"color": ["Black"]}
    assert set(i.item_id for i in d.kept) | set(d.new_items) == {it.item_id for it in resp2.items}
    assert 0.0 <= d.turnover <= 1.0
    assert "hard_constraint_satisfaction" in d.metrics_after


def test_provenance_flags_missing_price_and_relaxation(engine):
    c = HardConstraints(category=Slot(state=SlotState.VALUE, values=["outerwear"]),
                        color=Slot(state=SlotState.VALUE, values=["Purple"]))
    resp = engine.run(request(constraints=c), "full")
    pv = provenance(resp)
    assert pv.relaxed and pv.relaxed_human and any("放寬" in c for c in pv.caveats)
    assert pv.price_available is False and any("價格" in c for c in pv.caveats)
    assert pv.explanation_sources.get("template", 0) == len(resp.items)


def test_build_view_round_trips_through_json(engine):
    req = request()
    resp = engine.run(req, "full")
    view = build_view(req, resp, **view_labels(engine))
    raw = json.loads(view.model_dump_json())
    assert raw["said_vs_unsaid"]["sentence"] and raw["provenance"]["arm"] == "full"
    assert raw["round_diff"] is None
    assert raw["diversity"]["k"] == req.options.top_k


def test_div_at_k_is_rule_based(engine):
    from engine02.panels import slate_diversity

    resp = engine.run(request(), "full")
    d = slate_diversity(resp, 3)
    assert d.k == 3 and sum(d.categories.values()) == 3 and sum(d.colors.values()) == 3
    assert d.distinct_categories == 1, "the hard filter pinned the category to outerwear"
    assert 0.0 <= d.div_at_k <= 1.0
    assert d.div_at_k == round((d.distinct_categories + d.distinct_colors) / 6, 4)


def test_view_works_on_the_service_response(tmp_path):
    """The real API path is Engine02Service.rank → DiversifiedResponse; the panels must read it."""
    from engine02.composed import ComposedEngine02
    from engine02.service import Engine02Service

    cat = Catalog(items=_frame(), root=tmp_path, name="toy")
    enc = HashEncoder(dim=128, captions={f"{i}.jpg": t for i, t, *_ in ROWS})
    eng = ComposedEngine02(cat, enc, cache_dir=tmp_path / "index")
    svc = Engine02Service(eng)
    req = request()
    resp = svc.rank(req, "full_zclip3")
    view = build_view(req, resp, **view_labels(eng))
    assert view.provenance.diversification.get("method") == "dpp"
    assert view.needs.total_positive_contribution > 0
    assert view.said_vs_unsaid.stated["category"] == ["outerwear"]
    json.loads(view.model_dump_json())  # serialisable for the frontend


def test_need_supply_and_concept_neighbors(engine):
    sup = need_supply(engine, ARMS["full"], threshold=0.0)
    assert set(sup) == set(engine.kansei.need_ids)
    assert all(0.0 <= v <= 1.0 for v in sup.values())
    nn = concept_image_neighbors(engine, engine.image_emb[0], k=3)
    assert len(nn) == 3 and nn[0]["item_id"] == "1"
    assert nn[0]["cosine"] >= nn[1]["cosine"] >= nn[2]["cosine"]
    assert all(x["source"] == "concept_image_nearest" for x in nn)


# ---------------------------------------------------------------------------
# offline replay (PRD §8 斷網重播模式)
# ---------------------------------------------------------------------------
def test_replay_records_then_reproduces_exactly(engine, tmp_path):
    from engine02.replay import ReplayMiss, ReplayStore, request_key

    req = request()
    rec = ReplayStore(tmp_path / "replay", mode="record")
    ranked = rec.wrap(engine.run)
    live = ranked(req, "full")
    assert rec.stats["recorded"] == 1

    calls = {"n": 0}

    def exploding(r, arm=None):  # stands in for "the network / the model is gone"
        calls["n"] += 1
        raise RuntimeError("offline")

    rp = ReplayStore(tmp_path / "replay", mode="replay")
    off = rp.wrap(exploding)
    got = off(req, "full")
    assert calls["n"] == 0 and rp.stats["hit"] == 1
    assert [i.item_id for i in got.items] == [i.item_id for i in live.items]
    assert [round(i.score, 9) for i in got.items] == [round(i.score, 9) for i in live.items]
    assert got.items[0].reasons == live.items[0].reasons
    with pytest.raises(ReplayMiss):
        off(request(round=7), "full")

    # the key ignores session_id but not round / constraints / feedback
    assert request_key(req, "full") == request_key(request(session_id="other"), "full")
    assert request_key(req, "full") != request_key(request(round=2), "full")
    assert request_key(req, "full") != request_key(req, "full_zclip3")
    assert rp.manifest()["n_records"] == 1


def test_replay_auto_mode_fills_in_misses(engine, tmp_path):
    from engine02.replay import ReplayStore

    st = ReplayStore(tmp_path / "replay", mode="auto")
    ranked = st.wrap(engine.run)
    a = ranked(request(), "full")
    b = ranked(request(), "full")
    assert st.stats == {"hit": 1, "miss": 1, "recorded": 1}
    assert [i.item_id for i in a.items] == [i.item_id for i in b.items]
    assert ReplayStore(tmp_path / "replay", mode="off").wrap(engine.run) == engine.run


def test_replay_keeps_service_response_fields(tmp_path):
    from engine02.composed import ComposedEngine02
    from engine02.replay import ReplayStore
    from engine02.service import Engine02Service

    cat = Catalog(items=_frame(), root=tmp_path, name="toy")
    enc = HashEncoder(dim=128, captions={f"{i}.jpg": t for i, t, *_ in ROWS})
    svc = Engine02Service(ComposedEngine02(cat, enc, cache_dir=tmp_path / "index"))
    st = ReplayStore(tmp_path / "replay", mode="record")
    live = st.wrap(svc.rank)(request(), "full_zclip3")
    back = ReplayStore(tmp_path / "replay", mode="replay").load(request(), "full_zclip3")
    assert type(back).__name__ == type(live).__name__
    assert back.diversification == live.diversification
    assert [i.relevance_rank for i in back.items] == [i.relevance_rank for i in live.items]


# ---------------------------------------------------------------------------
# ENGINE 03 handshake
# ---------------------------------------------------------------------------
def test_exclude_is_permanent_and_leaves_the_positive_slot(engine):
    req = request(constraints=HardConstraints(
        category=Slot(state=SlotState.VALUE, values=["outerwear"]),
        color=Slot(state=SlotState.VALUE, values=["Black", "Navy Blue"])))
    resp = engine.run(req, "full")
    res = apply_round(req, resp, FeedbackRound(session_id="s", round=1,
                                               ops=[ExcludeOp(attribute="color", value="Black")]),
                      kansei=engine.kansei)
    assert res.request.constraints.excluded_values["color"] == ["Black"]
    assert res.request.constraints.color.values == ["Navy Blue"]
    out = engine.run(res.request, "full")
    assert all((it.color or "") != "Black" for it in out.items)
    assert out.metrics.excluded_value_hits == 0


def test_adjust_steps_accumulate_and_clip(engine):
    req, resp = request(), None
    resp = engine.run(req, "full")
    el = engine.kansei.element_ids[0]
    for _ in range(5):
        res = apply_round(req, resp, FeedbackRound(session_id="s", round=req.round,
                                                   ops=[AdjustOp(element=el, step=1)]),
                          kansei=engine.kansei)
        req = res.request
        resp = engine.run(req, "full")
    assert req.feedback.design_adjust_steps[el] == 3, "clipped at max_steps"
    assert any("上限" in (e.note or "") for e in res.ledger)
    bad = apply_round(req, resp, FeedbackRound(session_id="s", round=1,
                                               ops=[AdjustOp(element="not_an_element", step=1)]),
                      kansei=engine.kansei)
    assert bad.rejected_ops and "unknown design element" in bad.rejected_ops[0]["reason"]
    assert not bad.ledger


def test_critique_becomes_a_never_relaxed_required_value(engine):
    req = request()
    resp = engine.run(req, "full")
    res = apply_round(req, resp, FeedbackRound(session_id="s", round=1, ops=[
        CritiqueOp(reference_item_id=resp.items[0].item_id, attribute="color", to_value="Olive",
                   quote="這件但換成橄欖綠")]), kansei=engine.kansei)
    assert res.request.feedback.reference_item_id == resp.items[0].item_id
    assert res.request.constraints.required_values["color"] == ["Olive"]
    # single-round: the next handshake clears the pointer but keeps the required value
    res2 = apply_round(res.request, engine.run(res.request, "full"),
                       FeedbackRound(session_id="s", round=2, ops=[]), kansei=engine.kansei)
    assert res2.request.feedback.critique is None
    assert res2.request.constraints.required_values["color"] == ["Olive"]


def test_choice_history_accumulates_and_service_learns_from_it(engine):
    req = request()
    resp = engine.run(req, "full")
    shown = [it.item_id for it in resp.items]
    res = apply_round(req, resp, FeedbackRound(session_id="s", round=1, ops=[
        ChoiceOp(shown_item_ids=shown, chosen_item_id=shown[-1], rejected_item_ids=[shown[0]])]),
        kansei=engine.kansei)
    fb = res.request.feedback
    assert len(fb.choice_history) == 1 and fb.choice_history[0].chosen_item_id == shown[-1]
    assert fb.chosen_item_ids == [shown[-1]] and fb.rejected_item_ids == [shown[0]]
    assert fb.design_weight_delta == {}, "the service fits Δβ; ENGINE 03 must not send weights"
    res2 = apply_round(res.request, engine.run(res.request, "full"),
                       FeedbackRound(session_id="s", round=2, ops=[
                           ChoiceOp(shown_item_ids=shown, chosen_item_id=shown[0])]), kansei=engine.kansei)
    assert len(res2.request.feedback.choice_history) == 2


def test_feeling_applies_prd_formula_four(engine):
    req = request()
    resp = engine.run(req, "full")
    res = apply_round(req, resp, FeedbackRound(session_id="s", round=1, ops=[
        FeelingOp(quote="太像上班族", need_log_likelihood={"avoid_tryhard": 1.0, "trustworthy": -0.5},
                  lam=1.0)]), kansei=engine.kansei)
    probs = {n.need_id: n.prob for n in res.request.needs}
    assert abs(sum(probs.values()) - 1.0) < 1e-9
    assert probs["avoid_tryhard"] > 0.4 and probs["trustworthy"] < 0.6
    entry = [e for e in res.ledger if e.op == "feeling"][0]
    assert entry.before["trustworthy"] == 0.6 and entry.quote == "太像上班族"
    bad = apply_round(req, resp, FeedbackRound(session_id="s", round=1, ops=[FeelingOp(quote="不喜歡")]),
                      kansei=engine.kansei)
    assert bad.rejected_ops and "does not infer" in bad.rejected_ops[0]["reason"]


def test_update_needs_is_a_reweighting():
    needs = [NeedProbability(need_id="a", prob=0.5), NeedProbability(need_id="b", prob=0.5)]
    same = update_needs(needs, {}, 1.0)
    assert [round(n.prob, 6) for n in same] == [0.5, 0.5]
    moved = update_needs(needs, {"a": math.log(3.0)}, 1.0)
    assert abs(moved[0].prob - 0.75) < 1e-9


def test_need_likelihood_uses_returned_design_scores(engine):
    resp = engine.run(request(), "full")
    a, b = resp.items[0], resp.items[-1]
    n = engine.kansei.need_ids[0]
    p = need_likelihood(a, b, engine.kansei, n)
    assert 0.0 <= p <= 1.0
    assert abs(need_likelihood(a, a, engine.kansei, n) - 0.5) < 1e-9
    assert abs(p + need_likelihood(b, a, engine.kansei, n) - 1.0) < 1e-9


def test_anchor_enables_compatibility_and_exclude_item_hides(engine):
    req = request()
    resp = engine.run(req, "full")
    assert all(cb.group != "compat" for it in resp.items for cb in it.contributions)
    res = apply_round(req, resp, FeedbackRound(session_id="s", round=1, ops=[
        AnchorOp(item_ids=["6"]), ExcludeItemOp(item_ids=[resp.items[0].item_id])]), kansei=engine.kansei)
    out = engine.run(res.request, "full")
    assert any(cb.group == "compat" for it in out.items for cb in it.contributions)
    assert resp.items[0].item_id not in [it.item_id for it in out.items]


def test_round_is_incremented_and_request_survives_json(engine):
    req = request()
    resp = engine.run(req, "full")
    res = apply_round(req, resp, FeedbackRound(session_id="s", round=1, utterance="不要黑色", ops=[
        ExcludeOp(attribute="color", value="Black"), RequireOp(attribute="occasion", value="Casual")]),
        kansei=engine.kansei)
    assert res.request.round == 2 and res.request.utterances[-1] == "不要黑色"
    again = round_trip(res.request)
    assert again.model_dump() == res.request.model_dump()
    out1 = engine.run(res.request, "full")
    out2 = engine.run(again, "full")
    assert [i.item_id for i in out1.items] == [i.item_id for i in out2.items]
    assert [round(i.score, 9) for i in out1.items] == [round(i.score, 9) for i in out2.items]


def test_handshake_example_document(engine, tmp_path):
    req = request()
    resp = engine.run(req, "full")
    fb = FeedbackRound(session_id="s", round=1, utterance="太像上班族，不要黑色", ops=[
        ExcludeOp(attribute="color", value="Black", quote="不要黑色"),
        FeelingOp(quote="太像上班族", need_log_likelihood={"avoid_tryhard": 0.8}),
        ChoiceOp(shown_item_ids=[it.item_id for it in resp.items], chosen_item_id=resp.items[-1].item_id),
    ])
    doc = handshake_example(req, resp, fb, kansei=engine.kansei)
    assert set(doc) >= {"round_1_request", "engine03_feedback", "ledger", "round_2_request"}
    assert doc["round_2_request"]["round"] == 2
    p = tmp_path / "example.json"
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    assert json.loads(p.read_text(encoding="utf-8"))["ledger"][0]["op"] == "exclude"


def test_feedback_round_schema_is_a_closed_operation_set():
    schema = FeedbackRound.model_json_schema()
    names = set()
    for defn in schema.get("$defs", {}).values():
        op = defn.get("properties", {}).get("op", {})
        names.update(op.get("enum", []) or ([op["const"]] if "const" in op else []))
    assert names == {"exclude", "require", "adjust", "choice", "feeling", "critique", "anchor",
                     "exclude_item"}
