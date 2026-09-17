import numpy as np
import pandas as pd
import pytest

from engine02.catalog import Catalog
from engine02.config import ARMS
from engine02.contracts import Engine02Options, Engine02Request, HardConstraints, NeedProbability, Slot, SlotState
from engine02.encoders import HashEncoder
from engine02.preference import (
    BayesLogistic,
    ChoiceRound,
    DesignSpace,
    LinUCB,
    NoLearning,
    PreferenceEngine02,
    RuleStep,
    ThompsonLogistic,
    comparison_pairs,
    rerank_candidates,
)

WORDS = ["navy", "black", "grey", "white", "red", "blue", "beige", "olive", "tailored", "relaxed", "casual",
         "formal", "knit", "denim", "wool", "leather", "pattern", "logo", "sport", "crisp", "collar", "soft"]


@pytest.fixture()
def engine(tmp_path):
    rng = np.random.default_rng(0)
    rows = []
    for i in range(60):
        words = " ".join(rng.choice(WORDS, size=4, replace=False))
        rows.append(dict(item_id=str(i), title=f"{words} jacket", description=None, category="outerwear",
                         subcategory="jacket", color=None, season=None, occasion=None, gender=None, price=None,
                         image_path=f"images/{i}.jpg"))
    df = pd.DataFrame(rows)
    cat = Catalog(items=df, root=tmp_path, name="toy")
    enc = HashEncoder(dim=128, captions={f"{r['item_id']}.jpg": r["title"] for r in rows})
    return PreferenceEngine02(cat, enc, cache_dir=tmp_path / "index")


def _req(k=5, n_cand=40):
    c = HardConstraints(category=Slot(state=SlotState.VALUE, values=["outerwear"]))
    return Engine02Request(session_id="s", retrieval_text="navy tailored jacket", constraints=c,
                           needs=[NeedProbability(need_id="trustworthy", prob=0.7)],
                           options=Engine02Options(top_k=k, n_candidates=n_cand, explain_with_llm=False))


def test_hook_matches_fast_rerank_and_keeps_additivity(engine):
    arm = ARMS["full_no_rocchio"]
    space = DesignSpace.from_kansei(engine.kansei)
    F = space.features(engine.design_matrix(arm))
    base = engine.run(_req(k=40), arm)
    pos = engine.catalog.positions([it.item_id for it in base.items])
    delta = np.zeros(space.dim)
    delta[space.element_ids.index("formal_style")] = 1.5
    delta[space.element_ids.index("dark_tone")] = -0.7
    from engine02.preference import PreferenceUpdate

    fast = rerank_candidates(np.array([it.score for it in base.items]), F[pos], PreferenceUpdate(delta=delta))
    fast_order = [base.items[i].item_id for i in np.argsort(-fast, kind="stable")[:5]]

    hooked = engine.run(_req(k=5), arm, design_weight_delta=space.to_dict(delta))
    assert [it.item_id for it in hooked.items] == fast_order
    for it in hooked.items:
        assert abs(sum(c.contribution for c in it.contributions) - it.score) < 1e-6
        for c in it.contributions:
            if c.group == "design":
                assert abs(sum(c.need_shares.values()) - c.contribution) < 1e-6
    # a top-k=5 run has the same order as the head of a top-k=40 run (eval relies on it)
    plain5 = engine.run(_req(k=5), arm)
    assert [it.item_id for it in plain5.items] == [it.item_id for it in base.items[:5]]
    assert [it.item_id for it in plain5.items] != fast_order  # the delta really moved the ranking


def test_folded_pole_delta_is_negated(engine):
    arm = ARMS["full_no_rocchio"]
    a = engine.run(_req(k=10), arm, design_weight_delta={"formal_style": 1.0})
    b = engine.run(_req(k=10), arm, design_weight_delta={"casual_style": -1.0})
    assert [it.item_id for it in a.items] == [it.item_id for it in b.items]
    assert np.allclose([it.score for it in a.items], [it.score for it in b.items])


