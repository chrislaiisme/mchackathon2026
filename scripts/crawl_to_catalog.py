"""Turn crawler output (records.json from `python -m engine02.crawl`) into an ENGINE 02 catalog.

Same schema as scripts/prepare_catalog.py / prepare_catalog_hm.py (item_id, title, description,
category, subcategory, color, season, occasion, gender, price, currency, outfit_ids, image_path,
source, attr_source, image_url) plus crawl provenance columns (brand, url, sku, availability,
category_raw, color_raw, gender_raw, field_origin, fetched_at).

    python scripts/crawl_to_catalog.py --records out/crawl/20260919T102554Z --out data/catalog/crawl_tw
    python scripts/crawl_to_catalog.py --records a/records.json --records b/ --out X --download-images

Nothing is guessed:
  * price / currency exactly as the page stated them (price -> float when it parses, else null);
  * category from the page's structured category (JSON-LD Product.category / og product:category)
    when it maps to a coarse slot, else from the explicit TITLE keyword rules below
    (attr_source.category = "title_rule"); no match -> "other", dropped by --apparel-only (default);
  * color / gender only when structured data states them; season / occasion always null
    (scripts/vlm_fill_catalog.py fills them later with its own provenance).
Only page_type == "product" records with at least one image are kept; duplicates (same normalised
URL) are dropped. Every drop is counted by reason in stats.json, with examples.

Licence: third-party shop content -- non-commercial research demo only; images are not redistributed.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from engine02.crawl.records import normalize_url  # noqa: E402

MAX_SIDE = 384
MAX_WORKERS = 8
PER_HOST = 2
USER_AGENT = "ENGINE02-research-catalog/1.0 (non-commercial research demo)"
N_EXAMPLES = 5


def _en(*words: str) -> str:
    """English words delimited by non-letters (CJK text is \\w, so \\b would miss "長版dress")."""
    return r"(?<![a-z])(?:" + "|".join(words) + r")(?![a-z])"


# Ordered: the first matching slot wins. "連身裙" before 裙, "外套" before 上衣/毛衣 ("毛衣外套" is a
# cardigan jacket). A bare 包 is deliberately NOT a bag rule: "娃娃大集合包" (a bundle), "福袋包" --
# only compounds that name a bag count.
CATEGORY_RULES: list[tuple[str, re.Pattern]] = [(cat, re.compile(p, re.IGNORECASE)) for cat, p in [
    # 長洋 / 短洋: Taiwanese shop shorthand for 長洋裝 (iroo titles use nothing else); a bare 洋 is not
    # a rule (海洋, 洋蔥)
    ("dress", r"洋裝|長洋|短洋|連身裙|連衣裙|連身褲|" + _en("dress", "dresses", "jumpsuit")),
    ("outerwear", r"外套|夾克|大衣|風衣|羽絨|派克|防風|" + _en(
        "jacket", "jackets", "coat", "coats", "blazer", "blazers", "parka", "parkas", "puffer",
        "windbreaker", "anorak", "track shell")),
    ("bottom", r"褲|裙|" + _en("pants", "jeans", "shorts", "trousers", "skirt", "skirts")),
    # 大學T / 帽T / 圓領T / 短T / 長T are how Taiwanese shops name sweatshirts, hoodies and tees
    ("top", r"上衣|t恤|襯衫|毛衣|針織|背心|內搭|(?:大學|帽|圓領|短|長)T(?![a-z])|" + _en(
        "shirt", "shirts", "t-shirt", "t-shirts", "tee", "tees", "top", "tops", "knit", "knitwear",
        "sweater", "blouse", "sweatshirt", "sweatshirts", "hoodie", "hoodies", "singlet", "vest",
        "vests", "polo", "cardigan")),
    ("shoes", r"鞋|" + _en("shoes", "shoe", "sneakers", "sneaker")),
    ("bag", r"包包|背包|提包|肩背包|斜背包|側背包|托特包|腰包|手拿包|郵差包|水桶包|"
            + _en("bag", "bags", "tote", "backpack")),
]]
APPAREL = {cat for cat, _ in CATEGORY_RULES}

GENDER = {"male": "Men", "men": "Men", "man": "Men", "mens": "Men", "男": "Men", "男性": "Men", "男裝": "Men",
          "female": "Women", "women": "Women", "woman": "Women", "womens": "Women", "女": "Women",
          "女性": "Women", "女裝": "Women", "unisex": "Unisex", "中性": "Unisex", "男女": "Unisex"}


def rule_category(text: str | None) -> tuple[str, str | None]:
    """(coarse category, matched keyword) from the explicit rules; ("other", None) if none match."""
    for cat, pat in CATEGORY_RULES:
        m = pat.search(text or "")
        if m:
            return cat, m.group(0)
    return "other", None


def norm_color(raw: str | None) -> str | None:
    """A stated colour -> this catalog's vocabulary (engine02.attribute_fill); unresolvable -> None."""
    if not raw:
        return None
    from engine02.attribute_fill import COLOR_FAMILIES, COLOR_ZH, FAMILY_CANONICAL
    c = str(raw).strip().lower()
    for fam_cols in COLOR_FAMILIES.values():       # already a catalog colour, e.g. "Navy Blue"
        for col in fam_cols:
            if col.lower() == c:
                return col
    fam = COLOR_ZH.get(c) or COLOR_ZH.get(c.removesuffix("色")) or (c if c in COLOR_FAMILIES else None)
    return FAMILY_CANONICAL[fam] if fam else None


