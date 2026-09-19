"""scripts/crawl_to_catalog.py on synthetic records.json fixtures (offline), plus the structured
product facts engine02.crawl.extract now reads (category, sku, availability, color, gender)."""

from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import pandas as pd
import pytest
from PIL import Image

from engine02.crawl.extract import extract
from engine02.crawl.records import CSV_FIELDS, Record, export

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("crawl_to_catalog", ROOT / "scripts" / "crawl_to_catalog.py")
c2c = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(c2c)

SCHEMA = ["item_id", "title", "description", "category", "subcategory", "color", "season", "occasion",
          "gender", "price", "currency", "outfit_ids", "image_path", "source", "attr_source", "image_url"]


def rec(url, title, page_type="product", imgs=("https://img.a.test/1.jpg", "https://img.a.test/2.jpg"),
        source="pinkoi", **kw):
    base = {"source": source, "url": url, "title": title, "text": f"{title} desc", "brand": "Maker",
            "price": "1290", "currency": "TWD", "image_urls": list(imgs), "published_at": None,
            "account": None, "page_type": page_type, "fetched_at": "2026-09-19T10:00:00+00:00",
            "field_origin": {"title": "jsonld:Product.name", "price": "jsonld:Offer.price"}}
    base.update(kw)
    return base


FIXTURE = [
    rec("https://www.pinkoi.com/product/A1", "氣質素色洋裝雙口袋-深藍色", color="深藍色", gender="female"),
    rec("https://www.pinkoi.com/product/A1?utm_source=x", "氣質素色洋裝 again"),          # duplicate url
    rec("https://www.lativ.com.tw/product/72035", "純棉圓領T恤-男", source="lativ", price="179"),
    rec("https://www.pinkoi.com/product/B2", "【預購】Wemoji | 娃娃大集合包 (限量販售)", price="2880"),
    rec("https://www.pinkoi.com/product/C3", "2027 幹話日曆 365則厭世語錄與可愛插圖", price="939"),
    rec("https://www.pinkoi.com/product/D4", "Linen wide pants", price="N/A", currency=None),
    rec("https://www.pinkoi.com/product/E5", "Handmade thing", category="Clothing > Dresses", price="1,990"),
    rec("https://www.pinkoi.com/product/F6", "Leather tote", category="Toys"),              # title rule
    rec("https://www.pinkoi.com/product/G7", "No image jacket", imgs=()),
    rec("https://blog.test/fall-looks", "Fall looks: coats", page_type="article"),
]


@pytest.fixture()
def records_dir(tmp_path):
    d = tmp_path / "crawl" / "20260919T000000Z"
    d.mkdir(parents=True)
    (d / "records.json").write_text(json.dumps(FIXTURE, ensure_ascii=False), encoding="utf-8")
    return tmp_path / "crawl"


def _png(w=800, h=1000) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (10, 20, 30)).save(buf, "PNG")
    return buf.getvalue()


# ------------------------------------------------------------------------------------------ rules
@pytest.mark.parametrize("title,cat", [
    ("氣質素色洋裝雙口袋-深藍色", "dress"), ("宛如可穿戴藝術 拼色亞麻混紡長洋裝 260503-1", "dress"),
    ("連身裙", "dress"), ("長版dress", "dress"), ("毛衣外套", "outerwear"), ("Wool Coat", "outerwear"),
    ("寬褲", "bottom"), ("Denim JEANS", "bottom"), ("百褶裙", "bottom"), ("純棉圓領T恤-男", "top"),
    ("Oversized tee", "top"), ("Striped T-shirt", "top"), ("帆布鞋", "shoes"), ("Running sneakers", "shoes"),
    ("托特包", "bag"), ("canvas bag", "bag"),
    # names seen in the 2026-09-19 crawl that the first rules dropped as non-apparel
    ("暗黑浪漫絲絨蕾絲長洋", "dress"), ("Black Tonal Disc Louise Down Parka", "outerwear"),
    ("Off-White Fallon Fleece Puffer Down Vest", "outerwear"), ("rnrn Windbreaker", "outerwear"),
    ("rnrn Track Shell", "outerwear"), ("Crewneck Logo Sweatshirt 聯名大學T (海國)", "top"),
    ("輕薄涼感圓領T_黑(PS1561)", "top"), ("TW HOODIE 2 帽T 口袋 女款", "top"), ("rnrn Singlet 001", "top"),
    ("rnrn Crew Vest", "top"), ("皺皺透膚內搭 3colors", "top"),
    ("溫柔感真2件式套裝 3color", "other"),        # a set is two items; like H&M multipacks, left out
    ("rnrn Marathon Cap", "other"), ("rnrn Pace Socks", "other"), ("APFR INCENSE STICKS_FIG", "other"),
    ("海洋風格 保溫瓶", "other"), ("GOLDWIN BIG LOGO BEANIE_BLACK", "other"),
    ("【預購】a ~~~ Wemoji ! | 娃娃大集合包 (限量販售)", "other"),   # bare 包 is not a bag
    ("2027 幹話日曆 365則厭世語錄與可愛插圖", "other"), ("laptop sleeve", "other"), ("coating spray", "other"),
])
def test_title_rules(title, cat):
    assert c2c.rule_category(title)[0] == cat