def _simulate(learner, w_true, rounds=40, seed=0, d=11, n=300):
    rng = np.random.default_rng(seed)
    F = rng.normal(size=(n, d))
    beta0 = np.zeros(d)
    hist = []
    for _ in range(rounds):
        shown = [int(x) for x in rng.choice(n, size=5, replace=False)]
        u = F[shown] @ w_true + rng.gumbel(size=5)
        hist.append(ChoiceRound(shown=shown, chosen=shown[int(np.argmax(u))], rejected=[shown[int(np.argmin(u))]]))
    return learner.update(hist, F, beta0, rng=np.random.default_rng(1)), F, hist


@pytest.mark.parametrize("learner", [BayesLogistic(prior_sd=1.0), BayesLogistic(prior_sd=1.0, likelihood="mnl"),
                                     LinUCB(alpha=0.0)])
def test_learners_recover_direction(learner):
    w = np.array([2.0, -1.5, 0, 0, 1.0, 0, 0, 0, 0, 0, 0])
    upd, _, _ = _simulate(learner, w)
    est = upd.mean
    assert est @ w / (np.linalg.norm(est) * np.linalg.norm(w)) > 0.8


def test_thompson_is_seeded_and_centred():
    w = np.array([2.0, -1.5, 0, 0, 1.0, 0, 0, 0, 0, 0, 0])
    ts = ThompsonLogistic(prior_sd=1.0)
    a, F, hist = _simulate(ts, w)
    b = ts.update(hist, F, np.zeros(11), rng=np.random.default_rng(1))
    assert np.allclose(a.delta, b.delta)
    assert np.allclose(a.mean, BayesLogistic(prior_sd=1.0).update(hist, F, np.zeros(11)).mean)
    assert ts.update([], F, np.zeros(11)).delta.tolist() == [0.0] * 11


def test_rulestep_prd_semantics():
    F = np.zeros((5, 3))
    F[0] = [2.0, 0.1, 0.0]  # chosen: much higher on element 0
    F[4] = [0.0, 0.0, -3.0]  # rejected: much lower on element 2 → +1 step on element 2
    h = [ChoiceRound(shown=[0, 1, 2, 3, 4], chosen=0, rejected=[4])]
    upd = RuleStep(step_size=0.25, max_steps=3).update(h * 5, F, np.zeros(3))
    assert np.allclose(upd.delta, [0.75, 0.0, 0.75])  # clipped at 3 steps
    assert NoLearning().update(h, F, np.zeros(3)).delta.tolist() == [0.0, 0.0, 0.0]


def test_pairs_and_bonus_shapes():
    F = np.eye(6, 4)
    h = [ChoiceRound(shown=[0, 1, 2, 3], chosen=1, rejected=[3])]
    X = comparison_pairs(h, F)
    assert X.shape == (3 + 2, 4)  # chosen ≻ 3 others; 0,2 ≻ rejected
    upd = LinUCB(alpha=0.5).update(h, F, np.zeros(4))
    assert upd.bonus(F).shape == (6,) and (upd.bonus(F) >= 0).all()


def test_kansei_prior_cov_is_psd(engine):
    space = DesignSpace.from_kansei(engine.kansei)
    S = space.prior_cov(0.5, kind="kansei")
    assert S.shape == (space.dim, space.dim)
    assert np.linalg.eigvalsh(S).min() > 0
    assert "casual_style" not in space.element_ids and "formal_style" in space.element_ids


def test_bayes_damping_options():
    w = np.array([2.0, -1.5, 0, 0, 1.0, 0, 0, 0, 0, 0, 0])
    _, F, hist = _simulate(BayesLogistic(prior_sd=1.0), w, rounds=3)
    base = BayesLogistic(prior_sd=1.0).update(hist, F, np.zeros(11)).delta
    assert np.allclose(BayesLogistic(prior_sd=1.0, shrink_kappa=None, max_abs_delta=None)
                       .update(hist, F, np.zeros(11)).delta, base)  # defaults = undamped
    shrunk = BayesLogistic(prior_sd=1.0, shrink_kappa=2.0).update(hist, F, np.zeros(11)).delta
    assert np.allclose(shrunk, base * 3 / 5)
    capped = BayesLogistic(prior_sd=1.0, max_abs_delta=0.1).update(hist, F, np.zeros(11)).delta
    assert np.abs(capped).max() <= 0.1 + 1e-12 and np.allclose(capped, np.clip(base, -0.1, 0.1))
    assert BayesLogistic(shrink_kappa=1.0).update([], F, np.zeros(11)).delta.tolist() == [0.0] * 11
