"""engine02.price_estimate: every item priced, estimates labelled, listed prices untouched."""

import json

import numpy as np
import pandas as pd

from engine02.catalog import Catalog
from engine02.contracts import BudgetSlot, HardConstraints, SlotState
from engine02.price_estimate import comparable_price, estimate_price, fill_missing_prices, shop_round


def _items():
    return pd.DataFrame([
        {"item_id": "a", "title": "Basic tee", "subcategory": "T-shirt", "category": "top", "price": None,
         "currency": None, "occasion": "Casual", "boldness": 0, "source": "hm",
         "attr_source": json.dumps({"price": "null"}), "image_path": "images/a.jpg"},
        {"item_id": "b", "title": "Wool coat", "subcategory": "Coat", "category": "outerwear", "price": None,
         "currency": None, "occasion": "Formal", "boldness": 2, "source": "hm",
         "attr_source": json.dumps({"price": "null"}), "image_path": "images/b.jpg"},
        {"item_id": "c", "title": "SSENSE parka", "subcategory": None, "category": "outerwear", "price": 450.0,
         "currency": "USD", "source": "ssense", "attr_source": json.dumps({"price": "structured"}),
         "image_path": "images/c.jpg"},
        {"item_id": "d", "title": "蕾絲長洋", "subcategory": None, "category": "dress", "price": 1280.0,
         "currency": "TWD", "source": "iroo", "attr_source": json.dumps({"price": "structured"}),
         "image_path": "images/d.jpg"},
    ])


def test_missing_prices_are_estimated_and_labelled_listed_ones_untouched():
    df, n = fill_missing_prices(_items())
    assert n == 2 and df["price"].notna().all()
    est = df.set_index("item_id")
    assert est.loc["a", "price_estimated"] and est.loc["b", "price_estimated"]
    assert not est.loc["c", "price_estimated"] and est.loc["c", "price"] == 450.0 and est.loc["c", "currency"] == "USD"
    assert est.loc["d", "price"] == 1280.0 and est.loc["d", "price_basis"] is None
    assert "估計價" in est.loc["b", "price_basis"] and "正式場合" in est.loc["b", "price_basis"]
    assert json.loads(est.loc["a", "attr_source"])["price"].startswith("estimated:")
    assert json.loads(est.loc["c", "attr_source"])["price"] == "structured"
    # a wool coat for a formal occasion costs more than a basic tee
    assert est.loc["b", "price"] > 3 * est.loc["a", "price"]
    # the US$450 parka is compared as NT$14,400, not as 450
    assert est.loc["c", "price_twd"] == 450.0 * 32.0


def test_estimates_are_deterministic_idempotent_and_shop_rounded():
    a, _ = fill_missing_prices(_items())
    b, n = fill_missing_prices(a)
    assert n == 2 and a["price"].tolist() == b["price"].tolist() and b["price_estimated"].tolist() == a["price_estimated"].tolist()
    assert shop_round(1234) == 1190 and shop_round(260) == 249 and shop_round(40) == 99
    p1, _ = estimate_price({"item_id": "x", "subcategory": "Tshirts", "category": "top"})
    p2, _ = estimate_price({"item_id": "x", "subcategory": "Tshirts", "category": "top"})
    assert p1 == p2 and 249 <= p1 <= 499


def test_rules_pick_the_specific_type_first():
    def label(sub, title=""):
        return estimate_price({"item_id": "i", "subcategory": sub, "title": title, "category": "other"})[1]
    assert "T 恤" in label("Tshirts") and "帽T" in label("Sweatshirts") and "背心" in label("Vest top")
    assert "運動鞋" in label("Sports Shoes") and "靴子" in label("Ankle Booties") and "手錶" in label("Watches")
    assert "洋裝" in label(None, "黑天鵝網紗長洋") and "外套" in label(None, "rnrn Windbreaker")
    # three the first table got wrong on the real catalogs
    assert "背心外套" in label("Tailored Waistcoat") and "睡衣" in label("Night suits")
    assert "彩妝" in label("Kajal and Eyeliner") and "連身褲" in label("Dungarees")


def test_catalog_load_estimates_unless_disabled(tmp_path, monkeypatch):
    _items().to_parquet(tmp_path / "items.parquet")
    cat = Catalog.load(tmp_path)
    assert cat.items["price"].notna().all() and cat.price_estimated(0) and not cat.price_estimated(2)
    monkeypatch.setenv("ENGINE02_ESTIMATE_PRICES", "0")
    assert Catalog.load(tmp_path).items["price"].isna().sum() == 2


def test_budget_compares_on_one_currency_and_counts_estimates():
    from engine02.constraints import build_mask
    df, _ = fill_missing_prices(_items())
    c = HardConstraints(budget=BudgetSlot(state=SlotState.VALUE, max_price=3000, currency="TWD"))
    mask, applied = _mask(build_mask, df, c)
    kept = set(df.loc[mask, "item_id"])
    assert "c" not in kept                        # US$450 > NT$3,000
    assert "d" in kept and "a" in kept
    assert int(applied["budget_estimated_prices"][0]) == len(kept & {"a", "b"})
    assert np.isclose(comparable_price(df, "USD")[2], 450.0)


def _mask(build_mask, df, c):
    mask, applied = build_mask(df, c, {})
    return np.asarray(mask, bool), applied
