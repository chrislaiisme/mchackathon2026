"""Build a *priced* ENGINE 02 catalog from Amazon Reviews 2023 item metadata (McAuley-Lab).

The public fashion datasets we already ship (Marqo/KAGL, Marqo/polyvore) have no price
column at all, so `engine02.constraints` budget filtering and the `budget:x1.2` /
`budget:drop` rungs of the relaxation ladder are dead code. This script produces a
catalog in the *same* layout as `scripts/prepare_catalog.py` but with a real
`price` / `currency`, so the budget slot can actually be exercised.

Source
------
https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023
  raw/meta_categories/meta_Clothing_Shoes_and_Jewelry.jsonl   (17.96 GB, 7.2M items)
  raw/meta_categories/meta_Amazon_Fashion.jsonl               ( 1.42 GB, 826K items)

Public repo (`gated: false`), no token needed. The .jsonl is read as an HTTP *stream*
and the connection is closed as soon as `--limit` rows have been accepted, so a
5,000-item smoke build reads only a few tens of MB of the 18 GB file.

Images are **not** in the dataset: metadata carries Amazon CDN URLs. We rewrite them to
the CDN's own resize form (`._AC_UL400_.jpg`, ~22 KB instead of ~300 KB) and store a
384 px JPEG locally, matching prepare_catalog.py.

Usage
-----
    # print exactly what would be downloaded, write nothing
    .venv/Scripts/python.exe scripts/prepare_catalog_priced.py --name amz_clothing --dry-run

    # smoke run
    .venv/Scripts/python.exe scripts/prepare_catalog_priced.py --name amz_smoke --limit 50

    # real demo catalog
    .venv/Scripts/python.exe scripts/prepare_catalog_priced.py --name amz_clothing --limit 8000

    # reuse a previously downloaded .jsonl instead of streaming
    .venv/Scripts/python.exe scripts/prepare_catalog_priced.py --name amz_clothing \
        --local-jsonl D:/dl/meta_Clothing_Shoes_and_Jewelry.jsonl --limit 8000

    # mapping unit tests, no network, no writes
    .venv/Scripts/python.exe scripts/prepare_catalog_priced.py --self-test

Output (under data/catalog/<name>/ only):
    items.parquet  images/*.jpg  stats.json  README.md

Schema is byte-identical to prepare_catalog.py:
    item_id, title, description, category, subcategory, color, season, occasion, gender,
    price, currency, outfit_ids, image_path, source, attr_source

Values are never invented. Amazon metadata has no season and no occasion, so those two
columns are always null; colour is only written when `details.Color` exists.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG_ROOT = ROOT / "data" / "catalog"

COARSE = ("top", "bottom", "outerwear", "dress", "shoes", "bag", "accessory", "jewelry", "other")
ATTRS = ("color", "season", "occasion", "gender", "price")
COLUMNS = ["item_id", "title", "description", "category", "subcategory", "color", "season",
           "occasion", "gender", "price", "currency", "outfit_ids", "image_path", "source",
           "attr_source"]
MAX_SIDE = 384          # same as prepare_catalog.py
CDN_PX = 400            # CDN-side resize before download (keeps >= MAX_SIDE)
CURRENCY = "USD"        # dataset card: "Price in US dollars (at time of crawling)"
UA = "mchackathon2026-engine02-catalog-builder/1.0 (research prototype)"

HF_REPO = "McAuley-Lab/Amazon-Reviews-2023"
SOURCES = {
    "clothing": dict(
        path="raw/meta_categories/meta_Clothing_Shoes_and_Jewelry.jsonl",
        approx_bytes=17_960_000_000, approx_items=7_200_000,
        note="Clothing, Shoes & Jewelry — hierarchical `categories` on ~100% of rows",
    ),
    "fashion": dict(
        path="raw/meta_categories/meta_Amazon_Fashion.jsonl",
        approx_bytes=1_420_000_000, approx_items=825_900,
        note="Amazon Fashion — smaller, but `categories` is empty and price coverage is ~14%",
    ),
}
LICENSE_NOTE = (
    "No licence is declared on the HF dataset card or in the repo tags (checked via the HF API: "
    "tags carry no `license:` entry). The metadata is a crawl of amazon.com; product images stay "
    "on Amazon's CDN and remain Amazon's / the sellers' copyright. Treat as research-only and "
    "clear redistribution with legal before shipping."
)

# --------------------------------------------------------------------------------------
# category mapping: Amazon hierarchical `categories` -> our coarse slot
#   e.g. ['Clothing, Shoes & Jewelry', 'Women', 'Shoes', 'Sandals', 'Flats'] -> shoes
# Rules are matched against every path segment from the LEAF backwards, so the most
# specific segment wins. BLOCK is checked first: multi-piece / non-garment buckets that
# do not occupy an outfit slot go to `other`, matching prepare_catalog.py's KAGL rules
# (Swimwear, Innerwear, Kurta Sets, Night suits, personal care -> other).
# --------------------------------------------------------------------------------------
BLOCK = (
    "costume", "lingerie", "sleep & lounge", "underwear", "intimate", "bras", "panties",
    "shapewear", "swim", "cover ups", "maternity", "novelty", "uniforms", "pet supplies",
    "baby", "traditional & cultural", "religious", "suits & sport coats", " sets",
    "sleepwear", "robes", "thermal", "beauty", "personal care", "luggage & travel gear",
)
RULES: tuple[tuple[str, str], ...] = (
    # --- shoes -------------------------------------------------------------------------
    ("sneaker", "shoes"), ("boots", "shoes"), ("sandals", "shoes"), ("loafers", "shoes"),
    ("slip-ons", "shoes"), ("flats", "shoes"), ("pumps", "shoes"), ("oxfords", "shoes"),
    ("heels", "shoes"), ("mules & clogs", "shoes"), ("slippers", "shoes"),
    ("shoes", "shoes"), ("footwear", "shoes"),
    # --- bags --------------------------------------------------------------------------
    ("crossbody", "bag"), ("shoulder bags", "bag"), ("totes", "bag"), ("satchels", "bag"),
    ("hobo bags", "bag"), ("clutches", "bag"), ("evening bags", "bag"), ("backpacks", "bag"),
    ("wristlets", "bag"), ("handbags", "bag"), ("bags", "bag"),
    # --- jewelry -----------------------------------------------------------------------
    ("rings", "jewelry"), ("necklaces", "jewelry"), ("earrings", "jewelry"),
    ("bracelets", "jewelry"), ("anklets", "jewelry"), ("brooches", "jewelry"),
    ("pendants", "jewelry"), ("body jewelry", "jewelry"), ("jewelry", "jewelry"),
    # --- accessories (incl. wallets/watches, as in the KAGL table) ----------------------
    ("wallets", "accessory"), ("watches", "accessory"), ("sunglasses", "accessory"),
    ("eyewear", "accessory"), ("hats & caps", "accessory"), ("scarves", "accessory"),
    ("wraps", "accessory"), ("belts", "accessory"), ("gloves", "accessory"),
    ("mittens", "accessory"), ("socks", "accessory"), ("hosiery", "accessory"),
    ("tights", "accessory"), ("ties", "accessory"), ("cummerbunds", "accessory"),
    ("pocket squares", "accessory"), ("hair accessories", "accessory"),
    ("cold weather", "accessory"), ("accessories", "accessory"),
    # --- dresses / one-pieces -----------------------------------------------------------
    ("dresses", "dress"), ("rompers", "dress"), ("jumpsuits", "dress"),
    # --- outerwear (before "vests"/"jackets" can be eaten by top) ------------------------
    ("coats", "outerwear"), ("jackets", "outerwear"), ("blazers", "outerwear"),
    ("parkas", "outerwear"), ("trench", "outerwear"), ("outerwear", "outerwear"),
    ("vests", "outerwear"),
    # --- bottoms ------------------------------------------------------------------------
    ("jeans", "bottom"), ("pants", "bottom"), ("shorts", "bottom"), ("skirts", "bottom"),
    ("leggings", "bottom"), ("capris", "bottom"), ("trousers", "bottom"),
    ("chinos", "bottom"), ("bottoms", "bottom"),
    # --- tops ---------------------------------------------------------------------------
    ("t-shirts", "top"), ("tees", "top"), ("tanks", "top"), ("camis", "top"),
    ("blouses", "top"), ("button-down", "top"), ("tunics", "top"), ("polos", "top"),
    ("henleys", "top"), ("sweaters", "top"), ("cardigans", "top"), ("pullovers", "top"),
    ("sweatshirts", "top"), ("hoodies", "top"), ("knits", "top"), ("shirts", "top"),
    ("tops", "top"),
)
GENDER = {
    "women": "Women", "womens": "Women", "men": "Men", "mens": "Men",
    "girls": "Girls", "boys": "Boys",
    "unisex": "Unisex", "unisex-adult": "Unisex", "unisex-child": "Unisex",
    "unisex-baby": "Unisex", "unisex adult": "Unisex",
}


def coarse_category(categories) -> tuple[str | None, str | None]:
    """(coarse, subcategory) from the Amazon hierarchical category path.

    Returns (None, None) when the path is empty — the caller then drops the row rather
    than guessing. Anything recognisably non-apparel or multi-piece becomes 'other'.
    """
    segs = [str(s).strip() for s in (categories or []) if str(s).strip()]
    if not segs:
        return None, None
    leaf = segs[-1]
    # segs[0] is the store root ("Clothing, Shoes & Jewelry"), which contains the words
    # "Shoes" and "Jewelry" and would match every single item — never match against it.
    low = [s.lower() for s in (segs[1:] if len(segs) > 1 else segs)]
    if any(b in s for s in low for b in BLOCK):
        return "other", leaf
    for seg in reversed(low):
        for key, coarse in RULES:
            if key in seg:
                return coarse, leaf
    return "other", leaf


def gender_of(categories, details) -> str | None:
    for seg in (str(s).strip().lower() for s in (categories or [])):
        if seg in GENDER:
            return GENDER[seg]
    dep = (details or {}).get("Department")
    if dep:
        return GENDER.get(str(dep).strip().lower())
    return None


def _s(v):
    if v is None:
        return None
    v = str(v).strip()
    return v or None


def _price(v) -> float | None:
    """Card declares float, but some configs ship it as a string ('None', '$12.99')."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        p = float(v)
    else:
        m = re.search(r"\d+(?:\.\d+)?", str(v).replace(",", ""))
        if not m:
            return None
        p = float(m.group())
    return p if 0 < p < 100_000 else None