def norm_gender(raw: str | None) -> str | None:
    if not raw:
        return None
    return GENDER.get(str(raw).strip().lower())


def parse_price(v) -> float | None:
    if v is None:
        return None
    try:
        f = float(str(v).replace(",", "").strip())
    except ValueError:
        return None
    return f if f == f and f >= 0 else None


def item_id_of(url: str) -> str:
    return "crawl_" + hashlib.sha1(normalize_url(url).encode("utf-8")).hexdigest()[:12]


def find_records(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for p in map(Path, paths):
        if p.is_file():
            files.append(p)
        elif (p / "records.json").is_file():
            files.append(p / "records.json")
        elif p.is_dir():
            files += sorted(p.rglob("records.json"))
        else:
            raise FileNotFoundError(f"no records.json at {p}")
    return files


def _example(r: dict, **extra) -> dict:
    return {"source": r.get("source"), "title": r.get("title"), "url": r.get("url"), **extra}


def to_row(r: dict) -> dict:
    """One product record -> one catalog row. Every value comes from the record; nothing inferred."""
    iid = item_id_of(r["url"])
    fo = r.get("field_origin") or {}
    cat_raw = r.get("category")
    cat, cat_src, kw = "other", "null", None
    if cat_raw:
        cat, kw = rule_category(cat_raw)
        cat_src = "structured" if cat != "other" else "null"
    if cat == "other":
        cat, kw = rule_category(r.get("title"))
        cat_src = "title_rule" if cat != "other" else "null"
    color = norm_color(r.get("color"))
    gender = norm_gender(r.get("gender"))
    price = parse_price(r.get("price"))
    imgs = r.get("image_urls") or []
    return {
        "item_id": iid,
        "title": r.get("title"),
        "description": r.get("text"),
        "category": cat,
        "subcategory": cat_raw,                 # the page's own category string, verbatim (or null)
        "color": color,
        "season": None,
        "occasion": None,
        "gender": gender,
        "price": price,
        "currency": r.get("currency") if r.get("currency") else None,
        "outfit_ids": None,
        "image_path": f"images/{iid}.jpg",
        "source": r.get("source"),
        "attr_source": json.dumps({
            "category": cat_src, "color": "structured" if color else "null", "season": "null",
            "occasion": "null", "gender": "structured" if gender else "null",
            "price": "structured" if price is not None else "null"}),
        "image_url": imgs[0],
        "brand": r.get("brand"),
        "url": r.get("url"),
        "sku": r.get("sku"),
        "availability": r.get("availability"),
        "category_raw": cat_raw,
        "category_rule_match": kw,
        "color_raw": r.get("color"),
        "gender_raw": r.get("gender"),
        "field_origin": json.dumps(fo, ensure_ascii=False),
        "fetched_at": r.get("fetched_at"),
    }


# ------------------------------------------------------------------------------------------ images
def http_get(url: str, timeout: int = 20) -> bytes:
    last: Exception | None = None
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code in (403, 404, 410):
                raise
            last = e
        except (urllib.error.URLError, OSError) as e:
            last = e
        time.sleep(1.5 * (attempt + 1))
    raise OSError(f"failed: {url}: {last}")


def download_images(rows: list[dict], out: Path, fetch=http_get, workers: int = MAX_WORKERS) -> dict[str, str]:
    """item_id -> "ok" | "cached" | "failed". <= 8 workers overall, <= 2 in flight per host."""
    from PIL import Image
    (out / "images").mkdir(parents=True, exist_ok=True)
    host_sem: dict[str, threading.Semaphore] = defaultdict(lambda: threading.Semaphore(PER_HOST))
    lock = threading.Lock()

    def one(row: dict) -> tuple[str, str]:
        dst = out / row["image_path"]
        if dst.exists():
            return row["item_id"], "cached"
        host = (urlsplit(row["image_url"]).hostname or "").lower()
        with lock:
            sem = host_sem[host]
        try:
            with sem:
                data = fetch(row["image_url"])
            im = Image.open(io.BytesIO(data)).convert("RGB")
            im.thumbnail((MAX_SIDE, MAX_SIDE))
            im.save(dst, "JPEG", quality=90)
            return row["item_id"], "ok"
        except Exception:                           # any failure: skip the item, count it
            return row["item_id"], "failed"

    with ThreadPoolExecutor(max(1, min(workers, MAX_WORKERS))) as ex:
        return dict(ex.map(one, rows))


# ------------------------------------------------------------------------------------------- build
def build(records: list[str], out: Path, download: bool = False, max_items: int | None = None,
          apparel_only: bool = True, fetch=http_get, workers: int = MAX_WORKERS) -> tuple[pd.DataFrame, dict]:
    t0 = time.perf_counter()
    files = find_records(records)
    dropped: Counter = Counter()
    examples: dict[str, list] = defaultdict(list)
    in_by_source: Counter = Counter()
    seen: set[str] = set()
    rows: list[dict] = []

    def drop(reason: str, r: dict, **extra) -> None:
        dropped[reason] += 1
        if len(examples[reason]) < N_EXAMPLES:
            examples[reason].append(_example(r, **extra))

    n_in = 0
    for f in files:
        for r in json.loads(f.read_text(encoding="utf-8")):
            n_in += 1
            in_by_source[r.get("source") or "?"] += 1
            if r.get("page_type") != "product":
                drop("not_product", r, page_type=r.get("page_type"))
                continue
            if not r.get("image_urls"):
                drop("no_image", r)
                continue
            if not r.get("url") or not (r.get("title") or "").strip():
                drop("no_url_or_title", r)
                continue
            key = normalize_url(r["url"])
            if key in seen:
                drop("duplicate_url", r)
                continue
            seen.add(key)
            row = to_row(r)
            if apparel_only and row["category"] not in APPAREL:
                drop("not_apparel", r, category_raw=row["category_raw"])
                continue
            rows.append(row)

    if max_items is not None and len(rows) > max_items:
        for row in rows[max_items:]:
            drop("max_items", row)
        rows = rows[:max_items]

    out.mkdir(parents=True, exist_ok=True)
    img_status: dict[str, str] = {}
    if download:
        img_status = download_images(rows, out, fetch=fetch, workers=workers)
        keep = []
        for row in rows:
            if img_status.get(row["item_id"]) == "failed":
                drop("image_download_failed", row, image_url=row["image_url"])
            else:
                keep.append(row)
        rows = keep

    cols = ["item_id", "title", "description", "category", "subcategory", "color", "season", "occasion",
            "gender", "price", "currency", "outfit_ids", "image_path", "source", "attr_source", "image_url",
            "brand", "url", "sku", "availability", "category_raw", "category_rule_match", "color_raw",
            "gender_raw", "field_origin", "fetched_at"]
    items = pd.DataFrame(rows, columns=cols)
    items["price"] = items["price"].astype("float64")
    items.to_parquet(out / "items.parquet", index=False)

    cat_src = Counter(json.loads(s)["category"] for s in items["attr_source"])
    stats = {
        "inputs": [f.as_posix() for f in files],
        "n_records_in": n_in,
        "n_items": len(items),
        "records_in_by_source": dict(in_by_source),
        "items_by_source": items["source"].value_counts().to_dict(),
        "category": items["category"].value_counts().to_dict(),
        "category_origin": dict(cat_src),
        "dropped": dict(dropped),
        "dropped_examples": {k: v for k, v in examples.items()},
        "price_coverage": round(float(items["price"].notna().mean()), 4) if len(items) else 0.0,
        "currency": items["currency"].value_counts(dropna=False).rename(index=lambda x: x or "null").to_dict(),
        "attr_coverage": {k: round(float(items[k].notna().mean()), 4) if len(items) else 0.0
                          for k in ("color", "season", "occasion", "gender", "price", "brand")},
        "apparel_only": apparel_only,
        "images": dict(Counter(img_status.values())) if download else "not downloaded (use --download-images)",
        "seconds": round(time.perf_counter() - t0, 2),
    }
    (out / "stats.json").write_text(json.dumps(stats, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    srcs = ", ".join(f"`{k}` ({v})" for k, v in stats["items_by_source"].items()) or "none"
    (out / "README.md").write_text(
        "# Catalog: crawled Taiwanese shop products\n\n"
        "Built by `scripts/crawl_to_catalog.py` from `engine02.crawl` output (records.json):\n\n"
        + "".join(f"- `{f}`\n" for f in stats["inputs"]) +
        f"\nSources (items kept): {srcs}. {stats['n_items']} items from {n_in} records; "
        f"dropped: {json.dumps(stats['dropped'], ensure_ascii=False)} (see stats.json for examples).\n\n"
        "- **Licence**: third-party shop content (titles, descriptions, prices, images belong to the\n"
        "  shops / makers). **Non-commercial research demo only.** Images are NOT redistributed: they are\n"
        "  not committed, `image_url` points at the shop, `images/` is a local cache.\n"
        "- **From the page's structured data (JSON-LD / OpenGraph), verbatim**: title, description,\n"
        "  brand, price, currency, sku, availability; colour and gender only when stated (normalised to\n"
        "  the catalog vocabulary; the raw value is kept in `color_raw` / `gender_raw`).\n"
        "- **category**: the page's structured category if it maps to a coarse slot, else explicit\n"
        "  keyword rules on the title (`attr_source.category = \"title_rule\"`, matched keyword in\n"
        "  `category_rule_match`); no match -> `other`, dropped unless `--no-apparel-only`.\n"
        "- **season / occasion**: null here; `scripts/vlm_fill_catalog.py` fills them with provenance --\n"
        "  never use model-filled fields as evaluation ground truth.\n", encoding="utf-8")
    return items, stats


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--records", action="append", required=True,
                    help="records.json, or a directory containing one (or several, searched recursively)")
    ap.add_argument("--out", default="data/catalog/crawl_tw")
    ap.add_argument("--download-images", action="store_true")
    ap.add_argument("--max-items", type=int, default=None)
    ap.add_argument("--apparel-only", action=argparse.BooleanOptionalAction, default=True,
                    help="drop items whose category is 'other' (default on)")
    ap.add_argument("--workers", type=int, default=MAX_WORKERS, help=f"image workers, capped at {MAX_WORKERS}")
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # zh titles on a cp950 console
    except (AttributeError, ValueError):
        pass
    items, stats = build(a.records, ROOT / a.out, download=a.download_images, max_items=a.max_items,
                         apparel_only=a.apparel_only, workers=a.workers)
    print(json.dumps({k: stats[k] for k in ("n_records_in", "n_items", "items_by_source", "category",
                                             "category_origin", "dropped", "price_coverage", "images")},
                     ensure_ascii=False))
    for reason, exs in stats["dropped_examples"].items():
        for e in exs:
            print(f"  dropped[{reason}] {e.get('source')}: {e.get('title')}")


if __name__ == "__main__":
    main()
