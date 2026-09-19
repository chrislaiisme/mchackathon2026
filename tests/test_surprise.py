"""驚喜款 (surprise slot) in diversify_response: faithful, opt-in, no-op without catalog boldness."""

import pandas as pd
import pytest

from engine02.catalog import Catalog
from engine02.contracts import (
    ContextInput,
    Engine02Options,
    Engine02Request,
    HardConstraints,
    NeedProbability,
    Slot,
    SlotState,
)
from engine02.diversify import DiversityConfig, deep_request, diversify_response
from engine02.encoders import HashEncoder
from engine02.pipeline import Engine02

TITLES = [
    "navy tailored blazer structured", "navy tailored blazer structured wool", "navy tailored blazer",
    "black formal suit jacket", "olive oversized casual jacket", "beige trench coat classic",
    "grey soft knit cardigan", "red bold pattern bomber jacket", "white linen summer jacket",
    "brown leather biker jacket", "navy matte wool coat", "green quilted puffer",
]
CFG = DiversityConfig("none", depth=12)


def make_engine(tmp_path, boldness=None):
    df = pd.DataFrame([
        dict(item_id=str(i), title=t, description=None, category="outerwear", subcategory=t.split()[-1],
             color=t.split()[0], season=None, occasion=None, gender=None, price=None, image_path=f"images/{i}.jpg")
        for i, t in enumerate(TITLES)
    ])
    if boldness is not None:
        df["boldness"] = boldness
    cat = Catalog(items=df, root=tmp_path, name="toy")
    enc = HashEncoder(dim=128, captions={f"{i}.jpg": t for i, t in enumerate(TITLES)})
    return Engine02(cat, enc, cache_dir=tmp_path / "index")


def req(surprise=False):
    return Engine02Request(
        session_id="s", retrieval_text="navy tailored blazer",
        constraints=HardConstraints(category=Slot(state=SlotState.VALUE, values=["outerwear"])),
        needs=[NeedProbability(need_id="trustworthy", prob=0.6), NeedProbability(need_id="avoid_tryhard", prob=0.4)],
        options=Engine02Options(top_k=4, explain_with_llm=False),
        context=ContextInput(surprise=surprise),
    )


def run(engine, r):
    deep = engine.run(deep_request(r, CFG.depth), "full")
    return deep, diversify_response(engine, r, deep, CFG)


def bold_map(**over):
    b = [0.0] * len(TITLES)
    for k, v in over.items():
        b[int(k[1:])] = v
    return b


def test_surprise_applied(tmp_path):
    engine = make_engine(tmp_path, bold_map(i7=3, i4=2))
    deep, base = run(engine, req(False))
    _, resp = run(engine, req(True))
    base_ids = [it.item_id for it in base.items]
    ids = [it.item_id for it in resp.items]
    assert "7" not in base_ids  # the bold bomber is not a relevance top-4 card here
    assert ids[:-1] == base_ids[:-1] and ids[-1] == "7"  # only the LAST card is swapped
    card = resp.items[-1]
    assert card.promoted_by_surprise and not card.promoted_by_diversity
    deep_ids = [it.item_id for it in deep.items]
    assert card.relevance_rank == deep_ids.index("7") + 1
    assert card.reasons[0] == (f"驚喜款：設計大膽度 3/3（其他卡片最高 0/3），仍符合你所有的條件"
                               f"（純相關度排第 {card.relevance_rank} 名）")
    assert not any(c.sufficient for c in card.contributions)  # not claimed on relevance alone
    assert not any(it.promoted_by_surprise for it in resp.items[:-1])
    s = resp.diversification["surprise"]
    assert s["requested"] and s["applied"] and s["reason_if_not_applied"] is None
    assert (s["item_id"], s["boldness"], s["relevance_rank"], s["replaced_item_id"]) == \
        ("7", 3.0, card.relevance_rank, base_ids[-1])
    assert base_ids[-1] in [d["item_id"] for d in resp.diversification["displaced"]]
    assert resp.diversification["promoted"] == []


def test_surprise_no_qualifying_item(tmp_path):
    engine = make_engine(tmp_path, [1.0] * len(TITLES))
    _, base = run(engine, req(False))
    _, resp = run(engine, req(True))
    assert [it.model_dump() for it in resp.items] == [it.model_dump() for it in base.items]
    s = resp.diversification["surprise"]
    assert s["requested"] and not s["applied"] and s["item_id"] is None
    assert "大膽度" in s["reason_if_not_applied"]


def test_surprise_not_bolder_than_kept_cards(tmp_path):
    # the relevance #1 card is already 3/3 -> nobody can be strictly bolder
    engine = make_engine(tmp_path)
    _, base = run(engine, req(False))
    top = int(base.items[0].item_id)
    engine2 = make_engine(tmp_path / "b", bold_map(i7=3, **{f"i{top}": 3}))
    _, resp = run(engine2, req(True))
    assert not resp.diversification["surprise"]["applied"]
    assert not any(it.promoted_by_surprise for it in resp.items)


@pytest.mark.parametrize("boldness", [None, "column"])
def test_surprise_false_identical(tmp_path, boldness):
    b = bold_map(i7=3) if boldness else None
    e1 = make_engine(tmp_path / "a", b)
    e0 = make_engine(tmp_path / "b", None)
    _, with_col = run(e1, req(False))
    _, without = run(e0, req(False))
    assert with_col.model_dump_json(exclude={"timings_ms"}) == without.model_dump_json(exclude={"timings_ms"})
    assert "surprise" not in with_col.diversification


def test_no_boldness_column_items_unchanged(tmp_path):
    engine = make_engine(tmp_path)
    _, base = run(engine, req(False))
    _, resp = run(engine, req(True))
    assert [it.model_dump() for it in resp.items] == [it.model_dump() for it in base.items]
    assert not resp.diversification["surprise"]["applied"]


def test_contributions_sum_to_score(tmp_path):
    engine = make_engine(tmp_path, bold_map(i7=3, i4=2))
    deep, resp = run(engine, req(True))
    by_id = {it.item_id: it for it in deep.items}
    for it in resp.items:
        assert abs(sum(c.contribution for c in it.contributions) - it.score) < 1e-6
        assert it.score == by_id[it.item_id].score
