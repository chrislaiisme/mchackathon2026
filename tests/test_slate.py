import itertools

import numpy as np
import pandas as pd
import pytest

from engine02.catalog import Catalog
from engine02.compat import CategoryCooccurrence
from engine02.complete_look import CompleteTheLook, cooccurrence_from_outfits, rank_categories
from engine02.contracts import Engine02Options, Engine02Request, HardConstraints, NeedProbability, Slot, SlotState
from engine02.diversify import (
    DiversityConfig,
    alpha_ndcg,
    deep_request,
    diversify_response,
    ild,
    near_duplicate_rate,
    run_diversified,
    select_dpp,
    select_mmr,
    select_xquad,
)
from engine02.encoders import HashEncoder
from engine02.pipeline import Engine02

TITLES = [
    "navy tailored blazer structured", "navy tailored blazer structured wool", "navy tailored blazer",
    "black formal suit jacket", "olive oversized casual jacket", "beige trench coat classic",
    "grey soft knit cardigan", "red bold pattern bomber jacket", "white linen summer jacket",
    "brown leather biker jacket", "navy matte wool coat", "green quilted puffer",
]


@pytest.fixture()
def engine(tmp_path):
    df = pd.DataFrame([
        dict(item_id=str(i), title=t, description=None, category="outerwear", subcategory=t.split()[-1],
             color=t.split()[0], season=None, occasion=None, gender=None, price=None, image_path=f"images/{i}.jpg")
        for i, t in enumerate(TITLES)
    ])
    cat = Catalog(items=df, root=tmp_path, name="toy")
    enc = HashEncoder(dim=128, captions={f"{i}.jpg": t for i, t in enumerate(TITLES)})
    return Engine02(cat, enc, cache_dir=tmp_path / "index")


def req(**kw):
    base = dict(session_id="s", retrieval_text="navy tailored blazer",
                constraints=HardConstraints(category=Slot(state=SlotState.VALUE, values=["outerwear"])),
                needs=[NeedProbability(need_id="trustworthy", prob=0.6), NeedProbability(need_id="avoid_tryhard", prob=0.4)],
                options=Engine02Options(top_k=4, explain_with_llm=False))
    base.update(kw)
    return Engine02Request(**base)


# ---------------------------------------------------------------- algorithms
def test_dpp_matches_bruteforce_greedy():
    rng = np.random.default_rng(0)
    f = rng.normal(size=(15, 8))
    f /= np.linalg.norm(f, axis=1, keepdims=True)
    rel = rng.random(15)
    theta = 0.6
    r = (rel - rel.min()) / (rel.max() - rel.min())
    S = (1 + f @ f.T) / 2
    sel = []
    for _ in range(5):  # naive greedy on θ·Σr + (1−θ)·log det S_Y
        best = max((i for i in range(15) if i not in sel),
                   key=lambda i: theta * r[i] + (1 - theta) * np.linalg.slogdet(S[np.ix_(sel + [i], sel + [i])])[1])
        sel.append(best)
    assert select_dpp(rel, f, 5, theta) == sel


def test_limits_reduce_to_relevance():
    rng = np.random.default_rng(1)
    f = rng.normal(size=(10, 4))
    f /= np.linalg.norm(f, axis=1, keepdims=True)
    rel = rng.random(10)
    top = list(np.argsort(-rel)[:4])
    assert select_mmr(rel, f, 4, 1.0) == top
    assert select_dpp(rel, f, 4, 1.0) == top
    assert select_xquad(rel, rng.random((10, 3)), np.ones(3) / 3, 4, 0.0) == top


def test_dpp_avoids_duplicates():
    f = np.array([[1, 0], [1, 0], [0, 1]], dtype=float)
    rel = np.array([1.0, 0.99, 0.5])
    assert select_dpp(rel, f, 2, 0.5) == [0, 2]


def test_xquad_covers_aspects():
    rel = np.array([1.0, 0.95, 0.5])
    P = np.array([[1, 0], [1, 0], [0, 1]], dtype=float)
    assert select_xquad(rel, P, np.array([0.5, 0.5]), 2, 0.7) == [0, 2]


def test_metrics():
    sim = np.array([[1, 0.97, 0.2], [0.97, 1, 0.1], [0.2, 0.1, 1]])
    assert abs(near_duplicate_rate(sim) - 1 / 3) < 1e-9
    assert abs(ild(sim) - (1 - (0.97 + 0.2 + 0.1) / 3)) < 1e-9
    J = np.array([[1, 0], [1, 0], [0, 1]])
    assert alpha_ndcg(J, [0, 2, 1], 2) == pytest.approx(1.0)
    assert alpha_ndcg(J, [0, 1, 2], 2) < 1.0


