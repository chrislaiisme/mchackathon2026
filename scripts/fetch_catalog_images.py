"""Download the images a committed catalog points at, so a fresh clone can use it.

Catalogs whose items.parquet is in the repo (e.g. data/catalog/hm_filled, which a GPU filled in)
ship without their images -- those are third-party and large. Every row keeps an `image_url`,
so this rebuilds `images/` exactly (384 px JPEG, the same size prepare_catalog_*.py writes).

    python scripts/fetch_catalog_images.py --catalog data/catalog/hm_filled
    python scripts/fetch_catalog_images.py --catalog data/catalog/hm_filled --workers 16

Existing files are skipped, so it can be re-run after an interruption. No account is needed.
"""

from __future__ import annotations

import argparse
import io
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def fetch(url: str, dst: Path) -> bool:
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                im = Image.open(io.BytesIO(r.read())).convert("RGB")
            im.thumbnail((384, 384))
            dst.parent.mkdir(parents=True, exist_ok=True)
            im.save(dst, "JPEG", quality=90)
            return True
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return False
            time.sleep(2 * (attempt + 1))
        except (urllib.error.URLError, OSError):
            time.sleep(2 * (attempt + 1))
    return False


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    cat = Path(a.catalog) if Path(a.catalog).is_absolute() else ROOT / a.catalog
    items = pd.read_parquet(cat / "items.parquet")
    if "image_url" not in items.columns:
        sys.exit(f"{cat}/items.parquet has no image_url column; this catalog cannot be rebuilt this way")
    img_dir = cat / "images"
    if img_dir.is_symlink() and not img_dir.exists():
        img_dir.unlink()                          # a dangling link from the machine that built it
    todo = [(u, cat / p) for u, p in zip(items["image_url"], items["image_path"]) if not (cat / p).exists()]
    print(f"{len(items)} items, {len(items) - len(todo)} images present, {len(todo)} to fetch", flush=True)
    ok = 0
    with ThreadPoolExecutor(a.workers) as ex:
        for i, good in enumerate(ex.map(lambda t: fetch(*t), todo), 1):
            ok += good
            if i % 500 == 0:
                print(f"  {i}/{len(todo)}", flush=True)
    print(f"fetched {ok}, failed {len(todo) - ok}")


if __name__ == "__main__":
    main()