def test_normalisers():
    assert c2c.norm_color("深藍色") == "Blue" and c2c.norm_color("navy blue") == "Navy Blue"
    assert c2c.norm_color("霧霾藍綠拼接") is None and c2c.norm_color(None) is None
    assert c2c.norm_gender("female") == "Women" and c2c.norm_gender("Unisex") == "Unisex"
    assert c2c.norm_gender("kids") is None
    assert c2c.parse_price("1,290") == 1290.0 and c2c.parse_price("N/A") is None and c2c.parse_price(None) is None
    assert c2c.item_id_of("https://x.test/p/1?utm_source=a") == c2c.item_id_of("https://X.test/p/1")


# ------------------------------------------------------------------------------------------ build
def test_build_offline(records_dir, tmp_path):
    out = tmp_path / "cat"
    items, stats = c2c.build([str(records_dir)], out)
    assert (out / "items.parquet").exists() and (out / "stats.json").exists() and (out / "README.md").exists()
    df = pd.read_parquet(out / "items.parquet")
    assert list(df.columns[: len(SCHEMA)]) == SCHEMA and "brand" in df.columns
    by_url = df.set_index("url")

    dress = by_url.loc["https://www.pinkoi.com/product/A1"]
    assert dress.category == "dress" and dress.color == "Blue" and dress.gender == "Women"
    assert dress.price == 1290.0 and dress.currency == "TWD" and dress.brand == "Maker"
    assert pd.isna(dress.season) and pd.isna(dress.occasion)
    assert dress.item_id.startswith("crawl_") and dress.image_path == f"images/{dress.item_id}.jpg"
    assert dress.image_url == "https://img.a.test/1.jpg"
    assert json.loads(dress.attr_source) == {"category": "title_rule", "color": "structured", "season": "null",
                                             "occasion": "null", "gender": "structured", "price": "structured"}

    tee = by_url.loc["https://www.lativ.com.tw/product/72035"]
    assert tee.category == "top" and pd.isna(tee.gender)     # "-男" in the title is not structured data
    pants = by_url.loc["https://www.pinkoi.com/product/D4"]
    assert pants.category == "bottom" and pd.isna(pants.price) and pd.isna(pants.currency)
    assert json.loads(pants.attr_source)["price"] == "null"
    struct = by_url.loc["https://www.pinkoi.com/product/E5"]
    assert struct.category == "dress" and struct.subcategory == "Clothing > Dresses" and struct.price == 1990.0
    assert json.loads(struct.attr_source)["category"] == "structured"
    tote = by_url.loc["https://www.pinkoi.com/product/F6"]    # structured "Toys" does not map -> title rule
    assert tote.category == "bag" and json.loads(tote.attr_source)["category"] == "title_rule"

    assert len(df) == 5 and df.item_id.is_unique
    assert stats["dropped"] == {"duplicate_url": 1, "not_apparel": 2, "no_image": 1, "not_product": 1}
    ex = [e["title"] for e in stats["dropped_examples"]["not_apparel"]]
    assert any("娃娃大集合包" in t for t in ex) and any("日曆" in t for t in ex)
    assert stats["items_by_source"] == {"pinkoi": 4, "lativ": 1}
    assert stats["price_coverage"] == 0.8 and stats["n_records_in"] == len(FIXTURE)
    assert "non-commercial" in (out / "README.md").read_text(encoding="utf-8").lower()


def test_apparel_only_off_and_max_items(records_dir, tmp_path):
    _, stats = c2c.build([str(records_dir)], tmp_path / "all", apparel_only=False)
    assert stats["n_items"] == 7 and stats["category"]["other"] == 2 and "not_apparel" not in stats["dropped"]
    _, stats = c2c.build([str(records_dir / "20260919T000000Z" / "records.json")], tmp_path / "few", max_items=2)
    assert stats["n_items"] == 2 and stats["dropped"]["max_items"] == 3


