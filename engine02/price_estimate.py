"""Every item gets a price: the listed one when the catalog has it, otherwise a clearly-labelled
estimate -- plus one comparable number (`price_twd`) for budgets across currencies.

Why estimate at all: budget filters, 「一套 3,000 元」 outfits, cost-per-wear and the travel capsule
all need a number, and most public catalogs (KAGL, Polyvore, H&M) ship none. An estimate is a
different claim from a price tag, so it is never silent:

  * `price_estimated` is True on every estimated row, `price_basis` says how it was reached
    (「估計價（非實際標價）：Dress 類基準 1,190 元 × 正式場合 1.2」);
  * `attr_source.price` becomes "estimated:price-estimate-v1" (never used as ground truth);
  * cards, the ENGINE 01 product attributes, rent-or-buy and the capsule all say 「估計價」, and a
    budget that relied on estimates says how many.

The estimator is deliberately a plain, deterministic table (no GPU, no key, same result on every
machine -- a fresh clone gets the same prices): a mass-market Taiwan base price per product type
(anchored on H&M / Uniqlo / NET price points and the real prices in data/catalog/crawl_tw), times
a few stated modifiers (formal occasion, bold design, premium material, catalog tier), times a fixed
±15% spread from the item id so that two T-shirts do not cost exactly the same, rounded to a shop
price (399, 1,190). Listed prices are never touched. `ENGINE02_ESTIMATE_PRICES=0` turns it off.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from functools import lru_cache

import numpy as np
import pandas as pd

ESTIMATOR_VERSION = "price-estimate-v1"

# Approximate TWD per unit (2026-09). Only used to put listed prices in different currencies on one
# scale for budgets; the listed price and its currency are kept as they are.
TWD_PER = {"TWD": 1.0, "NTD": 1.0, "USD": 32.0, "EUR": 35.0, "GBP": 41.0, "JPY": 0.21, "CNY": 4.4,
           "HKD": 4.1, "KRW": 0.023, "SGD": 24.0, "AUD": 21.0, "CAD": 23.5, "INR": 0.38, "SEK": 3.0}

# (pattern, label, base TWD) -- first match wins, so specific before generic ("t-shirt" before
# "shirt", "vest top" before "vest", "sports shoe" before "shoe"). Matched against subcategory first
# (short, clean: "Tshirts", "Ankle Booties"), then the title.
RULES: list[tuple[str, str, int]] = [
    # accessories & jewellery
    (r"watch", "手錶", 2490), (r"sunglass|eyewear|眼鏡", "太陽眼鏡", 890),
    (r"necklace|earring|bracelet|bangle|\brings?\b|pendant|jewel|項鍊|耳環|手鍊|戒指", "飾品", 490),
    (r"\bbelts?\b|皮帶", "皮帶", 590), (r"wallet|purse|皮夾", "皮夾", 790),
    (r"scar(f|ves)|stole|muffler|shawl|圍巾|絲巾", "圍巾", 590),
    (r"\bcaps?\b|\bhats?\b|beanie|帽(?!T)", "帽子", 490), (r"socks?|襪", "襪子", 199),
    (r"\bties?\b|領帶", "領帶", 690), (r"gloves?|mittens?|手套", "手套", 490),
    (r"perfume|fragrance|deodorant|香水", "香氛", 990),
    (r"lipstick|lip gloss|nail|makeup|cosmetic|eyeliner|kajal|mascara|eyeshadow|foundation|primer|"
     r"highlighter|blush|concealer|hair colou?r|彩妝|口紅", "彩妝", 390),
    (r"night ?suits?|pyjama|pajama|sleepwear|nightwear|睡衣", "睡衣", 590),
    (r"\bbras?\b|underwear|briefs?|boxers?|lingerie|panties|內衣|內褲", "內著", 390),
    (r"swim|bikini|泳", "泳裝", 790),
    # bags
    (r"backpack|後背包|背包", "後背包", 1290),
    (r"handbag|shoulder bag|tote|clutch|satchel|bucket|crossbody|手提包|肩背包|托特", "手提包", 1290),
    (r"\bbags?\b|包", "包款", 990),
    # shoes
    (r"boot|bootie|靴", "靴子", 2490),
    (r"sneaker|sports? shoe|trainer|running|球鞋|運動鞋", "運動鞋", 1990),
    (r"heels?|pumps?|高跟", "高跟鞋", 1490), (r"formal shoe|oxford|loafer|derby|皮鞋", "皮鞋", 1990),
    (r"sandal|slipper|flip ?flop|slides?\b|拖鞋|涼鞋", "涼拖鞋", 690), (r"flats?\b|ballet", "平底鞋", 990),
    (r"shoe|鞋", "鞋款", 1490),
    # tops that other rules would steal
    (r"vest top|tank|camisole|strap top|背心", "背心", 299),
    (r"hoodie|sweatshirt|大學T|帽T", "帽T／大學T", 990),          # before t-shirt: "sweaTSHIRTs"
    (r"t-?shirts?|\btees?\b|圓領T|短T|長T|T恤", "T 恤", 399),
    # outerwear ("waistcoat" is not a coat)
    (r"(?<!waist)coat|trench|大衣", "大衣", 2990), (r"puffer|\bdown\b|parka|羽絨|派克", "羽絨外套", 2490),
    (r"blazer|\bsuits?\b|西裝", "西裝外套", 2290),
    (r"jacket|bomber|windbreaker|anorak|外套|夾克", "外套", 1790),
    (r"cardigan|開襟", "開襟衫", 990), (r"gilet|\bvests?\b|waistcoat", "背心外套", 990),
    # one-pieces
    (r"jumpsuit|playsuit|romper|dungaree|overall|連身褲|吊帶褲", "連身褲", 1290), (r"dress|gown|洋裝|長洋|短洋", "洋裝", 1190),
    (r"kurta|saree|sari|lehenga|salwar|dupatta", "民族服飾", 990),
    # bottoms
    (r"legging|內搭褲", "內搭褲", 499), (r"jeans|denim|牛仔", "牛仔褲", 1290),
    (r"shorts|短褲", "短褲", 690), (r"skirt|裙", "裙子", 890),
    (r"trouser|pants|chino|jogger|褲", "長褲", 990),
    # tops
    (r"sweater|jumper|knit|pullover|毛衣|針織", "毛衣", 990),
    (r"shirt|blouse|襯衫", "襯衫", 790), (r"\btops?\b|上衣", "上衣", 590),
]
_RULES = [(re.compile(p, re.IGNORECASE), label, base) for p, label, base in RULES]

CATEGORY_BASE = {"top": ("上衣", 590), "bottom": ("下身", 990), "dress": ("洋裝", 1190),
                 "outerwear": ("外套", 1990), "shoes": ("鞋款", 1490), "bag": ("包款", 990),
                 "accessory": ("配件", 590), "jewelry": ("飾品", 490), "other": ("服飾", 690)}

PREMIUM = re.compile(r"cashmere|\bsilk\b|(?<!imitation )(?<!faux )leather|\bwool\b|suede|真皮|羊毛|羊絨|喀什米爾|蠶絲",
                     re.IGNORECASE)
# catalog tier by `source`: Polyvore sets were designer-heavy; KAGL is Myntra's Indian mass market
TIER = [(re.compile(r"polyvore", re.I), "設計師品牌居多", 1.6), (re.compile(r"kagl|myntra", re.I), "平價電商", 0.9)]


def _num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or f < 0 else f


def _text(v) -> str:
    return "" if v is None or (isinstance(v, float) and math.isnan(v)) else str(v)


def shop_round(x: float) -> float:
    """399 / 1,190 style: below 300 to 49/99, otherwise to the hundred minus 10."""
    if x < 300:
        return float(max(99, round(x / 50) * 50 - 1))
    return float(round(x / 100) * 100 - 10)


def _spread(item_id: str) -> float:
    h = int(hashlib.sha1(str(item_id).encode("utf-8")).hexdigest()[:8], 16) / 0xFFFFFFFF
    return 0.85 + 0.30 * h


@lru_cache(maxsize=65536)
def _match(text: str) -> tuple[str, int] | None:
    """The first rule matching `text` (cached: a catalog has a few hundred subcategory strings)."""
    if not text:
        return None
    for pat, lab, b in _RULES:
        if pat.search(text):
            return lab, b
    return None


def estimate_price(row: dict) -> tuple[float, str]:
    """(price in TWD, basis sentence) for one catalog row. Deterministic."""
    sub, title = _text(row.get("subcategory")), _text(row.get("title"))
    label = base = None
    hit = _match(sub) or _match(title)
    if hit:
        label, base = hit
    if base is None:
        label, base = CATEGORY_BASE.get(_text(row.get("category")).lower(), CATEGORY_BASE["other"])
    mods: list[tuple[str, float]] = []
    occ = _text(row.get("occasion")).lower()
    if occ == "formal":
        mods.append(("正式場合", 1.2))
    elif occ == "smart casual":
        mods.append(("商務休閒", 1.1))
    bold = _num(row.get("boldness"))
    if bold is not None and bold >= 3:
        mods.append(("設計感強", 1.3))
    elif bold is not None and bold >= 2:
        mods.append(("設計感", 1.15))
    if PREMIUM.search(f"{sub} {title}"):
        mods.append(("高級材質", 1.3))
    src = _text(row.get("source"))
    for pat, lab, f in TIER:
        if pat.search(src):
            mods.append((lab, f))
            break
    x = float(base) * _spread(row.get("item_id"))
    for _, f in mods:
        x *= f
    price = shop_round(x)
    basis = f"估計價（非實際標價）：{label}類基準 {base:,} 元" + "".join(f" × {n} {f:g}" for n, f in mods)
    return price, basis


def to_twd(price, currency) -> float | None:
    """A listed price in TWD, for comparisons only; unknown currency -> None (never guessed)."""
    p = _num(price)
    if p is None:
        return None
    cur = _text(currency).strip().upper() or "TWD"
    rate = TWD_PER.get(cur)
    return None if rate is None else p * rate


def fill_missing_prices(items: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Estimated prices for rows without one; adds price_estimated, price_basis, price_twd.
    Listed prices are kept. Returns (items, number of rows estimated in this call). Deterministic: a second call gives the same values."""
    df = items.copy()
    if "currency" not in df.columns:
        df["currency"] = None
    price = pd.to_numeric(df.get("price"), errors="coerce") if "price" in df.columns else \
        pd.Series(np.nan, index=df.index)
    already = df["price_estimated"].fillna(False).astype(bool) if "price_estimated" in df.columns else \
        pd.Series(False, index=df.index)
    # rows estimated earlier are re-estimated with the current rules, so a file written by an
    # older table and the service can never disagree; listed prices are never touched
    missing = price.isna() | already
    est_vals, bases = {}, {}
    if missing.any():
        sub = df.loc[missing]
        for idx, row in zip(sub.index, sub.to_dict("records")):
            est_vals[idx], bases[idx] = estimate_price(row)
    df["price"] = price.astype("float64")
    if est_vals:
        idx = list(est_vals)
        df.loc[idx, "price"] = [est_vals[i] for i in idx]
        df["currency"] = df["currency"].astype(object)
        df.loc[idx, "currency"] = "TWD"
    df["price_estimated"] = already | missing
    if "price_basis" not in df.columns:
        df["price_basis"] = None
    df["price_basis"] = df["price_basis"].astype(object)
    if bases:
        df.loc[list(bases), "price_basis"] = [bases[i] for i in bases]
    if "attr_source" in df.columns and est_vals:
        def mark(s):
            try:
                d = json.loads(s) if isinstance(s, str) and s.strip().startswith("{") else {}
            except ValueError:
                d = {}
            d["price"] = f"estimated:{ESTIMATOR_VERSION}"
            return json.dumps(d, ensure_ascii=False)
        df.loc[list(est_vals), "attr_source"] = df.loc[list(est_vals), "attr_source"].map(mark)
    df["price_twd"] = [to_twd(p, c) for p, c in zip(df["price"], df["currency"])]
    return df, len(est_vals)


def enabled() -> bool:
    return os.environ.get("ENGINE02_ESTIMATE_PRICES", "1").strip().lower() not in ("0", "false", "no", "off")


def comparable_price(items: pd.DataFrame, currency: str | None = "TWD") -> np.ndarray:
    """Prices on one scale for a budget in `currency` (NaN when unknown). Uses price_twd when the
    catalog has it, so a US$450 jacket is never compared with a NT$3,000 budget as 450."""
    n = len(items)
    if "price" not in items.columns:
        return np.full(n, np.nan)
    if "price_twd" in items.columns:
        twd = pd.to_numeric(items["price_twd"], errors="coerce").to_numpy(dtype=float, copy=True)
    elif "currency" in items.columns:
        twd = np.array([np.nan if (v := to_twd(p, c)) is None else v
                        for p, c in zip(items["price"], items["currency"])], dtype=float)
    else:
        return pd.to_numeric(items["price"], errors="coerce").to_numpy(dtype=float, copy=True)
    rate = TWD_PER.get((currency or "TWD").strip().upper())
    return twd if rate is None else twd / rate