IMG_RE = re.compile(r"^(https://m\.media-amazon\.com/images/I/[A-Za-z0-9@+%_-]+?)(?:\.[^/]*)?\.jpg$")


def cdn_resized(url: str, px: int = CDN_PX) -> str | None:
    """Rewrite an Amazon image URL to the CDN's own max-longest-side form.

    'https://m.media-amazon.com/images/I/81X._AC_UL1500_.jpg' -> '..._AC_UL400_.jpg'
    Returns None for anything that is not an Amazon image URL (we never fetch elsewhere).
    """
    m = IMG_RE.match((url or "").strip())
    return f"{m.group(1)}._AC_UL{px}_.jpg" if m else None


def pick_image(images) -> str | None:
    if not images:
        return None
    entries = list(images)
    main = [e for e in entries if isinstance(e, dict) and e.get("variant") == "MAIN"]
    for e in (main + entries):
        if not isinstance(e, dict):
            continue
        for key in ("hi_res", "large"):   # never 'thumb': 38x50 is useless for SigLIP
            u = cdn_resized(e.get(key) or "")
            if u:
                return u
    return None


def adapt(row: dict) -> dict | None:
    """Amazon metadata row -> unified record (without image_path). None = reject."""
    price = _price(row.get("price"))
    if price is None:
        return None
    img = pick_image(row.get("images"))
    if not img:
        return None
    asin = _s(row.get("parent_asin"))
    title = _s(row.get("title"))
    if not asin or not title:
        return None
    cat, sub = coarse_category(row.get("categories"))
    if cat is None:
        return None
    details = row.get("details")
    if isinstance(details, str):
        try:
            details = json.loads(details)
        except Exception:
            details = {}
    details = details if isinstance(details, dict) else {}
    desc = [d for d in (row.get("description") or []) if _s(d)]
    if not desc:
        desc = [d for d in (row.get("features") or []) if _s(d)][:5]
    color = _s(details.get("Color") or details.get("Colour"))
    return dict(
        item_id=asin,
        title=title,
        description=(" ".join(map(str, desc)).strip() or None),
        category=cat,
        subcategory=sub,
        color=color,
        season=None,        # not in this source
        occasion=None,      # not in this source
        gender=gender_of(row.get("categories"), details),
        price=price,
        currency=CURRENCY,
        outfit_ids=None,    # not in this source
        _image_url=img,
    )


