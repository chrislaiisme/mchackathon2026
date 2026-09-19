"""Build a modern-looking ENGINE 02 catalog from the H&M Personalized Fashion dataset (2018-2020).

KAGL (Myntra, ~2012) is clean but visibly dated. H&M's articles are studio product shots on one
consistent background, and -- unlike Amazon -- every attribute we need is a HUMAN label from H&M:
product type, colour, pattern, department. Nothing here is guessed; season and occasion are the only
fields H&M does not have, and they are left empty for scripts/vlm_fill_catalog.py to fill with an
explicit provenance.

Source: https://huggingface.co/datasets/einrafh/hnm-fashion-recommendations-data -- an open mirror
of the Kaggle competition data (no Kaggle account needed), one JPEG per article.
Licence of the upstream data: "DATA ACCESS AND USE: Non-Commercial Purposes & Academic Research"
(Kaggle H&M competition rules). Fine for a hackathon demo; NOT for anything the sponsor ships.

    python scripts/prepare_catalog_hm.py --n 10000 --out data/catalog/hm
    python scripts/prepare_catalog_hm.py --n 50 --out data/catalog/hm_smoke     # quick check

Deterministic: same --n and --seed give the same items in the same order.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from PIL import Image  # noqa: E402

REPO = "https://huggingface.co/datasets/einrafh/hnm-fashion-recommendations-data/resolve/main"
ARTICLES = f"{REPO}/data/processed/articles.parquet"

# product_type_name -> our coarse slot. Anything not listed is dropped (and counted), never guessed.
CATEGORY = {
    **{t: "top" for t in ("T-shirt", "Top", "Blouse", "Shirt", "Vest top", "Sweater", "Hoodie",
                          "Cardigan", "Polo shirt", "Bodysuit", "Tailored Waistcoat")},
    **{t: "bottom" for t in ("Trousers", "Skirt", "Shorts", "Leggings/Tights", "Outdoor trousers")},
    **{t: "dress" for t in ("Dress", "Jumpsuit/Playsuit", "Dungarees", "Garment Set")},
    **{t: "outerwear" for t in ("Jacket", "Blazer", "Coat", "Outdoor Waistcoat", "Outdoor overall")},
    **{t: "shoes" for t in ("Boots", "Sneakers", "Sandals", "Other shoe", "Heeled sandals", "Pumps",
                            "Ballerinas", "Flat shoe", "Wedge", "Bootie", "Slippers", "Flip flop",
                            "Moccasins", "Leather shoes", "Flat shoes")},
}
CATEGORY.update({"Bag": "bag", "Cross-body bag": "bag", "Shoulder bag": "bag", "Tote bag": "bag",
                 "Backpack": "bag", "Weekend/Gym bag": "bag", "Bumbag": "bag"})

# H&M colour_group_name -> this catalog's colour vocabulary (engine02/attribute_fill.py
# COLOR_FAMILIES). Asserted below: a value the intent adapter and negation logic cannot resolve
# must never be written. None = no single colour (the field stays empty).
COLOR = {
    "Black": "Black", "White": "White", "Off White": "Off White", "Grey": "Grey",
    "Light Grey": "Grey", "Dark Grey": "Charcoal", "Silver": "Silver",
    "Blue": "Blue", "Light Blue": "Blue", "Other Blue": "Blue", "Dark Blue": "Navy Blue",
    "Turquoise": "Turquoise Blue", "Light Turquoise": "Turquoise Blue",
    "Dark Turquoise": "Teal", "Other Turquoise": "Teal",
    "Red": "Red", "Light Red": "Red", "Other Red": "Red", "Dark Red": "Maroon",
    "Pink": "Pink", "Light Pink": "Pink", "Other Pink": "Pink", "Dark Pink": "Magenta",
    "Purple": "Purple", "Dark Purple": "Purple", "Other Purple": "Purple", "Light Purple": "Lavender",
    "Green": "Green", "Light Green": "Green", "Dark Green": "Green", "Other Green": "Green",
    "Greenish Khaki": "Olive",
    "Yellow": "Yellow", "Light Yellow": "Yellow", "Other Yellow": "Yellow", "Dark Yellow": "Mustard",
    "Gold": "Gold",
    "Orange": "Orange", "Light Orange": "Orange", "Dark Orange": "Orange", "Other Orange": "Orange",
    "Beige": "Beige", "Light Beige": "Beige", "Dark Beige": "Khaki",
    "Greyish Beige": "Taupe", "Yellowish Brown": "Tan", "Bronze/Copper": "Bronze",
    "Other": None, "Transparent": None, "Unknown": None,
}
PATTERN = {  # graphical_appearance_name -> the pattern vocabulary used by vlm_fill_catalog.py
    "Solid": "solid", "Melange": "solid", "Denim": "solid", "Treatment": "solid",
    "Stripe": "stripe_check", "Check": "stripe_check", "Dot": "graphic",
    "All over pattern": "graphic", "Placement print": "graphic", "Front print": "graphic",
    "Application/3D": "other", "Embroidery": "other", "Colour blocking": "other",
    "Other structure": "other", "Lace": "other", "Jacquard": "other",
    "Glittering/Metallic": "other", "Other pattern": "other", "Mixed solid/pattern": "other",
    "Chambray": "solid", "Sequin": "other", "Metallic": "other", "Contrast": "other",
    "Argyle": "stripe_check", "Hologram": "other", "Mesh": "other", "Neps": "solid",
    "Slub": "solid", "Transparent": "other", "Unknown": None,
}


def gender_of(index_name: str, section: str) -> str | None:
    s = f"{index_name} {section}".lower()
    if "kid" in s or "baby" in s or "child" in s:
        return None                                   # dropped: the demo is for adult shoppers
    if index_name == "Menswear" or s.startswith("sport men") or "men h&m sport" in s:
        return "Men"
    return "Women"                                    # Ladieswear, Divided, Ladies Sport, accessories


def fetch(url: str, timeout: int = 60) -> bytes:
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise
            time.sleep(2 * (attempt + 1))
        except (urllib.error.URLError, OSError):
            time.sleep(2 * (attempt + 1))
    raise OSError(f"failed after retries: {url}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=10000)
    ap.add_argument("--out", default="data/catalog/hm")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--articles", default=None, help="local articles.parquet (skip the download)")
    a = ap.parse_args()

    from engine02.attribute_fill import COLOR_TO_FAMILY
    bad = {v for v in COLOR.values() if v and v.lower() not in COLOR_TO_FAMILY}
    assert not bad, f"colour values the catalog vocabulary cannot resolve: {bad}"

    out = ROOT / a.out
    (out / "images").mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    art = pd.read_parquet(a.articles) if a.articles else pd.read_parquet(io.BytesIO(fetch(ARTICLES, 300)))
    n_all = len(art)
    art["gender"] = [gender_of(i, s) for i, s in zip(art.index_name, art.section_name)]
    art["category"] = art.product_type_name.map(CATEGORY)
    unmapped = art.loc[art.gender.notna() & art.category.isna(), "product_type_name"].value_counts()
    pool = art[art.gender.notna() & art.category.notna()].copy()
    pool["article_id"] = pool.article_id.astype(str).str.zfill(10)
    pool = pool.sort_values("article_id").reset_index(drop=True)      # stable order before sampling

    # weight 1/sqrt(type count): keeps every type present without letting T-shirts dominate
    w = 1.0 / np.sqrt(pool.groupby("product_type_name").article_id.transform("count").to_numpy())
    rng = np.random.default_rng(a.seed)
    order = rng.choice(len(pool), size=min(len(pool), int(a.n * 1.4)), replace=False, p=w / w.sum())
    cand = pool.iloc[order]

    def get(aid: str) -> tuple[str, bool]:
        dst = out / "images" / f"{aid}.jpg"
        if dst.exists():
            return aid, True
        try:
            im = Image.open(io.BytesIO(fetch(f"{REPO}/data/raw/images/{aid[:3]}/{aid}.jpg"))).convert("RGB")
        except (OSError, urllib.error.HTTPError):
            return aid, False                                # ~20% of articles have no image
        im.thumbnail((384, 384))
        im.save(dst, "JPEG", quality=90)
        return aid, True

    ok: dict[str, bool] = {}
    ids = list(cand.article_id)
    with ThreadPoolExecutor(a.workers) as ex:
        for i in range(0, len(ids), 200):                    # stop once n items have images
            for aid, good in ex.map(get, ids[i:i + 200]):
                ok[aid] = good
            if sum(ok.values()) >= a.n:
                break
            print(f"  {sum(ok.values())} images / {len(ok)} tried", flush=True)
    keep = [aid for aid in ids if ok.get(aid)][: a.n]
    for f in (out / "images").glob("*.jpg"):                  # images of candidates beyond n
        if f.stem not in set(keep):
            f.unlink()
    sel = cand.set_index("article_id").loc[keep].reset_index()

    items = pd.DataFrame({
        "item_id": "hm_" + sel.article_id,
        "title": sel.prod_name.astype(str),
        "description": sel.detail_desc.where(sel.detail_desc.notna(), None),
        "category": sel.category,
        "subcategory": sel.product_type_name,
        "color": sel.colour_group_name.map(COLOR),
        "season": None,                   # H&M has no season -> vlm_fill_catalog.py
        "occasion": None,                 # H&M has no occasion -> vlm_fill_catalog.py
        "gender": sel.gender,
        "price": None,                    # the public data has no product price; never invented
        "currency": None,
        "outfit_ids": None,
        "image_path": "images/" + sel.article_id + ".jpg",
        "source": "hm",
        "pattern": sel.graphical_appearance_name.map(PATTERN),
        "hm_colour": sel.colour_group_name,
        "hm_section": sel.section_name,
        "image_url": REPO + "/data/raw/images/" + sel.article_id.str[:3] + "/" + sel.article_id + ".jpg",
    })
    items["attr_source"] = [json.dumps({
        "color": "dataset" if c else "null", "season": "null", "occasion": "null",
        "gender": "dataset", "price": "null"}) for c in items.color]
    items.to_parquet(out / "items.parquet", index=False)

    cov = {k: round(float(items[k].notna().mean()), 4) for k in ("color", "season", "occasion", "gender", "price")}
    stats = {"source": "einrafh/hnm-fashion-recommendations-data (H&M, 2018-2020)",
             "license": "H&M Kaggle competition: Non-Commercial Purposes & Academic Research",
             "n_items": len(items), "n_articles_upstream": n_all, "adult_apparel_pool": len(pool),
             "images_missing_upstream": sum(1 for v in ok.values() if not v), "tried": len(ok),
             "seed": a.seed, "seconds": round(time.perf_counter() - t0, 1),
             "attr_coverage": cov,
             "category": items.category.value_counts().to_dict(),
             "gender": items.gender.value_counts().to_dict(),
             "dropped_product_types_top": unmapped.head(15).to_dict()}
    (out / "stats.json").write_text(json.dumps(stats, indent=1, ensure_ascii=False), encoding="utf-8")
    (out / "README.md").write_text(
        "# Catalog: H&M (2018-2020)\n\n"
        f"Built by `scripts/prepare_catalog_hm.py --n {a.n} --seed {a.seed}` from the open Hugging Face mirror\n"
        "`einrafh/hnm-fashion-recommendations-data`.\n\n"
        "- **Licence**: H&M Kaggle competition rules -- *Non-Commercial Purposes & Academic Research*.\n"
        "  Product images are H&M's. Hackathon demo only; not for anything shipped commercially.\n"
        "- **Human labels from H&M**: category (product type), colour, pattern, gender (department).\n"
        "- **Not in the source**: season, occasion (filled by `scripts/vlm_fill_catalog.py`, recorded in\n"
        "  `attr_source` as model-filled -- never use those as evaluation ground truth), and **price**.\n"
        "- Images are NOT committed; `image_url` points at the mirror, so the build is reproducible\n"
        "  without any account.\n", encoding="utf-8")
    print(json.dumps({k: stats[k] for k in ("n_items", "adult_apparel_pool", "images_missing_upstream",
                                             "tried", "seconds", "attr_coverage", "category")},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
