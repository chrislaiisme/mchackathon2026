import json

import numpy as np
import pandas as pd
import pytest

from engine02.catalog import Catalog
from engine02.config import ARMS
from engine02.contracts import Engine02Options, Engine02Request
from engine02.encoders import HashEncoder
from engine02.ltr import (
    CORE_FEATURES,
    EXT_FEATURES,
    CapturingEngine02,
    LearnedWeightsEngine,
    LinearRanker,
    TypeAwareRanker,
    capture_query,
    coordinate_ascent,
    learn_grid_full,
    learn_linear,
    learn_type_aware,
    make_batch,
    pairwise_logistic,
    qf_from_dict,
    qf_to_dict,
    ranker_to_json,
)

ROWS = [
    ("1", "navy tailored blazer structured shoulders", "outerwear", "blazer", "navy"),
    ("2", "black formal suit jacket", "outerwear", "blazer", "black"),
    ("3", "grey soft knit sweater", "top", "sweater", "grey"),
    ("4", "white crisp collar shirt", "top", "shirt", "white"),
    ("5", "red bold pattern dress", "dress", "dress", "red"),
    ("6", "blue relaxed denim jeans", "bottom", "jeans", "blue"),
    ("7", "navy matte wool coat", "outerwear", "coat", "navy"),
    ("8", "beige casual chinos", "bottom", "trousers", "beige"),
    ("9", "black leather ankle boots", "shoes", "boots", "black"),
    ("10", "olive oversized casual jacket", "outerwear", "jacket", "green"),
    ("11", "navy casual jacket with zip", "outerwear", "jacket", "navy"),
    ("12", "white linen summer shirt", "top", "shirt", "white"),
]
QUERIES = [("navy jacket", {"11": 3, "10": 1, "7": 2}), ("white shirt", {"4": 3, "12": 3}),
           ("azure tee", {"4": 1, "12": 1}), ("black boots", {"9": 3}), ("crimson frock", {"5": 3})]


def _engine(tmp_path, cls=CapturingEngine02, **kw):
    df = pd.DataFrame([dict(item_id=i, title=t, description=None, category=c, subcategory=s, color=col, season=None,
                            occasion=None, gender=None, price=10.0, image_path=f"images/{i}.jpg")
                       for i, t, c, s, col in ROWS])
    cat = Catalog(items=df, root=tmp_path, name="toy")
    enc = HashEncoder(dim=128, captions={f"{i}.jpg": t for i, t, *_ in ROWS})
    return cls(cat, enc, cache_dir=tmp_path / "index", **kw)


@pytest.fixture()
def qfs(tmp_path):
    eng = _engine(tmp_path)
    out = []
    for n, (text, grades) in enumerate(QUERIES):
        qf = capture_query(eng, f"q{n}", f"g{n}", "lexical", text, grades, top_k=5, n_candidates=8)
        for arm in ("hybrid_rrf", "hybrid_convex", "dense", "full_adaptive_bm25"):
            req = Engine02Request(session_id="s", retrieval_text=text,
                                  options=Engine02Options(top_k=5, n_candidates=8, explain_with_llm=False,
                                                          counterfactual_check=False))
            qf.engine_top[arm] = [it.item_id for it in eng.run(req, arm).items]
        out.append(qf)
    return out


def test_capture_has_norm_and_contributions(tmp_path):
    eng = _engine(tmp_path)
    capture_query(eng, "q", "g", "lexical", "navy jacket", {"11": 3}, top_k=5, n_candidates=8)
    cap = eng.last_capture
    assert cap["norm"].shape[1] == len(cap["term_names"]) and "dense" in cap["term_names"]


def test_simulation_reproduces_engine(qfs):
    sims = {"full": LinearRanker(n_candidates=8),
            "hybrid_rrf": LinearRanker(weights=(), n_candidates=8),
            "hybrid_convex": LinearRanker(weights=(), fusion="convex", n_candidates=8),
            "dense": LinearRanker(weights=(), fusion="dense", n_candidates=8),
            "full_adaptive_bm25": LinearRanker(n_candidates=8, adaptive_bm25=True)}
    for qf in qfs:
        for arm, r in sims.items():
            assert r.rank(qf, 5) == qf.engine_top[arm], (qf.text, arm)


def test_learners_nonnegative(qfs):
    for feats in (CORE_FEATURES, EXT_FEATURES):
        b = make_batch(qfs, feats, LinearRanker(n_candidates=8), k=5)
        w, v = coordinate_ascent(b, n_restarts=2)
        assert (w >= 0).all() and abs(w.sum() - 1) < 1e-9 and 0 <= v <= 1
        w2 = pairwise_logistic(b, epochs=50)
        assert (w2 >= 0).all()
    g = learn_grid_full(qfs)
    assert all(v >= 0 for _, v in g.weights)
    ta = learn_type_aware(qfs, learn_linear, features=CORE_FEATURES)
    assert isinstance(ta, TypeAwareRanker)
    assert len(ta.rank(qfs[0], 5)) == 5


def test_qf_roundtrip(qfs):
    d = json.loads(json.dumps(qf_to_dict(qfs[0])))
    back = qf_from_dict(d)
    assert LinearRanker(n_candidates=8).rank(back, 5) == LinearRanker(n_candidates=8).rank(qfs[0], 5)


def test_learned_weights_engine_keeps_additivity(tmp_path):
    r = TypeAwareRanker(covered=LinearRanker(weights=(("dense", 0.3), ("bm25", 1.2)), rrf_k=10),
                        uncovered=LinearRanker(weights=(("dense", 1.5), ("bm25", 0.0)), fusion="dense"))
    js = ranker_to_json(r)
    eng = _engine(tmp_path, LearnedWeightsEngine, learned=js)
    from engine02.contracts import NeedProbability

    for text in ("navy jacket", "azure frock"):
        req = Engine02Request(session_id="s", retrieval_text=text,
                              needs=[NeedProbability(need_id="trustworthy", prob=0.7)],
                              options=Engine02Options(top_k=3, explain_with_llm=False))
        resp = eng.run(req, "full")
        assert resp.arm == "full+ltr"
        for it in resp.items:
            assert abs(sum(c.contribution for c in it.contributions) - it.score) < 1e-9
            assert all(c.weight >= 0 for c in it.contributions if c.group in ("dense", "bm25"))
    # fusion-only arms are untouched
    assert eng.arm_for("navy jacket", ARMS["hybrid_rrf"]) is ARMS["hybrid_rrf"]
    assert eng.arm_for("azure frock", ARMS["full"]).candidate_fusion == "dense"