# --------------------------------------------------------------------------------------
# io
# --------------------------------------------------------------------------------------
def out_dir_for(name: str) -> Path:
    """Refuse to write anywhere except data/catalog/<name>/."""
    if not re.fullmatch(r"[A-Za-z0-9._-]+", name or ""):
        raise SystemExit(f"--name must be a plain directory name, got {name!r}")
    out = (CATALOG_ROOT / name).resolve()
    if out.parent != CATALOG_ROOT.resolve():
        raise SystemExit(f"refusing to write outside {CATALOG_ROOT}")
    return out


def hf_url(source: str) -> str:
    return f"https://huggingface.co/datasets/{HF_REPO}/resolve/main/{SOURCES[source]['path']}"


def _auth_headers() -> dict:
    """Token from the environment only — never a literal, never written to disk."""
    tok = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    return {"Authorization": f"Bearer {tok}"} if tok else {}


def _explain_http_error(resp, url: str) -> SystemExit:
    if resp.status_code in (401, 403):
        return SystemExit(
            f"HTTP {resp.status_code} for {url}\n"
            f"  {HF_REPO} is public today, so this normally means the repo became gated or your\n"
            "  token is wrong. Accept the terms on the dataset page, then export a token:\n"
            "      $env:HF_TOKEN = '<your token>'      # PowerShell\n"
            "      export HF_TOKEN=<your token>        # bash\n"
            "  This script reads HF_TOKEN / HUGGING_FACE_HUB_TOKEN from the environment only."
        )
    return SystemExit(f"HTTP {resp.status_code} for {url}")


