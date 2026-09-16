import numpy as np
import pandas as pd
import pytest

from engine02.catalog import Catalog
from engine02.compat import CategoryCooccurrence
from engine02.config import ARMS
from engine02.contracts import Engine02Request, HardConstraints, NeedProbability, Slot, SlotState
from engine02.encoders import HashEncoder
from engine02.explain import verify_paraphrase
from engine02.fusion import mmr, rrf
from engine02.pipeline import Engine02

ROWS = [
    ("1", "navy tailored blazer structured shoulders", "outerwear", "blazer", "navy", 120.0),
    ("2", "black formal suit jacket", "outerwear", "blazer", "black", 200.0),
    ("3", "grey soft knit sweater", "top", "sweater", "grey", 60.0),
    ("4", "white crisp collar shirt", "top", "shirt", "white", 45.0),
    ("5", "red bold pattern dress", "dress", "dress", "red", 80.0),
    ("6", "blue relaxed denim jeans", "bottom", "jeans", "blue", 70.0),
    ("7", "navy matte wool coat", "outerwear", "coat", None, 150.0),
    ("8", "beige casual chinos", "bottom", "trousers", "beige", 55.0),
    ("9", "black leather ankle boots", "shoes", "boots", "black", 110.0),
    ("10", "olive oversized casual jacket", "outerwear", "jacket", "green", 90.0),
]


@pytest.fixture()
def engine(tmp_path):
    df = pd.DataFrame(
        [
            dict(item_id=i, title=t, description=None, category=c, subcategory=s, color=col, season=None,
                 occasion=None, gender=None, price=p, image_path=f"images/{i}.jpg")
            for i, t, c, s, col, p in ROWS
        ]
    )
    cat = Catalog(items=df, root=tmp_path, name="toy")
    enc = HashEncoder(dim=128, captions={f"{i}.jpg": t for i, t, *_ in ROWS})
    cooc = CategoryCooccurrence({"top": {"bottom": 10, "outerwear": 6}, "outerwear": {"bottom": 8}, "shoes": {"bottom": 5}})
    return Engine02(cat, enc, cooccurrence=cooc, cache_dir=tmp_path / "index")


def request(**kw):
    c = HardConstraints(category=Slot(state=SlotState.VALUE, values=["outerwear"]))
    base = dict(session_id="s", utterances=["下週面試，不想太正式但要可靠"], constraints=c,
                retrieval_text="navy tailored jacket",
                needs=[NeedProbability(need_id="trustworthy", prob=0.6), NeedProbability(need_id="avoid_tryhard", prob=0.3)])
    base.update(kw)
    return Engine02Request(**base)


def test_contributions_sum_to_score(engine):
    resp = engine.run(request(), "full")
    assert resp.items, "should return items"
    for it in resp.items:
        assert abs(sum(c.contribution for c in it.contributions) - it.score) < 1e-6
        assert it.category == "outerwear"  # hard filter respected
        for c in it.contributions:
            if c.group == "design":
                assert abs(sum(c.need_shares.values()) - c.contribution) < 1e-6


def test_all_arms_run(engine):
    for name in ARMS:
        resp = engine.run(request(), name)
        assert resp.arm == name
        assert len(resp.items) >= 1


def test_relaxation_is_reported(engine):
    c = HardConstraints(
        category=Slot(state=SlotState.VALUE, values=["outerwear"]),
        color=Slot(state=SlotState.VALUE, values=["purple"]),
    )
    resp = engine.run(request(constraints=c), "full")
    assert "color:allow_unknown" in resp.constraint_report.relaxed
    assert any("放寬" in r for r in resp.items[0].reasons)
    assert all(it.category == "outerwear" for it in resp.items)


def test_exclusions_never_relaxed(engine):
    c = HardConstraints(category=Slot(state=SlotState.VALUE, values=["outerwear"]), excluded_values={"color": ["black"]})
    resp = engine.run(request(constraints=c), "full")
    assert all(it.color != "black" for it in resp.items)
    assert resp.metrics.excluded_value_hits == 0


def test_compat_only_with_anchor(engine):
    resp = engine.run(request(), "full")
    assert not any(c.group == "compat" for it in resp.items for c in it.contributions)
    req = request()
    req.feedback.anchor_item_ids = ["6"]
    resp = engine.run(req, "full")
    assert any(c.group == "compat" for it in resp.items for c in it.contributions)


def test_counterfactual_fields(engine):
    resp = engine.run(request(), "full")
    for it in resp.items:
        for c in it.contributions:
            assert c.rank_without is not None and c.necessary == (c.rank_without > 5)


def test_rocchio_changes_query(engine):
    base = engine.run(request(), "full")
    req = request()
    req.feedback.chosen_item_ids = ["3"]
    moved = engine.run(req, "full")
    assert not np.allclose(base.query_embedding, moved.query_embedding)


def test_llm_paraphrase_fact_check(engine):
    engine.llm = lambda prompt: "這件有亮面材質，很適合你（+9.99）"  # invents a label and a number
    resp = engine.run(request(), "full")
    assert all(it.explanation_source == "template" for it in resp.items)


def test_verify_paraphrase():
    facts = [{"type": "design", "label": "肩線挺", "contribution": 0.35, "serves_needs": ["被信任"]}]
    vocab = ["肩線挺", "被信任", "亮面材質"]
    assert verify_paraphrase("肩線挺讓你看起來值得被信任", facts, vocab)
    assert not verify_paraphrase("肩線挺又有亮面材質", facts, vocab)
    assert not verify_paraphrase("肩線挺，分數 0.99", facts, vocab)


def test_rrf_and_mmr():
    a = np.array([3.0, 2.0, 1.0])
    b = np.array([1.0, 2.0, 3.0])
    f = rrf([a, b], k=60)
    assert np.isclose(f[0], f[2])
    emb = np.eye(3)
    assert len(mmr(np.array([1.0, 0.9, 0.1]), emb, 2)) == 2


def test_metrics():
    from engine02.eval.metrics import cohen_kappa, ndcg_at_k, paired_permutation_test

    assert ndcg_at_k(["a", "b"], {"a": 2, "b": 1}, 2) == 1.0
    assert ndcg_at_k(["b", "a"], {"a": 2, "b": 1}, 2) < 1.0
    assert paired_permutation_test(np.ones(20), np.zeros(20)) < 0.01
    assert cohen_kappa([1, 0, 1, 0], [1, 0, 1, 0]) == 1.0


def test_sufficient_reasons_cover_every_card(engine):
    resp = engine.run(request(), "full")
    for it in resp.items:
        cited = [c for c in it.contributions if c.cited]
        assert all(c.sufficient for c in cited)
        if it.score > 0:
            assert cited, "sufficient mode should give at least one reason to a positive-score item"


def test_prd_original_and_concept_modes_run(engine):
    for name in ("prd_original", "full_concept_descriptor", "full_concept_random", "full_concept_no_mask",
                 "full_reason_contrastive", "full_norm_candidates"):
        resp = engine.run(request(), name)
        assert resp.items


def test_applicability_mask():
    from engine02.concepts import applicability_mask
    from engine02.kansei import KanseiTable

    t = KanseiTable.load()
    m = applicability_mask(["shoes", "top", None], t)
    j = t.element_ids.index("structured_shoulders")
    assert not m[0, j] and m[1, j] and not m[2, j]