# ---------------------------------------------------------------- faithful wrapper
def test_none_equals_pipeline(engine):
    base = [it.item_id for it in engine.run(req(), "full").items]
    resp = run_diversified(engine, req(), "full", DiversityConfig("none", depth=10))
    assert [it.item_id for it in resp.items] == base
    assert not any(it.promoted_by_diversity for it in resp.items)


def test_mmr_equals_full_mmr_arm(engine):
    base = [it.item_id for it in engine.run(req(), "full_mmr").items]
    resp = run_diversified(engine, req(), "full", DiversityConfig("mmr", 0.7, depth=20))
    assert [it.item_id for it in resp.items] == base


@pytest.mark.parametrize("cfg", [DiversityConfig("mmr", 0.3, depth=10), DiversityConfig("dpp", 0.3, depth=10),
                                 DiversityConfig("xquad", 0.9, depth=10)])
def test_faithful_explanations(engine, cfg):
    r = req()
    deep = engine.run(deep_request(r, cfg.depth), "full")
    resp = diversify_response(engine, r, deep, cfg)
    k = r.options.top_k
    deep_ids = [it.item_id for it in deep.items]
    assert len(resp.items) == k
    for it in resp.items:
        assert it.item_id in deep_ids[: cfg.depth]
        assert it.relevance_rank == deep_ids.index(it.item_id) + 1
        assert it.promoted_by_diversity == (it.relevance_rank > k)
        assert abs(sum(c.contribution for c in it.contributions) - it.score) < 1e-6
        cut = deep.items[k].score
        if it.promoted_by_diversity:
            assert it.reasons[0].startswith("為了多樣性而納入")
            assert not any(c.sufficient for c in it.contributions)
        else:  # cited terms alone beat the relevance rank-(k+1) item
            cited = sum(c.contribution for c in it.contributions if c.cited)
            assert cited > cut
    promoted = {it.item_id for it in resp.items if it.promoted_by_diversity}
    assert set(resp.diversification["promoted"]) == promoted
    assert len(resp.diversification["displaced"]) == len(promoted)


# ---------------------------------------------------------------- complete the look
def test_category_selection_excludes_anchor_and_heldout():
    items = pd.DataFrame(dict(
        category=["top", "bottom", "shoes", "top", "bottom", "bag", "dress", "shoes"],
        outfit_ids=[["a"], ["a"], ["a"], ["b"], ["b"], ["b"], ["c"], ["c"]],
    ))
    full = cooccurrence_from_outfits(items)
    held = cooccurrence_from_outfits(items, exclude_outfits={"c"})
    assert full.counts["dress"]["shoes"] == 1
    assert "dress" not in held.counts
    ranked = rank_categories(["top"], full)
    assert "top" not in [c for c, _ in ranked]
    assert ranked[0][0] == "bottom"


class FakeOT:
    def compatibility(self, anchors, cands):
        return np.linspace(0, 1, len(cands))

    def complementary(self, anchors, cands, target_category=""):
        return -np.linspace(0, 1, len(cands))


def test_complete_the_look_contributions(tmp_path):
    items = pd.DataFrame(dict(item_id=[str(i) for i in range(8)], title=[f"t{i}" for i in range(8)],
                              category=["top", "bottom", "bottom", "bottom", "shoes", "shoes", "top", "bag"],
                              outfit_ids=[["a"], ["a"], ["b"], ["c"], ["a"], ["b"], ["b"], ["c"]],
                              image_path=[f"images/{i}.jpg" for i in range(8)]))
    cat = Catalog(items=items, root=tmp_path)
    emb = np.random.default_rng(0).normal(size=(8, 6))
    emb /= np.linalg.norm(emb, axis=1, keepdims=True)
    ctl = CompleteTheLook(cat, emb, cooccurrence_from_outfits(items), ot=FakeOT())
    for method in ("random", "similarity", "ot", "ot_sim", "ot_cir"):
        slates = ctl.recommend(["0"], n_categories=2, k=2, method=method)
        assert slates and all(s.category != "top" for s in slates)
        for s in slates:
            for it in s.items:
                assert it.item_id != "0"
                assert abs(sum(it.contributions.values()) - it.score) < 1e-9
                assert cat.attr(it.position, "category") == s.category