def iter_rows(source: str, local: str | None):
    """Yield parsed json rows, streaming over HTTP and closing early when the caller stops."""
    if local:
        p = Path(local)
        if not p.exists():
            raise SystemExit(f"--local-jsonl not found: {p}")
        with p.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    yield json.loads(line)
                except Exception:
                    continue
        return
    import requests

    url = hf_url(source)
    with requests.get(url, stream=True, timeout=60,
                      headers={"User-Agent": UA, **_auth_headers()}) as r:
        if r.status_code != 200:
            raise _explain_http_error(r, url)
        for raw in r.iter_lines(decode_unicode=False):
            if not raw:
                continue
            try:
                yield json.loads(raw.decode("utf-8", "replace"))
            except Exception:
                continue


def fetch_image(url: str, dst: Path) -> None:
    import requests
    from PIL import Image

    r = requests.get(url, timeout=30, headers={"User-Agent": UA})
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}")
    img = Image.open(io.BytesIO(r.content))
    img.load()
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    img.save(dst, "JPEG", quality=90, optimize=True)


def safe_name(item_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", item_id)


# --------------------------------------------------------------------------------------
def dry_run(args) -> None:
    spec = SOURCES[args.source]
    out = out_dir_for(args.name)
    n = args.limit or spec["approx_items"]
    print("=" * 78)
    print("DRY RUN — nothing is downloaded and nothing is written.")
    print("=" * 78)
    print("\n1. METADATA (streamed, connection closed as soon as --limit is reached)")
    if args.local_jsonl:
        p = Path(args.local_jsonl)
        print(f"   local file   : {p}")
        print(f"   exists       : {p.exists()}"
              + (f"  ({p.stat().st_size / 1e9:.2f} GB)" if p.exists() else ""))
    else:
        print(f"   GET {hf_url(args.source)}")
        print(f"   full file    : {spec['approx_bytes'] / 1e9:.2f} GB, ~{spec['approx_items']:,} items")
        print(f"   auth         : {'HF_TOKEN found in env' if _auth_headers() else 'none (public repo)'}")
        # rows that pass the filters are a fraction of rows read; ~0.9 KB/row after gzip-less jsonl
        est = min(spec["approx_bytes"], int(n / max(args.accept_rate, 0.01) * 2200))
        print(f"   will read    : ~{est / 1e6:.0f} MB before stopping"
              f" (assuming ~{args.accept_rate:.0%} of rows pass price+image+category filters)")
    print("\n2. IMAGES (one per item, from Amazon's CDN, resized by the CDN before transfer)")
    print(f"   GET https://m.media-amazon.com/images/I/<id>._AC_UL{CDN_PX}_.jpg")
    print(f"   count        : up to {n:,}")
    print(f"   est. transfer: ~{n * 23_000 / 1e6:.0f} MB   (~23 KB/image measured at {CDN_PX} px)")
    print(f"   stored as    : {MAX_SIDE} px max-side JPEG q90, ~{n * 30_000 / 1e6:.0f} MB on disk")
    print(f"   workers      : {args.workers}")
    print("\n3. OUTPUT (nothing outside this directory is touched)")
    print(f"   {out}{os.sep}items.parquet")
    print(f"   {out}{os.sep}images{os.sep}*.jpg")
    print(f"   {out}{os.sep}stats.json, README.md")
    print("\n4. LICENCE")
    for line in LICENSE_NOTE.split(". "):
        print(f"   {line.strip()}")
    print("\n5. COLUMNS THAT WILL BE NULL (this source has no such field)")
    print("   season, occasion, outfit_ids  — always null")
    print("   color                          — only when details.Color exists (~5% of rows)")
    print("\nRe-run without --dry-run to execute.")


def build(args) -> None:
    import pandas as pd
    import pyarrow as pa
    import pyarrow.parquet  # noqa: F401

    out = out_dir_for(args.name)
    (out / "images").mkdir(parents=True, exist_ok=True)
    target = args.limit or 0
    # over-collect so image failures do not leave us short of --limit
    want = int(target * 1.15) + 10 if target else 0

    t0 = time.time()
    recs, seen, scanned = [], set(), 0
    for row in iter_rows(args.source, args.local_jsonl):
        scanned += 1
        rec = adapt(row)
        if rec is None or rec["item_id"] in seen:
            continue
        seen.add(rec["item_id"])
        recs.append(rec)
        if want and len(recs) >= want:
            break
        if len(recs) % 500 == 0:
            print(f"  {len(recs)} candidates from {scanned} rows  {time.time() - t0:.0f}s", flush=True)
    t_meta = time.time() - t0
    print(f"metadata: {len(recs)} candidates from {scanned} rows in {t_meta:.0f}s", flush=True)

    def grab(rec):
        rel = f"images/{safe_name(rec['item_id'])}.jpg"
        try:
            fetch_image(rec["_image_url"], out / rel)
        except Exception as e:
            return rec, None, str(e)
        return rec, rel, None

    kept, failed = [], 0
    t1 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for rec, rel, err in pool.map(grab, recs):
            if rel is None:
                failed += 1
                print(f"  skip {rec['item_id']}: {err}", file=sys.stderr)
                continue
            rec = {k: v for k, v in rec.items() if k != "_image_url"}
            rec["image_path"] = rel
            rec["source"] = f"{HF_REPO}:{SOURCES[args.source]['path']}"
            rec["attr_source"] = json.dumps(
                {a: ("dataset" if rec[a] is not None else "null") for a in ATTRS})
            kept.append(rec)
            if target and len(kept) >= target:
                break
    print(f"images: {len(kept)} kept, {failed} failed in {time.time() - t1:.0f}s", flush=True)

    df = pd.DataFrame.from_records(kept, columns=COLUMNS)
    df["price"] = df["price"].astype("float64")
    schema = pa.schema([(c, pa.float64() if c == "price"
                         else pa.list_(pa.string()) if c == "outfit_ids"
                         else pa.string()) for c in COLUMNS])
    pa.parquet.write_table(pa.Table.from_pandas(df, schema=schema, preserve_index=False),
                           out / "items.parquet")

    size_mb = sum(p.stat().st_size for p in out.rglob("*") if p.is_file()) / 1e6
    prices = df["price"].dropna()
    stats = dict(
        source=f"{HF_REPO}/{SOURCES[args.source]['path']}", license=LICENSE_NOTE,
        n_items=len(df), rows_scanned=scanned, failed_images=failed, limit=args.limit,
        seconds=round(time.time() - t0, 1), disk_mb=round(size_mb, 1),
        category=df["category"].value_counts(dropna=False).to_dict(),
        gender=df["gender"].value_counts(dropna=False).to_dict(),
        color=df["color"].value_counts(dropna=False).head(25).to_dict(),
        price_summary=({
            "currency": CURRENCY, "min": float(prices.min()), "max": float(prices.max()),
            "median": float(prices.median()),
            "quantiles": {q: round(float(prices.quantile(q)), 2)
                          for q in (0.1, 0.25, 0.5, 0.75, 0.9)},
        } if len(prices) else {}),
        attr_coverage={a: (float(df[a].notna().mean()) if len(df) else 0.0) for a in ATTRS},
    )
    (out / "stats.json").write_text(json.dumps(stats, indent=1, ensure_ascii=False), encoding="utf-8")
    (out / "README.md").write_text(
        f"""# Catalog: Amazon Reviews 2023 ({args.source}) — PRICED

Generated by `scripts/prepare_catalog_priced.py` (HTTP-streamed metadata; images fetched from
Amazon's CDN at {CDN_PX} px and stored as {MAX_SIDE} px JPEG).

- Source: https://huggingface.co/datasets/{HF_REPO} — `{SOURCES[args.source]['path']}`
- Licence: {LICENSE_NOTE}
- Items: {len(df)} (scanned {scanned} rows, {failed} image failures); disk {size_mb:.1f} MB
- Attribute coverage: {json.dumps(stats['attr_coverage'])}
- Price: {json.dumps(stats['price_summary'], ensure_ascii=False)}
- `season`, `occasion`, `outfit_ids` are ALWAYS null — the source has no such field.
  `color` only when `details.Color` is present. Nothing is invented; see `attr_source`.
""", encoding="utf-8")
    print(json.dumps(stats, indent=1, ensure_ascii=False))


# --------------------------------------------------------------------------------------
def self_test() -> int:
    """Mapping unit tests on hand-built rows. No network, no writes."""
    fails = []

    def eq(got, want, what):
        if got != want:
            fails.append(f"{what}: got {got!r}, want {want!r}")

    C = "Clothing, Shoes & Jewelry"
    eq(coarse_category([C, "Women", "Shoes", "Sandals", "Flats"]), ("shoes", "Flats"), "shoes leaf")
    eq(coarse_category([C, "Women", "Handbags & Wallets", "Crossbody Bags"]),
       ("bag", "Crossbody Bags"), "bag leaf")
    eq(coarse_category([C, "Women", "Handbags & Wallets", "Wallets"])[0], "accessory", "wallets")
    eq(coarse_category([C, "Women", "Jewelry", "Rings"]), ("jewelry", "Rings"), "jewelry")
    eq(coarse_category([C, "Men", "Clothing", "Jeans"])[0], "bottom", "jeans")
    eq(coarse_category([C, "Women", "Clothing", "Dresses", "Casual"])[0], "dress", "dress")
    eq(coarse_category([C, "Men", "Clothing", "Jackets & Coats", "Down Jackets"])[0],
       "outerwear", "outerwear beats nothing")
    eq(coarse_category([C, "Men", "Clothing", "Shirts", "Dress Shirts"])[0], "top", "top")
    eq(coarse_category([C, "Women", "Clothing", "Swimsuits & Cover Ups", "Bikinis"])[0],
       "other", "swim -> other (BLOCK wins over 'tops')")
    eq(coarse_category([C, "Novelty & More", "Clothing", "Novelty", "Women", "Skirts"])[0],
       "other", "novelty -> other")
    eq(coarse_category([C, "Men", "Accessories", "Watches"])[0], "accessory", "watch")
    eq(coarse_category([]), (None, None), "empty path rejected")
    eq(coarse_category([C, "Women", "Handmade Widgets"])[0], "other", "unknown -> other")

    eq(gender_of([C, "Women", "Shoes"], {}), "Women", "gender from path")
    eq(gender_of([C], {"Department": "mens"}), "Men", "gender from details")
    eq(gender_of([C], {"Department": "unisex-adult"}), "Unisex", "unisex")
    eq(gender_of([C], {}), None, "gender unknown stays null")

    eq(_price(31.99), 31.99, "float price")
    eq(_price("$12.99"), 12.99, "string price")
    eq(_price("None"), None, "None string")
    eq(_price(None), None, "null price")
    eq(_price(0), None, "zero rejected")
    eq(_price("1,299.00"), 1299.0, "thousands separator")

    eq(cdn_resized("https://m.media-amazon.com/images/I/81XlFXImFrS._AC_UL1500_.jpg"),
       f"https://m.media-amazon.com/images/I/81XlFXImFrS._AC_UL{CDN_PX}_.jpg", "cdn resize")
    eq(cdn_resized("https://m.media-amazon.com/images/I/81XlFXImFrS.jpg"),
       f"https://m.media-amazon.com/images/I/81XlFXImFrS._AC_UL{CDN_PX}_.jpg", "cdn bare url")
    eq(cdn_resized("https://evil.example.com/x.jpg"), None, "non-amazon host rejected")
    eq(cdn_resized(""), None, "empty url")
    eq(pick_image([{"variant": "PT01", "large": "https://m.media-amazon.com/images/I/aa._AC_.jpg"},
                   {"variant": "MAIN", "hi_res": "https://m.media-amazon.com/images/I/bb._AC_.jpg"}]),
       f"https://m.media-amazon.com/images/I/bb._AC_UL{CDN_PX}_.jpg", "MAIN preferred")
    eq(pick_image([{"variant": "MAIN", "thumb": "https://m.media-amazon.com/images/I/cc._SR38,50_.jpg"}]),
       None, "thumb-only rejected")

    good = dict(parent_asin="B001", title="SheIn Women's Plaid Mini Skirt",
                price=15.99, categories=[C, "Women", "Clothing", "Skirts"],
                images=[{"variant": "MAIN", "hi_res": "https://m.media-amazon.com/images/I/dd._AC_UL1500_.jpg"}],
                description=["A plaid mini skirt."], features=["stretch"],
                details={"Department": "womens", "Color": "Navy"})
    r = adapt(good)
    eq(r["category"], "bottom", "adapt category")
    eq(r["subcategory"], "Skirts", "adapt subcategory")
    eq(r["price"], 15.99, "adapt price")
    eq(r["currency"], "USD", "adapt currency")
    eq(r["color"], "Navy", "adapt colour")
    eq(r["gender"], "Women", "adapt gender")
    eq(r["season"], None, "season stays null")
    eq(r["occasion"], None, "occasion stays null")
    eq(r["outfit_ids"], None, "outfit_ids stays null")
    eq(r["description"], "A plaid mini skirt.", "adapt description")
    eq(set(r) - {"_image_url"}, set(COLUMNS) - {"image_path", "source", "attr_source"},
       "adapt emits exactly the catalog columns")
    eq(adapt({**good, "price": None}), None, "no price -> rejected")
    eq(adapt({**good, "images": []}), None, "no image -> rejected")
    eq(adapt({**good, "categories": []}), None, "no category -> rejected")
    eq(adapt({**good, "title": ""}), None, "no title -> rejected")
    eq(adapt({**good, "description": [], "features": ["a", "b"]})["description"], "a b",
       "features fall back into description")
    eq(adapt({**good, "details": '{"Color": "Red"}'})["color"], "Red", "details as json string")
    eq(adapt({**good, "details": {}})["color"], None, "no colour stays null")

    # the parquet column list must stay identical to prepare_catalog.py
    src = (ROOT / "scripts" / "prepare_catalog.py").read_text(encoding="utf-8")
    m = re.search(r'cols = \[(.*?)\]\n', src, re.S)
    if m:
        eq(COLUMNS, [c.strip().strip('"') for c in m.group(1).replace("\n", "").split(",") if c.strip()],
           "COLUMNS matches prepare_catalog.py")

    for f in fails:
        print("FAIL", f)
    print(f"\nself-test: {'FAILED' if fails else 'OK'} ({len(fails)} failures)")
    return 1 if fails else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", default="amz_clothing",
                    help="output goes to data/catalog/<name>/ and nowhere else")
    ap.add_argument("--source", default="clothing", choices=sorted(SOURCES))
    ap.add_argument("--limit", type=int, default=5000, help="max items (0 = all; you do not want 0)")
    ap.add_argument("--local-jsonl", default=None,
                    help="use an already-downloaded meta_*.jsonl instead of streaming")
    ap.add_argument("--workers", type=int, default=4, help="parallel image downloads")
    ap.add_argument("--accept-rate", type=float, default=0.55,
                    help="dry-run only: assumed share of rows passing the filters "
                         "(0.56 measured on the first 533 rows of the clothing shard)")
    ap.add_argument("--dry-run", action="store_true", help="print what would be downloaded, then exit")
    ap.add_argument("--self-test", action="store_true", help="run the mapping unit tests and exit")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()
    if args.dry_run:
        dry_run(args)
        return 0
    try:
        import requests  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError as e:
        raise SystemExit(f"missing dependency: {e}. Install with `pip install requests pillow`.")
    build(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
