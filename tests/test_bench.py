"""Logic tests for the external-benchmark adapters (`engine02/external.py`, `scripts/eval_external.py`).

Model-free: everything runs with `HashEncoder` / hand-built arrays, so this file is safe on the
laptop. What is checked is that each metric matches the *published* definition it claims to
reproduce, because that is the only thing that makes our numbers comparable to a paper.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine02 import external as ext
from engine02.catalog import Catalog
from engine02.contracts import Engine02Options, Engine02Request
from engine02.encoders import HashEncoder
from engine02.pipeline import Engine02

# ---------------------------------------------------------------------------
# 1. Marqo text-to-image metrics
# ---------------------------------------------------------------------------


def test_recall_denominator_is_all_relevant_docs():
    """trec_eval / BEIR semantics: Recall@1 with 4 relevant docs is at most 0.25."""
    m = ext.marqo_t2i_metrics(["a", "x", "y", "z", "b"], ["a", "b", "c", "d"], ks=(1, 10))
    assert m["recall@1"] == pytest.approx(0.25)
    assert m["recall@10"] == pytest.approx(0.5)  # a and b found out of 4
    assert m["avg_recall"] == pytest.approx(0.375)


def test_mrr_is_truncated_at_the_run_length():
    """Marqo's eval retrieves only top-10, so a hit at rank 11 scores 0 (= MRR@10)."""
    run = [f"d{i}" for i in range(1, 11)]
    assert ext.marqo_t2i_metrics(run, ["d3"])["mrr"] == pytest.approx(1 / 3)
    assert ext.marqo_t2i_metrics(run, ["d99"])["mrr"] == 0.0
    assert ext.marqo_t2i_metrics(run[:2] + ["gold"], ["gold"])["mrr"] == pytest.approx(1 / 3)


def test_precision_metric_for_attribute_tasks():
    m = ext.marqo_attr_metrics(["a", "b", "x"], ["a", "b", "c", "d", "e"], ks=(1, 10))
    assert m["p@1"] == pytest.approx(1.0)
    assert m["p@10"] == pytest.approx(0.2)  # 2 hits / k=10, even though only 3 docs were retrieved
    assert m["mrr"] == pytest.approx(1.0)


def test_rank_ids_is_deterministic_under_ties():
    scores = np.array([1.0, 1.0, 0.5])
    assert ext.rank_ids(scores, ["b", "a", "c"], k=3) == ["a", "b", "c"]  # tie broken by id
    assert ext.rank_ids(scores, ["b", "a", "c"], k=1) == ["a"]
    assert ext.rank_ids(np.zeros(0), [], k=5) == []


# ---------------------------------------------------------------------------
# 2. ESCI nDCG
# ---------------------------------------------------------------------------


def test_ndcg_linear_matches_hand_computation():
    grades = {"p1": 1.0, "p2": 0.1, "p3": 0.0}
    # perfect order
    assert ext.ndcg_linear(["p1", "p2", "p3"], grades, 3) == pytest.approx(1.0)
    # swapped top two
    dcg = 0.1 / np.log2(2) + 1.0 / np.log2(3)
    idcg = 1.0 / np.log2(2) + 0.1 / np.log2(3)
    assert ext.ndcg_linear(["p2", "p1", "p3"], grades, 3) == pytest.approx(dcg / idcg)


def test_ndcg_linear_differs_from_exponential_gain_version():
    """The ESCI gains are fractional, so 2^g-1 (engine02.eval.metrics) is a *different* metric."""
    from engine02.eval.metrics import ndcg_at_k

    grades = {"a": 1.0, "b": 0.1, "c": 0.01}
    order = ["b", "a", "c"]
    assert ext.ndcg_linear(order, grades, 3) != pytest.approx(ndcg_at_k(order, grades, 3), abs=1e-3)


def test_esci_gain_map_is_the_competition_one():
    assert ext.ESCI_GAINS == {"E": 1.0, "S": 0.1, "C": 0.01, "I": 0.0}


def test_apparel_query_heuristic():
    assert ext.is_apparel_query("mens black dress shirt")
    assert ext.is_apparel_query("nike running shoes size 10")
    assert not ext.is_apparel_query("usb c cable 6ft")
    assert not ext.is_apparel_query("shirtless poster")  # whole-word match only


# ---------------------------------------------------------------------------
# 3. AUROC
# ---------------------------------------------------------------------------


def test_auroc_known_values():
    assert ext.auroc([1.0, 0.9, 0.2, 0.1], [1, 1, 0, 0]) == pytest.approx(1.0)
    assert ext.auroc([0.1, 0.2, 0.9, 1.0], [1, 1, 0, 0]) == pytest.approx(0.0)
    assert ext.auroc([1.0, 1.0, 1.0, 1.0], [1, 1, 0, 0]) == pytest.approx(0.5)  # all ties
    # pairs: (1.0>0.5)=1, (1.0>0.0)=1, (0.5 vs 0.5)=0.5, (0.5>0.0)=1  → 3.5/4
    assert ext.auroc([1.0, 0.5, 0.5, 0.0], [1, 1, 0, 0]) == pytest.approx(0.875)
    assert np.isnan(ext.auroc([1.0, 0.5], [1, 1]))


