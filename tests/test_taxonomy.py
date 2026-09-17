from pathlib import Path

import pandas as pd
import pytest

from engine02.constraints import filter_with_relaxation
from engine02.contracts import HardConstraints, Slot, SlotState
from engine02.taxonomy import (
    ancestors,
    catalog_values,
    filter_with_category_relaxation,
    load_taxonomy,
    normalize_category,
    relax_ladder,
    resolve_category_values,
)

ROOT = Path(__file__).resolve().parents[1]
TAX = load_taxonomy()

# (query, expected ids — order-insensitive, exact set)
QUERIES = [
    ("T恤", {"tops.tshirts"}),
    ("短T", {"tops.tshirts"}),
    ("ｔ恤", {"tops.tshirts"}),  # full-width
    ("上衣", {"tops"}),
    ("襯衫", {"tops.shirts"}),
    ("雪紡衫", {"tops.blouses"}),
    ("POLO衫", {"tops.polos"}),
    ("帽T", {"tops.sweatshirts_hoodies"}),
    ("大學T", {"tops.sweatshirts_hoodies"}),
    ("毛衣", {"tops.sweaters"}),
    ("針織外套", {"tops.cardigans"}),
    ("小可愛", {"tops.tanks_camis"}),
    ("背心", {"tops.tanks_camis", "outerwear.vests"}),
    ("西裝外套", {"outerwear.blazers"}),
    ("我想買一件黑色西裝外套", {"outerwear.blazers"}),
    ("西裝", {"outerwear.blazers", "sets.suits"}),
    ("外套", {"outerwear"}),
    ("大衣", {"outerwear.coats"}),
    ("羽絨外套", {"outerwear.jackets"}),
    ("牛仔褲", {"bottoms.jeans"}),
    ("運動褲", {"bottoms.track_pants"}),
    ("瑜珈褲", {"bottoms.leggings"}),
    ("瑜伽褲", {"bottoms.leggings"}),
    ("運動短褲", {"bottoms.shorts", "coll.activewear"}),
    ("褲子", {"bottoms"}),
    ("窄裙", {"bottoms.skirts"}),
    ("洋裝", {"dresses.dresses", "dresses.party_dresses"}),
    ("連身裙", {"dresses.dresses", "dresses.party_dresses"}),
    ("小禮服", {"dresses.party_dresses"}),
    ("婚紗", {"dresses.gowns"}),
    ("連身褲", {"dresses.jumpsuits_rompers"}),
    ("運動內衣", {"intimates.sports_bras"}),
    ("睡衣", {"intimates.sleepwear"}),
    ("比基尼", {"swimwear.bikinis"}),
    ("高跟鞋", {"shoes.heels"}),
    ("運動鞋", {"shoes.athletic", "shoes.sneakers"}),
    ("樂福鞋", {"shoes.loafers"}),
    ("包", {"bags"}),
    ("後背包", {"bags.backpacks"}),
    ("皮夾", {"bags.wallets"}),
    ("手錶", {"accessories.watches"}),
    ("黑色帽子", {"accessories.hats"}),
    ("耳環", {"jewelry.earrings"}),
    ("口紅", {"beauty.makeup"}),
    ("運動服", {"coll.activewear"}),
    ("想找上班穿的襯衫和窄裙", {"tops.shirts", "bottoms.skirts"}),
    ("衣服", set()),
    ("", set()),
    # English / catalog vocabulary (what GPT copies from GET /vocabulary)
    ("blazer", {"outerwear.blazers"}),
    ("Sportcoats & Blazers", {"outerwear.blazers"}),
    ("Tshirts", {"tops.tshirts"}),
    ("T-Shirts", {"tops.tshirts"}),
    ("Casual Shoes", {"shoes.sneakers"}),
    ("Day Dresses", {"dresses.dresses"}),
    ("Kurtas", {"tops.kurtas"}),
    ("sweatpants", {"bottoms.track_pants"}),
    ("dress shirt", {"tops.shirts"}),
    ("track pants", {"bottoms.track_pants"}),
    ("outerwear.blazers", {"outerwear.blazers"}),
]


@pytest.mark.parametrize("q,expected", QUERIES)
def test_normalize_category(q, expected):
    assert set(normalize_category(q)) == expected


def test_hierarchy_and_ladder():
    assert ancestors("outerwear.blazers") == ["outerwear"]
    assert ancestors("outerwear") == []
    assert relax_ladder("outerwear.blazers") == ["outerwear.blazers", "outerwear", None]
    assert relax_ladder("tops") == ["tops", None]
    assert relax_ladder("coll.activewear") == ["coll.activewear", None]
    with pytest.raises(KeyError):
        relax_ladder("nope")


def test_every_node_well_formed():
    for nid, n in TAX.nodes.items():
        assert n["label_zh"] and n["label_en"]
        if n["level"] > 1:
            assert n["parent"] in TAX.nodes
        assert n["legacy_coarse"] in {"top", "bottom", "outerwear", "dress", "shoes", "bag", "accessory", "jewelry", "other"}
        if n.get("gpt"):
            assert n["gpt"]["path_en"].startswith(("Apparel", "Luggage", "Health", "Home", "Electronics"))


