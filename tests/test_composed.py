import numpy as np
import pandas as pd
import pytest

from dataclasses import replace

from engine02.catalog import Catalog
from engine02.config import ARMS
from engine02.composed import (
    METHODS,
    ComposedEngine02,
    Critique,
    LLMRewriter,
    TemplateRewriter,
    apply_to_request,
    rank_dense,
)
from engine02.contracts import Engine02Options, Engine02Request, HardConstraints, Slot, SlotState
from engine02.encoders import HashEncoder

ROWS = [
    ("1", "Brand Men Black Check Shirt", "top", "Shirts", "Black", "Casual", "Men"),
    ("2", "Brand Men Navy Blue Check Shirt", "top", "Shirts", "Navy Blue", "Casual", "Men"),
    ("3", "Brand Men Navy Blue Formal Shirt", "top", "Shirts", "Navy Blue", "Formal", "Men"),
    ("4", "Brand Men White Formal Shirt", "top", "Shirts", "White", "Formal", "Men"),
    ("5", "Brand Men Red Tshirt", "top", "Tshirts", "Red", "Casual", "Men"),
    ("6", "Brand Women Navy Blue Top", "top", "Tops", "Navy Blue", "Casual", "Women"),
    ("7", "Brand Men Black Formal Shirt", "top", "Shirts", "Black", "Formal", "Men"),
    ("8", "Brand Men Grey Check Shirt", "top", "Shirts", "Grey", "Casual", "Men"),
]


@pytest.fixture()
def engine(tmp_path):
    df = pd.DataFrame([dict(item_id=i, title=t, description=None, category=c, subcategory=s, color=col, season=None,
                            occasion=o, gender=g, price=None, image_path=f"images/{i}.jpg")
                       for i, t, c, s, col, o, g in ROWS])
    cat = Catalog(items=df, root=tmp_path, name="toy")
    enc = HashEncoder(dim=128, captions={f"{i}.jpg": t.lower() for i, t, *_ in ROWS})
    return ComposedEngine02(cat, enc, cache_dir=tmp_path / "index")


def base_constraints():
    return HardConstraints(category=Slot(state=SlotState.VALUE, values=["Shirts"]),
                           gender=Slot(state=SlotState.VALUE, values=["Men"]))


def test_template_rewrite_replaces_attribute(engine):
    row = engine.catalog.items.iloc[0]
    assert TemplateRewriter("title").rewrite(row, Critique("color", "Navy Blue")) == "Brand Men Navy Blue Check Shirt"
    assert TemplateRewriter("meta").rewrite(row, Critique("color", "Navy Blue")) == "Men Navy Blue Shirts for casual"
    assert TemplateRewriter("title").rewrite(row, Critique("occasion", direction="more_formal")).startswith("formal ")
    assert TemplateRewriter("meta").rewrite(row, Critique("occasion", direction="more_formal")).endswith("for formal")


def test_llm_rewriter_falls_back_on_bad_output(engine):
    row = engine.catalog.items.iloc[0]
    crit = Critique("color", "Navy Blue")
    bad = LLMRewriter(lambda p: "a black check shirt in navy blue")  # keeps old value
    assert bad.rewrite(row, crit) == "Brand Men Navy Blue Check Shirt" and bad.last_source == "template"
    good = LLMRewriter(lambda p: "men's navy blue check shirt")
    assert good.rewrite(row, crit) == "men's navy blue check shirt" and good.last_source == "llm"
    boom = LLMRewriter(lambda p: (_ for _ in ()).throw(RuntimeError("no key")))
    assert boom.rewrite(row, crit) == "Brand Men Navy Blue Check Shirt"


def test_all_methods_compose_and_rank(engine):
    comp = engine.composer()
    crit = Critique("color", "Navy Blue")
    for m in METHODS:
        cq = comp.compose(0, crit, "Men Shirts", m, alpha=0.3, lam=2.0)
        assert cq.exclude_item_ids == ["1"]
        if m == "critique_filter":
            assert cq.query_embedding is None and cq.retrieval_text == "Men Shirts"
            assert cq.constraint_updates == {"color": ["Navy Blue"]}
            continue
        assert abs(np.linalg.norm(cq.query_embedding) - 1) < 1e-6
        top = rank_dense(engine, base_constraints(), cq, k=3, min_results=1)
        ids = [str(engine.catalog.items.at[p, "item_id"]) for p in top]
        assert "1" not in ids  # the reference is never returned
        if m in ("ref_plus_filter", "image_plus_text_filter"):
            assert set(ids) <= {"2", "3"}  # hard filter on the new colour, Men Shirts only


def test_text_rewrite_prefers_changed_attribute(engine):
    comp = engine.composer()
    cq = comp.compose(0, Critique("color", "Navy Blue"), "Men Shirts", "text_rewrite")
    top = rank_dense(engine, base_constraints(), cq, k=1, min_results=1)
    assert engine.catalog.items.at[top[0], "item_id"] == "2"  # same title except colour


def test_run_composed_through_pipeline(engine):
    comp = engine.composer()
    req = Engine02Request(session_id="s", retrieval_text="Men Shirts", constraints=base_constraints(),
                          options=Engine02Options(top_k=2, explain_with_llm=False, counterfactual_check=False))
    cq = comp.compose(0, Critique("occasion", direction="more_formal"), "Men Shirts", "image_plus_text_filter",
                      alpha=0.5)
    new = apply_to_request(req, cq)
    assert new.constraints.occasion.values == ["Formal"] and req.constraints.occasion.values == []
    # arms default to min_results=5; with 3 formal shirts the ladder would drop the critique
    resp = engine.run_composed(req, cq, replace(ARMS["hybrid_rrf"], min_results=2))
    assert resp.items and all(it.item_id in {"3", "4", "7"} for it in resp.items)
    assert np.allclose(resp.query_embedding, cq.query_embedding, atol=1e-6)
    assert engine._override is None
    # critique_filter keeps the pipeline's own text embedding
    cf = comp.compose(0, Critique("occasion", direction="more_formal"), "Men Shirts", "critique_filter")
    resp2 = engine.run_composed(req, cf, replace(ARMS["full"], min_results=2))
    assert all(it.item_id in {"3", "4", "7"} for it in resp2.items)