def test_paired_auc_delta_test_detects_a_real_gap():
    rng = np.random.default_rng(0)
    labels = np.array([1] * 200 + [0] * 200)
    good = np.where(labels == 1, 1.0, 0.0) + rng.normal(0, 0.4, 400)
    bad = rng.normal(0, 1.0, 400)
    r = ext.paired_auc_delta_test(good, bad, labels, n_boot=400, seed=0)
    assert r["delta"] > 0.2 and r["p"] < 0.05
    same = ext.paired_auc_delta_test(good, good, labels, n_boot=400, seed=0)
    assert same["delta"] == pytest.approx(0.0) and same["p"] > 0.5


def test_bootstrap_auc_ci_brackets_the_point_estimate():
    rng = np.random.default_rng(1)
    labels = np.array([1] * 100 + [0] * 100)
    s = np.where(labels == 1, 0.7, 0.3) + rng.normal(0, 0.3, 200)
    lo, hi = ext.bootstrap_auc_ci(s, labels, n_boot=300, seed=0)
    assert lo < ext.auroc(s, labels) < hi


# ---------------------------------------------------------------------------
# 4. Polyvore FITB / compatibility question construction
# ---------------------------------------------------------------------------
CATS = ["top", "bottom", "shoes", "bag", "outerwear", "dress"]


def _outfit_items(n_outfits: int = 40, per: int = 4) -> pd.DataFrame:
    rows = []
    k = 0
    for o in range(n_outfits):
        for j in range(per):
            rows.append(dict(item_id=f"i{k}", title=f"item {k}", category=CATS[j % len(CATS)],
                             subcategory=CATS[j % len(CATS)], color=None,
                             outfit_ids=[f"o{o}"], image_path=f"images/i{k}.jpg"))
            k += 1
    # some non-apparel noise that must be ignored
    for j in range(10):
        rows.append(dict(item_id=f"n{j}", title=f"noise {j}", category="other", subcategory="other",
                         color=None, outfit_ids=["o0"], image_path=f"images/n{j}.jpg"))
    return pd.DataFrame(rows)


def test_fitb_questions_are_well_formed():
    items = _outfit_items()
    qs = ext.fitb_questions(items, n=20, seed=0, n_cands=4, neg_mode="same_category")
    assert len(qs) == 20
    cats = items["category"].tolist()
    for q in qs:
        assert len(q.candidates) == 4
        assert 0 <= q.gold < 4
        gold = q.candidates[q.gold]
        # the gold item really belongs to the outfit, the anchors are the rest of it
        assert f"o" in q.outfit_id
        assert gold not in q.anchors and len(q.anchors) >= 2
        # negatives are same-category and never from the same outfit
        for c in q.candidates:
            assert cats[c] == cats[gold]
            if c != gold:
                assert q.outfit_id not in (items.at[c, "outfit_ids"] or [])
        # non-apparel items never appear
        assert all(cats[a] in ext.APPAREL for a in q.anchors)


def test_fitb_random_negatives_are_not_category_matched():
    items = _outfit_items()
    qs = ext.fitb_questions(items, n=40, seed=0, n_cands=4, neg_mode="random")
    cats = items["category"].tolist()
    mixed = sum(any(cats[c] != cats[q.candidates[q.gold]] for c in q.candidates) for q in qs)
    assert mixed > len(qs) // 2  # Han-2017-style negatives are usually a different category


def test_fitb_questions_are_reproducible_and_seed_sensitive():
    items = _outfit_items()
    a = ext.fitb_questions(items, n=10, seed=0)
    b = ext.fitb_questions(items, n=10, seed=0)
    c = ext.fitb_questions(items, n=10, seed=1)
    assert [x.candidates for x in a] == [x.candidates for x in b]
    assert [x.candidates for x in a] != [x.candidates for x in c]


def test_fitb_hit_splits_ties():
    assert ext.fitb_hit(np.array([1.0, 0.0, 0.0, 0.0]), 0) == 1.0
    assert ext.fitb_hit(np.array([0.0, 1.0, 0.0, 0.0]), 0) == 0.0
    assert ext.fitb_hit(np.zeros(4), 2) == pytest.approx(0.25)  # all tied == chance
    assert ext.fitb_hit(np.array([1.0, 1.0, 0.0, 0.0]), 1) == pytest.approx(0.5)


def test_compat_pairs_are_paired_and_substituted():
    items = _outfit_items()
    pairs = ext.compat_pairs(items, n=20, seed=0, neg_mode="same_category")
    assert len(pairs) == 20
    cats = items["category"].tolist()
    for p in pairs:
        assert len(p.positive) == len(p.negative)  # same size distribution in both classes
        assert set(p.positive).isdisjoint(p.negative)
        assert [cats[x] for x in p.positive] == [cats[x] for x in p.negative]