def test_catalog_values_cross_vocabulary():
    assert catalog_values("outerwear.blazers", "kagl") == ["Blazers"]
    merged = set(catalog_values("outerwear.blazers", "kagl_polyvore"))
    assert {"Blazers", "Sportcoats & Blazers", "Men's Sportcoats & Blazers"} >= merged >= {"Blazers"}
    tees = set(catalog_values("tops.tshirts", "kagl_polyvore"))
    assert {"Tshirts", "T-Shirts"} <= tees
    # L1 includes all descendants
    assert set(catalog_values("tops", "kagl")) >= {"Tshirts", "Shirts", "Kurtas", "Tops", "Sweaters"}
    assert "Casual Shoes" in catalog_values("shoes", "kagl")


def test_source_ambiguous_values_resolve_by_source_column():
    items = pd.DataFrame({
        "subcategory": ["Camisoles", "Camisoles", "Tights", "Tights"],
        "source": ["Marqo/KAGL", "Marqo/polyvore", "Marqo/KAGL", "Marqo/polyvore"],
    })
    assert TAX.category_mask(items, ["tops.tanks_camis"], "kagl_polyvore").tolist() == [False, True, False, False]
    assert TAX.category_mask(items, ["accessories.hosiery"], "kagl_polyvore").tolist() == [False, False, False, True]
    assert TAX.category_mask(items, ["bottoms.shorts", "coll.activewear"]).sum() == 0


def _toy():
    rows = [("Blazers", "navy"), ("Jackets", "navy"), ("Jackets", "navy"), ("Coats", "black"), ("Tshirts", "navy"),
            ("Shorts", "black"), ("Activewear Shorts", "black")]
    return pd.DataFrame({
        "item_id": [str(i) for i in range(len(rows))], "subcategory": [r[0] for r in rows],
        "category": ["outerwear", "outerwear", "outerwear", "outerwear", "top", "bottom", "bottom"],
        "color": [r[1] for r in rows], "season": None, "occasion": None, "gender": None, "price": None,
        "source": ["Marqo/polyvore"] * len(rows),
    })


def test_hierarchical_relaxation_backs_off_before_dropping_colour():
    items = _toy()
    c = HardConstraints(category=Slot(state=SlotState.VALUE, values=["西裝外套"]),
                        color=Slot(state=SlotState.VALUE, values=["navy"]))
    legacy = filter_with_relaxation(items, c, 3)
    assert legacy.mask.sum() == 0  # legacy: category never relaxed, zh value never matches
    fr = filter_with_category_relaxation(items, c, 3, catalog="polyvore")
    assert fr.mask.tolist() == [True, True, True, False, False, False, False]  # navy outerwear, colour kept
    assert fr.relaxed[0].startswith("category:outerwear.blazers→outerwear")
    assert "color:drop" not in fr.relaxed


def test_specific_category_kept_when_enough():
    items = _toy()
    c = HardConstraints(category=Slot(state=SlotState.VALUE, values=["outerwear.blazers"]))
    fr = filter_with_category_relaxation(items, c, 1, catalog="polyvore")
    assert fr.mask.tolist() == [True] + [False] * 6 and fr.relaxed == []


def test_collection_intersection_then_dropped():
    items = _toy()
    c = HardConstraints(category=Slot(state=SlotState.VALUE, values=["運動短褲"]))
    fr = filter_with_category_relaxation(items, c, 1, catalog="polyvore")
    assert fr.mask.tolist() == [False] * 6 + [True]
    fr2 = filter_with_category_relaxation(items, c, 2, catalog="polyvore")
    assert fr2.mask.tolist() == [False] * 5 + [True, True]
    assert fr2.relaxed and fr2.relaxed[0].startswith("category:")


def test_unresolvable_values_fall_back_to_legacy():
    items = _toy()
    c = HardConstraints(category=Slot(state=SlotState.VALUE, values=["outerwear"]))  # legacy coarse name
    assert resolve_category_values(["outerwear"]) == ["outerwear"]
    fr = filter_with_category_relaxation(items, c, 1, catalog="polyvore")
    assert fr.mask.sum() == 4
    c2 = HardConstraints(category=Slot(state=SlotState.VALUE, values=["zzz-unknown"]))
    assert filter_with_category_relaxation(items, c2, 1).mask.sum() == filter_with_relaxation(items, c2, 1).mask.sum()


def test_closed_vocabulary_compact():
    v = TAX.closed_vocabulary()
    assert "beauty" not in v["category"] and "outerwear.blazers" in v["category"]["outerwear"]["children"]
    import json
    assert len(json.dumps(v, ensure_ascii=False)) < 12000


LOCAL = [("kagl", ROOT / "data/catalog/kagl/items.parquet", 0.99), ("polyvore", ROOT / "data/catalog/polyvore/items.parquet", 0.89)]


@pytest.mark.parametrize("name,path,min_share", LOCAL)
def test_local_catalog_coverage(name, path, min_share):
    if not path.exists():
        pytest.skip(f"{path} not available")
    df = pd.read_parquet(path, columns=["subcategory"])
    src = name
    entries = TAX.maps[src]
    missing = sorted(set(df["subcategory"].dropna()) - set(entries))
    assert not missing, f"values without an explicit decision: {missing}"
    mapped = df["subcategory"].map(lambda v: entries.get(v, {}).get("status") in ("mapped", "mapped_l1", "collection"))
    assert mapped.mean() >= min_share
