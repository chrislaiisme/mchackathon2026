"""Build a unified ENGINE 02 product catalog from a public Hugging Face fashion dataset.

Usage (from repo root):
    .venv/Scripts/python.exe scripts/prepare_catalog.py --source Marqo/KAGL --limit 5000 \
        --out data/catalog/kagl --shuffle-buffer 256 --seed 0
    .venv/Scripts/python.exe scripts/prepare_catalog.py --source Marqo/polyvore --limit 3000 \
        --out data/catalog/polyvore
    # full-dataset outfit co-occurrence for polyvore (reads only text columns, ~10 min):
    .venv/Scripts/python.exe scripts/prepare_catalog.py --source Marqo/polyvore --limit 3000 \
        --out data/catalog/polyvore --full-cooccurrence

Streams the dataset (nothing is fully downloaded), writes JPEGs (max side 384 px) under
<out>/images/ and <out>/items.parquet with the unified schema:

    item_id:str, title:str, description:str|null, category:str|null (coarse),
    subcategory:str|null (source fine category), color, season, occasion, gender: str|null,
    price:float|null, currency:str|null, outfit_ids:list[str]|null,
    image_path:str (relative to out dir), source:str,
    attr_source: JSON string {color|season|occasion|gender|price: 'dataset'|'null'}

Values are never invented: anything the source does not provide is null.

Coarse categories: top / bottom / outerwear / dress / shoes / bag / accessory / jewelry / other.
The mappings are explicit tables below (KAGL_*, POLYVORE_*); unmapped fine categories -> other.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import time
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

import pandas as pd
from PIL import Image

COARSE = ("top", "bottom", "outerwear", "dress", "shoes", "bag", "accessory", "jewelry", "other")
ATTRS = ("color", "season", "occasion", "gender", "price")
MAX_SIDE = 384

# --------------------------------------------------------------------------------------
# KAGL (Kaggle "Fashion Product Images", paramaggarwal; Myntra catalog)
#   category1 = masterCategory, category2 = subCategory, category3 = articleType
# Rule: category3 override table first, then category2 table, then category1 table, else other.
# --------------------------------------------------------------------------------------
KAGL_CAT3 = {
    # outerwear pulled out of Topwear
    "Jackets": "outerwear", "Blazers": "outerwear", "Rain Jacket": "outerwear",
    "Nehru Jackets": "outerwear", "Waistcoat": "outerwear", "Shrug": "outerwear",
    # dresses / one-pieces
    "Dresses": "dress", "Jumpsuit": "dress",
    # multi-piece sets & ethnic sets are not a single garment slot
    "Lehenga Choli": "other", "Kurta Sets": "other", "Tracksuits": "other",
    "Night suits": "other", "Nightdress": "other", "Sarees": "other", "Swimwear": "other",
    "Baby Dolls": "other", "Robe": "other", "Bath Robe": "other",
    # accessories that live under apparel/other buckets
    "Dupatta": "accessory", "Suspenders": "accessory", "Socks": "accessory",
    "Stockings": "accessory", "Wallets": "accessory",
    "Watches": "accessory", "Mobile Pouch": "bag", "Laptop Bag": "bag",
    "Rucksacks": "bag", "Duffel Bag": "bag", "Messenger Bag": "bag", "Waist Pouch": "bag",
    "Trolley Bag": "bag", "Tablet Sleeve": "bag", "Clutches": "bag", "Handbags": "bag",
    "Backpacks": "bag", "Travel Accessory": "accessory", "Cufflinks": "jewelry",
    "Shoe Accessories": "accessory", "Shoe Laces": "accessory",
    "Accessory Gift Set": "other", "Free Gifts": "other", "Water Bottle": "other",
}
KAGL_CAT2 = {
    "Topwear": "top", "Bottomwear": "bottom", "Dress": "dress", "Saree": "other",
    "Apparel Set": "other", "Innerwear": "other", "Loungewear and Nightwear": "other",
    "Socks": "accessory",
    "Shoes": "shoes", "Sandal": "shoes", "Flip Flops": "shoes",
    "Bags": "bag",
    "Jewellery": "jewelry", "Cufflinks": "jewelry",
    "Watches": "accessory", "Wallets": "accessory", "Eyewear": "accessory",
    "Belts": "accessory", "Headwear": "accessory", "Scarves": "accessory",
    "Stoles": "accessory", "Mufflers": "accessory", "Gloves": "accessory", "Ties": "accessory",
    "Accessories": "accessory", "Umbrellas": "accessory", "Shoe Accessories": "accessory",
    "Sports Accessories": "accessory",
}
KAGL_CAT1 = {  # fallback by master category
    "Footwear": "shoes", "Personal Care": "other", "Free Items": "other",
    "Sporting Goods": "other", "Home": "other",
}


def kagl_coarse(c1, c2, c3):
    for table, key in ((KAGL_CAT3, c3), (KAGL_CAT2, c2), (KAGL_CAT1, c1)):
        if key in table:
            return table[key]
    return "other"


# --------------------------------------------------------------------------------------
# Polyvore (Marqo/polyvore = Maryland Polyvore, Han et al. 2017). Fine category strings
# are Polyvore site categories; "Men's X" is normalised to "X" for lookup only.
# Everything not listed (beauty, home decor, furniture, generic "Clothing", kids, ...)
# maps to other.
# --------------------------------------------------------------------------------------
POLYVORE_COARSE = {
    "top": [
        "Tops", "Blouses", "T-Shirts", "Tank Tops", "Sweaters", "Cardigans", "Sweatshirts",
        "Hoodies", "Tunics", "Camisoles", "Polos", "Shirts", "Casual Shirts", "Dress Shirts",
        "Activewear Tops", "Activewear Tank Tops",
    ],
    "bottom": [
        "Pants", "Shorts", "Leggings", "Jeans", "Skinny Jeans", "Boyfriend Jeans",
        "Straight Leg Jeans", "Flared Jeans", "Bootcut Jeans", "Wide Leg Jeans",
        "Capri & Cropped Pants", "Skirts", "Mini Skirts", "Knee Length Skirts", "Long Skirts",
        "Activewear Pants", "Activewear Shorts", "Activewear Skirts", "Casual Pants",
        "Dress Pants",
    ],
    "outerwear": [
        "Jackets", "Coats", "Blazers", "Outerwear", "Vests", "Sportcoats & Blazers",
        "Activewear Jackets",
    ],
    "dress": [
        "Dresses", "Day Dresses", "Cocktail Dresses", "Gowns", "Wedding Dresses", "Rompers",
        "Jumpsuits",
    ],
    "shoes": [
        "Shoes", "Sandals", "Pumps", "Ankle Booties", "Boots", "Knee High Boots",
        "Over-The-Knee Boots", "Mid Calf Boots", "Sneakers", "Athletic Shoes", "Flats",
        "Loafers & Moccasins", "Oxfords", "Slippers", "Flip Flops", "Clogs", "Work Boots",
        "Dress Shoes",
    ],
    "bag": [
        "Bags", "Shoulder Bags", "Clutches", "Handbags", "Tote Bags", "Backpacks",
        "Messenger Bags", "Luggage", "Briefcases", "Bags & Cases", "Bags & Wallets",
    ],
    "jewelry": [
        "Jewelry", "Earrings", "Necklaces", "Bracelets & Bangles", "Bracelets", "Rings",
        "Brooches", "Charms & Pendants", "Cuff Links", "Watches & Jewelry",
    ],
    "accessory": [
        "Accessories", "Sunglasses", "Eyeglasses", "Eyewear", "Hats", "Scarves", "Belts",
        "Gloves", "Hair Accessories", "Socks", "Tights", "Hosiery", "Ties", "Bow Ties",
        "Suspenders", "Umbrellas", "Watches", "Wallets", "Tech Accessories",
        "Key Rings & Chains", "Money Clips", "Handkerchiefs",
    ],
}
_POLYVORE_LOOKUP = {name.lower(): coarse for coarse, names in POLYVORE_COARSE.items() for name in names}


def polyvore_coarse(fine):
    if not fine:
        return None
    key = re.sub(r"^men's\s+", "", fine.strip().lower())
    return _POLYVORE_LOOKUP.get(key, "other")


# --------------------------------------------------------------------------------------
# source adapters: row dict (without image) -> unified record (without image_path)
# --------------------------------------------------------------------------------------
def _s(v):
    if v is None:
        return None
    if isinstance(v, float) and v != v:  # NaN
        return None
    v = str(v).strip()
    return v or None


def adapt_kagl(row):
    return dict(
        item_id=str(row["item_ID"]),
        title=_s(row.get("text")) or "",
        description=None,
        category=kagl_coarse(row.get("category1"), row.get("category2"), row.get("category3")),
        subcategory=_s(row.get("category3")),
        color=_s(row.get("baseColour")),
        season=_s(row.get("season")),
        occasion=_s(row.get("usage")),
        gender=_s(row.get("gender")),
        price=None, currency=None, outfit_ids=None,
    )


def adapt_ashraq(row):  # same Kaggle metadata, original column names, 60x80 images
    return adapt_kagl({
        "item_ID": row["id"], "text": row.get("productDisplayName"),
        "category1": row.get("masterCategory"), "category2": row.get("subCategory"),
        "category3": row.get("articleType"), "baseColour": row.get("baseColour"),
        "season": row.get("season"), "usage": row.get("usage"), "gender": row.get("gender"),
    })


def polyvore_set_id(item_id: str) -> str | None:
    # Maryland Polyvore item ids are "<outfit set_id>_<position in outfit>"
    m = re.fullmatch(r"(\d+)_(\d+)", item_id)
    return m.group(1) if m else None


def adapt_polyvore(row):
    item_id = str(row["item_ID"])
    sid = polyvore_set_id(item_id)
    return dict(
        item_id=item_id,
        title=_s(row.get("text")) or "",
        description=None,
        category=polyvore_coarse(_s(row.get("category"))),
        subcategory=_s(row.get("category")),
        color=None, season=None, occasion=None, gender=None,
        price=None, currency=None,
        outfit_ids=[sid] if sid else None,
    )


SOURCES = {
    "Marqo/KAGL": dict(split="data", image="image", adapt=adapt_kagl,
                       columns=["image", "gender", "category1", "category2", "category3",
                                "baseColour", "season", "usage", "text", "item_ID"],
                       license="MIT (as stated on HF card; upstream Kaggle paramaggarwal/fashion-product-images-dataset, images from Myntra)"),
    "ashraq/fashion-product-images-small": dict(
        split="train", image="image", adapt=adapt_ashraq,
        columns=["id", "gender", "masterCategory", "subCategory", "articleType", "baseColour",
                 "season", "usage", "productDisplayName", "image"],
        license="not stated on HF card (upstream Kaggle paramaggarwal/fashion-product-images-small; Kaggle-side licence not verified)"),
    "Marqo/polyvore": dict(split="data", image="image", adapt=adapt_polyvore,
                           columns=["image", "category", "text", "item_ID"],
                           license="apache-2.0 (as stated on HF card; card disclaims ownership, upstream xthan/polyvore-dataset scraped from polyvore.com)"),
}


# --------------------------------------------------------------------------------------
def save_image(raw: dict, dst: Path) -> None:
    data = raw.get("bytes")
    img = Image.open(io.BytesIO(data)) if data else Image.open(raw["path"])
    img.load()
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))  # polyvore PNGs are transparent
        bg.paste(img, mask=img.split()[-1])
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    img.save(dst, "JPEG", quality=90, optimize=True)


def safe_name(item_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", item_id)


def cooccurrence(df: pd.DataFrame) -> tuple[dict, dict]:
    """Upper-triangular coarse x coarse counts of item pairs sharing an outfit.

    Output format matches engine02.compat.CategoryCooccurrence (which symmetrises), keys
    sorted so each unordered pair is stored once; diagonal = same-category pairs.
    """
    outfits = defaultdict(list)
    for cat, oids in zip(df["category"], df["outfit_ids"]):
        if oids is None or cat is None:
            continue
        for o in oids:
            outfits[o].append(cat)
    pairs = Counter()
    presence = Counter()
    for cats in outfits.values():
        for a, b in combinations(cats, 2):
            pairs[tuple(sorted((a, b)))] += 1
        for a, b in combinations(sorted(set(cats)), 2):
            presence[(a, b)] += 1
    counts: dict[str, dict[str, int]] = {}
    for (a, b), n in sorted(pairs.items()):
        counts.setdefault(a, {})[b] = n
    sizes = Counter(len(c) for c in outfits.values())
    meta = dict(
        n_outfits=len(outfits), n_items=int(sum(len(c) for c in outfits.values())),
        outfit_size_hist={str(k): v for k, v in sorted(sizes.items())},
        definition="counts[a][b] (a<=b) = number of item pairs in the same outfit with coarse categories a,b",
        outfits_containing_both={f"{a}|{b}": n for (a, b), n in sorted(presence.items())},
    )
    return counts, meta


def load_full_metadata(source: str, columns: list[str]) -> pd.DataFrame:
    """Read only non-image columns of every parquet shard (no image bytes kept)."""
    import pyarrow.parquet as pq
    from huggingface_hub import HfFileSystem

    fs = HfFileSystem()
    files = sorted(fs.glob(f"datasets/{source}/data/*.parquet"))
    frames = []
    for f in files:
        with fs.open(f, "rb") as fh:
            frames.append(pq.ParquetFile(fh).read(columns=columns).to_pandas())
        print(f"  metadata {f.rsplit('/', 1)[-1]} done", flush=True)
    return pd.concat(frames, ignore_index=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True, choices=sorted(SOURCES))
    ap.add_argument("--limit", type=int, default=5000, help="max items (0 = all)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--shuffle-buffer", type=int, default=0,
                    help="0 = dataset order; >0 = shuffle shard order + buffer (reproducible with --seed)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--full-cooccurrence", action="store_true",
                    help="outfit sources only: compute co-occurrence over the whole dataset's metadata")
    ap.add_argument("--metadata-parquet", default=None,
                    help="with --full-cooccurrence: reuse a cached parquet of the non-image columns")
    args = ap.parse_args(argv)

    from datasets import Image as HFImage, load_dataset

    spec = SOURCES[args.source]
    out = Path(args.out)
    (out / "images").mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    ds = load_dataset(args.source, split=spec["split"], streaming=True)
    ds = ds.select_columns(spec["columns"]).cast_column(spec["image"], HFImage(decode=False))
    if args.shuffle_buffer > 0:
        ds = ds.shuffle(seed=args.seed, buffer_size=args.shuffle_buffer)

    records, failed, seen = [], 0, set()
    for row in ds:
        if args.limit and len(records) >= args.limit:
            break
        raw = row.pop(spec["image"])
        rec = spec["adapt"](row)
        if rec["item_id"] in seen:
            continue
        rel = f"images/{safe_name(rec['item_id'])}.jpg"
        try:
            save_image(raw, out / rel)
        except Exception as e:  # corrupt / missing image -> skip item
            failed += 1
            print(f"  skip {rec['item_id']}: {e}", file=sys.stderr)
            continue
        seen.add(rec["item_id"])
        rec["image_path"] = rel
        rec["source"] = args.source
        rec["attr_source"] = json.dumps({a: ("dataset" if rec[a] is not None else "null") for a in ATTRS})
        records.append(rec)
        if len(records) % 500 == 0:
            print(f"  {len(records)} items  {time.time() - t0:.0f}s", flush=True)
    t_stream = time.time() - t0

    cols = ["item_id", "title", "description", "category", "subcategory", "color", "season",
            "occasion", "gender", "price", "currency", "outfit_ids", "image_path", "source", "attr_source"]
    df = pd.DataFrame.from_records(records, columns=cols)
    df["price"] = df["price"].astype("float64")
    import pyarrow as pa
    import pyarrow.parquet  # noqa: F401  (registers pa.parquet)
    schema = pa.schema([(c, pa.float64() if c == "price" else pa.list_(pa.string()) if c == "outfit_ids"
                         else pa.string()) for c in cols])
    pa.parquet.write_table(pa.Table.from_pandas(df, schema=schema, preserve_index=False),
                           out / "items.parquet")

    size_mb = sum(p.stat().st_size for p in out.rglob("*") if p.is_file()) / 1e6
    stats = dict(
        source=args.source, license=spec["license"], n_items=len(df), failed_images=failed,
        limit=args.limit, shuffle_buffer=args.shuffle_buffer, seed=args.seed,
        seconds=round(t_stream, 1), disk_mb=round(size_mb, 1),
        category=df["category"].value_counts(dropna=False).to_dict(),
        color=df["color"].value_counts(dropna=False).to_dict(),
        occasion=df["occasion"].value_counts(dropna=False).to_dict(),
        season=df["season"].value_counts(dropna=False).to_dict(),
        gender=df["gender"].value_counts(dropna=False).to_dict(),
        attr_coverage={a: float(df[a].notna().mean()) if len(df) else 0.0 for a in ATTRS},
    )

    has_outfits = df["outfit_ids"].notna().any()
    cooc_note = "no outfit groupings in this source; co-occurrence not computed"
    if has_outfits:
        if args.full_cooccurrence:
            meta_cols = [c for c in spec["columns"] if c != spec["image"]]
            if args.metadata_parquet and Path(args.metadata_parquet).exists():
                meta = pd.read_parquet(args.metadata_parquet)[meta_cols]
            else:
                meta = load_full_metadata(args.source, meta_cols)
            if not (out / "metadata_full.parquet").exists():
                meta.to_parquet(out / "metadata_full.parquet", index=False)
            full = pd.DataFrame.from_records([spec["adapt"](r) for r in meta.to_dict("records")])
            counts, cmeta = cooccurrence(full)
            cmeta["scope"] = f"full dataset metadata ({len(full)} items)"
        else:
            counts, cmeta = cooccurrence(df)
            cmeta["scope"] = f"streamed sample only ({len(df)} items; outfits may be truncated at the limit boundary)"
        (out / "category_cooccurrence.json").write_text(json.dumps(counts, indent=1), encoding="utf-8")
        (out / "category_cooccurrence.meta.json").write_text(json.dumps(cmeta, indent=1), encoding="utf-8")
        stats["cooccurrence"] = {k: v for k, v in cmeta.items() if k != "outfits_containing_both"}
        cooc_note = f"category_cooccurrence.json: {cmeta['scope']}, {cmeta['n_outfits']} outfits"

    (out / "stats.json").write_text(json.dumps(stats, indent=1, ensure_ascii=False), encoding="utf-8")
    write_readme(out, stats, cooc_note)
    print(json.dumps(stats, indent=1, ensure_ascii=False))


def write_readme(out: Path, s: dict, cooc_note: str) -> None:
    def vc(d, n=25):
        return "\n".join(f"| {k} | {v} |" for k, v in list(d.items())[:n])

    txt = f"""# Catalog: {s['source']}

Generated by `scripts/prepare_catalog.py` (streamed from Hugging Face, images resized to max side {MAX_SIDE} px JPEG).

- Source: https://huggingface.co/datasets/{s['source']}
- Licence (as stated on the card): {s['license']}
- Items: {s['n_items']} (limit={s['limit']}, shuffle_buffer={s['shuffle_buffer']}, seed={s['seed']}); failed images: {s['failed_images']}
- Build time: {s['seconds']} s; disk: {s['disk_mb']} MB
- Attribute coverage (non-null share): {json.dumps(s['attr_coverage'])}
- Outfits: {cooc_note}
- Values are copied from the dataset only; unknown fields are null (see `attr_source`).

Files: `items.parquet`, `images/`, `stats.json`{', `category_cooccurrence.json`, `category_cooccurrence.meta.json`' if 'cooccurrence' in s else ''}.

## category (coarse)
| value | n |
|---|---|
{vc(s['category'])}

## color
| value | n |
|---|---|
{vc(s['color'])}

## occasion
| value | n |
|---|---|
{vc(s['occasion'])}
"""
    (out / "README.md").write_text(txt, encoding="utf-8")


if __name__ == "__main__":
    main()