def test_mean_pairwise_similarity_and_npmi():
    emb = np.eye(4)
    assert ext.mean_pairwise_similarity(emb, [0, 1, 2]) == pytest.approx(0.0)
    assert ext.mean_pairwise_similarity(emb, [0]) == 0.0
    same = np.tile(np.array([1.0, 0.0, 0.0, 0.0]), (4, 1))
    assert ext.mean_pairwise_similarity(same, [0, 1, 2]) == pytest.approx(1.0)

    from engine02.compat import CategoryCooccurrence

    cooc = CategoryCooccurrence({"top": {"bottom": 10, "shoes": 1}, "bottom": {"shoes": 5}})
    strong = ext.mean_pairwise_npmi(cooc, ["top", "bottom"])
    weak = ext.mean_pairwise_npmi(cooc, ["top", "shoes"])
    assert strong > weak
    assert ext.mean_pairwise_npmi(cooc, ["top"]) == 0.0


# ---------------------------------------------------------------------------
# 5. end-to-end: the benchmark harness on a toy catalog with HashEncoder
# ---------------------------------------------------------------------------
TOY = [
    ("1", "navy tailored blazer", "outerwear"),
    ("2", "black formal suit jacket", "outerwear"),
    ("3", "grey soft knit sweater", "top"),
    ("4", "white crisp collar shirt", "top"),
    ("5", "red bold pattern dress", "dress"),
    ("6", "blue relaxed denim jeans", "bottom"),
]


@pytest.fixture()
def toy_engine(tmp_path):
    df = pd.DataFrame([dict(item_id=i, title=t, description=None, category=c, subcategory=c,
                            color=None, season=None, occasion=None, gender=None, price=None,
                            outfit_ids=None, image_path=f"images/{i}.jpg") for i, t, c in TOY])
    cat = Catalog(items=df, root=tmp_path, name="toy")
    enc = HashEncoder(dim=256, captions={f"{i}.jpg": t for i, t, _ in TOY})
    return Engine02(cat, enc, cache_dir=tmp_path / "index"), cat


def _arm_ranking(engine, query: str, arm: str, k: int = 3) -> list[str]:
    req = Engine02Request(session_id="t", retrieval_text=query,
                          options=Engine02Options(top_k=k, n_candidates=6, arm=arm,
                                                  explain_with_llm=False, counterfactual_check=False))
    return [it.item_id for it in engine.run(req, arm).items]


def test_arms_produce_rankings_scorable_by_the_marqo_metric(toy_engine):
    engine, _ = toy_engine
    gt = {t: {i: 1} for i, t, _ in TOY}  # text-to-image ground truth = the item its title came from
    for arm in ("dense", "hybrid_rrf", "full_zclip3"):
        ranked = [_arm_ranking(engine, q, arm) for q in gt]
        ms = [ext.marqo_t2i_metrics(r, gt[q]) for r, q in zip(ranked, gt)]
        assert len(ms) == len(TOY)
        assert all(0.0 <= m["recall@1"] <= 1.0 for m in ms)
        # a query that IS the indexed title must be found by BM25-backed arms
        if arm != "dense":
            assert np.mean([m["recall@1"] for m in ms]) > 0.5


def test_dense_arm_equals_raw_encoder_ranking(toy_engine):
    """Sanity check that the `dense` arm is exactly the protocol Marqo publishes (pure cosine)."""
    engine, cat = toy_engine
    ids = cat.items["item_id"].astype(str).tolist()
    for q in ("navy tailored blazer", "red bold pattern dress"):
        qv = engine.encoder.encode_text([q])[0].astype(np.float64)
        qv = qv / np.linalg.norm(qv)
        scores = engine.image_emb @ qv
        # the pipeline breaks ties by catalog position (np.argsort kind="stable"); rank_ids breaks
        # them by item id, so compare against the pipeline's own convention
        raw = [ids[i] for i in np.argsort(-scores, kind="stable")[:3]]
        assert _arm_ranking(engine, q, "dense") == raw
        assert ext.rank_ids(scores, ids, k=1)[0] in [i for i in ids if scores[ids.index(i)] == scores.max()]


def test_paired_table_shape_and_self_comparison():
    from scripts.eval_external import _paired_table

    a = np.array([1.0] * 15 + [0.0] * 5)
    pq = {"x": {"recall@1": a}, "y": {"recall@1": np.zeros(20)}}
    rows = _paired_table(pq, ("recall@1",))
    assert len(rows) == 1
    assert rows[0]["delta"] == pytest.approx(0.75)
    assert rows[0]["p_perm"] < 0.01  # 15/20 vs 0/20 is unmistakable
    assert rows[0]["metric"] == "recall@1"
    lo, hi = rows[0]["delta_ci95"]
    assert lo < 0.75 < hi


def test_marqo_ground_truth_roundtrip(tmp_path):
    import json

    p = tmp_path / "gt.json"
    p.write_text(json.dumps({"black dress": {"123": 1, "456": 1}}), encoding="utf-8")
    gt = ext.load_marqo_ground_truth(p)
    assert gt == {"black dress": {"123": 1, "456": 1}}
    assert ext.marqo_t2i_metrics(["456"], gt["black dress"])["recall@1"] == pytest.approx(0.5)
