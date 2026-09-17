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
        if ARMS[name].concept_mode in ("vlm", "hybrid"):  # needs offline VLM tagging output
            continue
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


def test_vlm_concept_scores(tmp_path, engine):
    from engine02.concepts import vlm_design_scores

    df = pd.DataFrame({"item_id": ["1", "2", "3"], "c_structured_shoulders": [0.9, -0.5, 0.1],
                       "na_structured_shoulders": [0.0, 0.1, 0.9]})
    f = tmp_path / "vlm_attributes_test.parquet"
    df.to_parquet(f)
    c = vlm_design_scores(["1", "2", "3", "4"], engine.kansei, f)
    j = engine.kansei.element_ids.index("structured_shoulders")
    assert c[0, j] > c[1, j] and c[2, j] == 0 and c[3, j] == 0


def test_feedback_adjust_label_not_leaked(engine):
    req = request()
    req.feedback.design_adjust_steps = {"formal_style": -2}
    resp = engine.run(req, "full")
    assert all("feedback_adjust" not in r for it in resp.items for r in it.reasons)


def test_reason_polarity(engine):
    req = request()
    req.needs = [NeedProbability(need_id="avoid_tryhard", prob=1.0)]  # K[avoid_tryhard, formal_style] < 0
    resp = engine.run(req, "full")
    for it in resp.items:
        for c in it.contributions:
            if c.cited and c.group == "design" and c.weight < 0:
                label = engine.kansei.elements[engine.kansei.element_ids.index(c.term.split(":")[1])].label
                assert any(f"避開{label}" in r for r in it.reasons)


def test_antonym_folding():
    from engine02.kansei import KanseiTable

    t = KanseiTable.load()
    assert t.folded.get("casual_style") == "formal_style"
    i, a, b = t.need_ids.index("polished"), t.element_ids.index("formal_style"), t.element_ids.index("casual_style")
    assert t.K[i, b] == 0 and 0 < t.K[i, a] <= 1
    _, fb = t.beta({}, {"casual_style": 1})
    assert fb[a] == -t.step_size and fb[b] == 0
    raw = KanseiTable.load(fold_antonyms=False)
    assert raw.K[i, b] < 0


def test_hybrid_concepts(tmp_path, engine):
    from dataclasses import replace

    j = engine.kansei.element_ids.index("visible_logo")
    df = pd.DataFrame({"item_id": ["1", "2", "3"], "c_visible_logo": [0.9, -0.9, 0.0], "na_visible_logo": [0.0, 0.0, 0.0]})
    df.to_parquet(engine.catalog.root / "vlm_attributes_test.parquet")
    arm = replace(ARMS["full_concept_hybrid"], vlm_elements=("visible_logo",))
    c = engine.design_matrix(arm)
    base = engine.design_matrix(replace(arm, concept_mode="antonym"))
    assert c[0, j] > c[1, j]
    assert np.allclose(c[3:, j], base[3:, j])  # untagged items keep CLIP scores
    other = engine.kansei.element_ids.index("formal_style")
    assert np.allclose(c[:, other], base[:, other])


def test_item_level_compat_model(engine):
    class Fake:
        name = "fake"

        def score(self, anchors, cands):
            return np.array([float(c) for c in cands])

    engine.compat_model = Fake()
    req = request()
    req.feedback.anchor_item_ids = ["6"]
    resp = engine.run(req, "full")
    terms = {c.term for it in resp.items for c in it.contributions}
    assert "compat:fake" in terms


def test_required_values_never_relaxed(engine):
    c = HardConstraints(category=Slot(state=SlotState.VALUE, values=["outerwear"]), required_values={"color": ["navy"]})
    resp = engine.run(request(constraints=c), "full")
    assert resp.items and all((it.color or "").lower() == "navy" for it in resp.items)
    assert not any(r.startswith("color") for r in resp.constraint_report.relaxed)


def test_service_critique_and_diversity(tmp_path):
    from engine02.composed import ComposedEngine02
    from engine02.contracts import Critique
    from engine02.service import Engine02Service

    df = pd.DataFrame(
        [dict(item_id=i, title=t, description=None, category=c, subcategory=s, color=col, season=None,
              occasion=None, gender=None, price=p, image_path=f"images/{i}.jpg") for i, t, c, s, col, p in ROWS]
    )
    cat = Catalog(items=df, root=tmp_path, name="toy")
    enc = HashEncoder(dim=128, captions={f"{i}.jpg": t for i, t, *_ in ROWS})
    svc = Engine02Service(ComposedEngine02(cat, enc, cache_dir=tmp_path / "index"))
    req = request()
    req.options.top_k = 3
    req.feedback.reference_item_id = "2"
    req.feedback.critique = Critique(attribute="color", to_value="navy")
    resp = svc.rank(req, "full")
    assert resp.composed and resp.composed["required_values"] == {"color": ["navy"]}
    assert all((it.color or "").lower() == "navy" for it in resp.items)
    assert all(it.item_id != "2" for it in resp.items)
    assert resp.diversification["method"] == "dpp"