def test_download_images_polite(records_dir, tmp_path):
    inflight: dict[str, int] = {}
    peak: dict[str, int] = {}
    lock = threading.Lock()
    png = _png()

    def fake_fetch(url):
        host = url.split("/")[2]
        with lock:
            inflight[host] = inflight.get(host, 0) + 1
            peak[host] = max(peak.get(host, 0), inflight[host])
        time.sleep(0.05)
        with lock:
            inflight[host] -= 1
        if "broken" in url:
            raise OSError("404")
        return png

    many = [rec(f"https://www.pinkoi.com/product/X{i}", f"洋裝 {i}", imgs=(f"https://img.a.test/{i}.jpg",))
            for i in range(10)]
    many.append(rec("https://www.pinkoi.com/product/BROKEN", "外套", imgs=("https://img.b.test/broken.jpg",)))
    f = tmp_path / "records.json"
    f.write_text(json.dumps(many, ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "img"
    items, stats = c2c.build([str(f)], out, download=True, fetch=fake_fetch, workers=64)
    assert stats["n_items"] == 10 and stats["dropped"] == {"image_download_failed": 1}
    assert stats["images"] == {"ok": 10, "failed": 1}
    assert peak["img.a.test"] <= c2c.PER_HOST
    im = Image.open(out / items.iloc[0].image_path)
    assert max(im.size) == 384 and im.format == "JPEG"
    _, again = c2c.build([str(f)], out, download=True, fetch=fake_fetch)      # cached files are not refetched
    assert again["images"]["cached"] == 10


def test_cli(records_dir, tmp_path):
    out = tmp_path / "cli"
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "crawl_to_catalog.py"), "--records",
                        str(records_dir), "--out", str(out)], capture_output=True, text=True,
                       encoding="utf-8", cwd=ROOT)
    assert r.returncode == 0, r.stderr
    assert json.loads((out / "stats.json").read_text(encoding="utf-8"))["n_items"] == 5
    assert "dropped[not_apparel]" in r.stdout


# ------------------------------------------------------------------------ extract: new product facts
def test_extract_structured_product_facts():
    html = """<html><head><script type="application/ld+json">{"@context":"https://schema.org",
    "@type":"Product","name":"Linen dress","category":"Apparel & Accessories > Clothing > Dresses",
    "sku":"LD-01","color":"深藍色","audience":{"@type":"PeopleAudience","suggestedGender":"female"},
    "image":"/d.jpg","offers":{"@type":"Offer","price":"1813","priceCurrency":"TWD",
    "availability":"https://schema.org/InStock"}}</script></head></html>"""
    p = extract(html, "https://shop.test/p/1")
    assert (p["category"], p["sku"], p["availability"], p["color"], p["gender"]) == (
        "Apparel & Accessories > Clothing > Dresses", "LD-01", "InStock", "深藍色", "female")
    fo = p["field_origin"]
    assert fo["category"] == "jsonld:Product.category" and fo["availability"] == "jsonld:Offer.availability"
    assert fo["gender"] == "jsonld:Product.audience.suggestedGender" and fo["color"] == "jsonld:Product.color"


def test_extract_og_product_facts_and_absence():
    og = """<html><head><meta property="og:type" content="product"><meta property="og:title" content="Tee">
    <meta property="product:category" content="Tops"><meta property="product:retailer_item_id" content="T9">
    <meta property="product:availability" content="out of stock"><meta property="product:color" content="Black">
    <meta property="product:target_gender" content="unisex"></head></html>"""
    p = extract(og, "https://shop.test/p/2")
    assert (p["category"], p["sku"], p["availability"], p["color"], p["gender"]) == (
        "Tops", "T9", "out of stock", "Black", "unisex")
    assert p["field_origin"]["sku"] == "og:product:retailer_item_id"
    bare = extract('<html><head><meta property="og:type" content="product"></head></html>', "https://s.test/")
    assert all(bare[k] is None for k in ("category", "sku", "availability", "color", "gender"))
    assert not {"category", "sku", "availability", "color", "gender"} & set(bare["field_origin"])


def test_record_new_fields_appended(tmp_path):
    assert CSV_FIELDS[:13] == ["source", "url", "title", "text", "brand", "price", "currency", "image_urls",
                               "published_at", "account", "page_type", "fetched_at", "field_origin"]
    assert CSV_FIELDS[13:] == ["category", "sku", "availability", "color", "gender"]
    r = Record(source="s", url="https://x.test/p", title="Dress", category="Dresses", color="Black")
    paths = export([r], tmp_path)
    row = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))[0]
    assert row["category"] == "Dresses" and row["color"] == "Black" and row["gender"] is None
