import pandas as pd

from engine02.context.base import DailyForecast
from engine02.contracts import HardConstraints
from engine02.services import advise, decode, plan_capsule


def _catalog(with_price=True):
    rows = [
        ("t1", "白色棉T", "top", "White", 1, 390),
        ("t2", "黑色針織上衣", "top", "Black", 1, 590),
        ("t3", "灰色條紋上衣", "top", "Grey", 1, 490),
        ("t4", "紅色襯衫", "top", "Red", 1, 690),
        ("b1", "深藍牛仔褲", "bottom", "Navy Blue", 1, 890),
        ("b2", "米色寬褲", "bottom", "Beige", 1, 790),
        ("b3", "綠色短裙", "bottom", "Green", 0, 650),
        ("d1", "粉色洋裝", "dress", "Pink", 1, 1290),
        ("s1", "白色球鞋", "shoes", "White", 1, 1490),
        ("s2", "黑色樂福鞋", "shoes", "Black", 1, 1990),
        ("o1", "卡其風衣", "outerwear", "Beige", 2, 2490),
        ("o2", "黑色防潑水外套", "outerwear", "Black", 2, 1990),
        ("o3", "羽絨外套", "outerwear", "Navy Blue", 3, 3990),
    ]
    df = pd.DataFrame(rows, columns=["item_id", "title", "category", "color", "warmth", "price"])
    df["water_repellent"] = df["item_id"].eq("o2")
    if not with_price:
        df = df.drop(columns=["price"])
    return df


def _days(rain=False):
    return [DailyForecast(date=f"2026-10-0{i}", place="台北", lat=25.03, lon=121.56,
                          temp_min_c=17, temp_max_c=24,
                          precip_prob_pct=80 if (rain and i == 2) else 10)
            for i in (1, 2, 3)]


def test_capsule_respects_n_items_and_multiplies_outfits():
    out = plan_capsule(_catalog(), _days(), n_items=8)
    assert len(out["items"]) <= 8
    assert out["n_outfits"] > len(out["items"])
    assert out["n_outfits"] == len(out["outfits"])
    assert len(out["per_day_plan"]) == 3
    # 3 days, enough outfits -> no repeats
    looks = [tuple(sorted(i for i in d["outfit"] if not i.startswith("o"))) for d in out["per_day_plan"]]
    assert len(set(looks)) == 3
    assert "套穿搭" in out["notes_zh"][0]


def test_capsule_colour_rule_one_non_neutral_per_outfit():
    out = plan_capsule(_catalog(), _days(), n_items=10)
    colors = {r["item_id"]: r["color"] for r in out["items"]}
    neutral = {"Black", "White", "Grey", "Navy Blue", "Beige"}
    for look in out["outfits"]:
        assert sum(colors[i] not in neutral for i in look) <= 1


def test_capsule_budget_respected_and_unpriced_skipped():
    df = _catalog()
    df.loc[df["item_id"] == "t1", "price"] = None
    out = plan_capsule(df, _days(), n_items=8, budget=5000)
    assert out["total_price"] <= 5000
    assert "t1" not in [r["item_id"] for r in out["items"]]
    assert any("沒有標價" in n for n in out["notes_zh"])
    assert out["n_outfits"] >= 1


def test_capsule_rain_brings_water_repellent_outer():
    out = plan_capsule(_catalog(), _days(rain=True), n_items=7)
    ids = [r["item_id"] for r in out["items"]]
    assert "o2" in ids
    rainy = out["per_day_plan"][1]
    assert "o2" in rainy["outfit"]
    assert "防潑水" in rainy["why_zh"]


def test_capsule_hot_trip_drops_puffer_and_impossible_budget_is_reported():
    hot = [DailyForecast(date="2026-07-01", place="墾丁", lat=22.0, lon=120.7,
                         temp_min_c=28, temp_max_c=33, precip_prob_pct=0)]
    out = plan_capsule(_catalog(), hot, n_items=8)
    assert "o3" not in [r["item_id"] for r in out["items"]]
    broke = plan_capsule(_catalog(), hot, n_items=8, budget=100)
    assert broke["n_outfits"] == 0 and broke["notes_zh"]


def test_dress_code_decodes_many_phrases():
    cases = {
        "Black Tie": "Formal",
        "Cocktail attire": "Formal",
        "Dress code: smart casual": "Smart Casual",
        "business casual please": "Smart Casual",
        "請穿著正式服裝": "Formal",
        "休閒輕鬆就好": "Casual",
        "海灘婚禮": "Smart Casual",
    }
    for text, occ in cases.items():
        r = decode(text)
        assert occ in r["constraints"]["occasion"]["values"], text
        assert r["confidence"] > 0.5 and r["explanation_zh"]
        HardConstraints(**r["constraints"])  # must be valid engine input

    white = decode("白色派對")
    assert "White" in white["constraints"]["color"]["values"]
    dark = decode("請著深色系")
    assert "Black" in dark["constraints"]["color"]["values"]
    assert dark["design_steps"]["dark_tone"] > 0


def test_dress_code_ban_white_and_wedding_etiquette():
    r = decode("禁穿白色")
    assert "White" in r["constraints"]["excluded_values"]["color"]
    assert "color" not in r["constraints"]
    w = decode("週六中午喜宴，歡迎盛裝出席")
    assert "White" in w["constraints"]["excluded_values"]["color"]
    assert "新娘" in w["explanation_zh"]
    assert w["design_steps"]["dark_tone"] < 0
    HardConstraints(**w["constraints"])
    # a white party at a wedding still cannot require white
    both = decode("婚禮 白色派對")
    assert "color" not in both["constraints"]


def test_dress_code_unknown_is_empty():
    r = decode("隨便啦哈哈 xyz")
    r2 = decode("qwerty")
    assert r2["constraints"] == {} and r2["confidence"] == 0.0 and r2["explanation_zh"]
    assert decode("")["constraints"] == {}
    assert isinstance(r, dict)


def test_rent_or_buy_rules_and_no_invented_price():
    gown = {"title": "亮片長禮服", "boldness": 3, "price": 6800}
    r = advise(gown, "尾牙", 1)
    assert r["advice"] == "rent" and "租比較划算" in r["explanation_zh"]
    assert r["cost_per_wear"] == 6800

    tee = {"title": "白色素T", "boldness": 0, "price": 390}
    b = advise(tee, None, 30)
    assert b["advice"] == "buy" and b["cost_per_wear"] == 13.0

    no_price = advise({"title": "黑色西裝褲", "boldness": 0}, None, 20)
    assert no_price["advice"] == "buy"
    assert no_price["cost_per_wear"] is None
    assert "不猜價格" in no_price["explanation_zh"]

    no_price_rent = advise({"title": "禮服", "boldness": 3}, "婚禮", None)
    assert no_price_rent["advice"] == "rent" and no_price_rent["cost_per_wear"] is None

    bold_often = advise({"title": "螢光外套", "boldness": 2, "price": 3000}, None, 10)
    assert bold_often["advice"] == "either" and bold_often["cost_per_wear"] == 300.0
