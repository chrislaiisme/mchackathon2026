"""A catalog with prices, for testing the budget path — clearly synthetic, never for evaluation.

The public catalogs we rank on have no price column, and the one real priced sample
(`data/catalog/amz_smoke`, 15 items) is smaller than `ArmConfig.min_results`, so every filter on it
trips the relaxation ladder and no budget behaviour can be observed. This derives a fixture from
KAGL with deterministic synthetic prices so the budget path can be tested end to end.

    python scripts/make_priced_fixture.py --n 500

The prices are invented. The README written next to the fixture says so, the catalog name says so,
and nothing in docs/engine02-design.md may quote a number measured on it.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SEED = 20260919

# rough price bands by coarse category, in TWD, so a budget question has a sensible answer
BANDS = {
    "top": (390, 1890), "bottom": (590, 2490), "dress": (890, 3490), "outerwear": (1290, 5990),
    "shoes": (890, 3990), "bag": (690, 4990), "accessory": (190, 1290), "jewelry": (290, 2990),
}
DEFAULT_BAND = (390, 1990)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default="data/catalog/kagl")
    ap.add_argument("--out", default="data/catalog/kagl_priced_fixture")
    ap.add_argument("--n", type=int, default=500)
    a = ap.parse_args()

    import numpy as np
    import pandas as pd

    src = ROOT / a.source
    dst = ROOT / a.out
    items = pd.read_parquet(src / "items.parquet")
    rng = np.random.default_rng(SEED)
    take = items.sample(min(a.n, len(items)), random_state=SEED).reset_index(drop=True)

    lo = take["category"].astype(str).map(lambda c: BANDS.get(c, DEFAULT_BAND)[0])
    hi = take["category"].astype(str).map(lambda c: BANDS.get(c, DEFAULT_BAND)[1])
    # log-uniform inside the band: real price distributions are right-skewed, and a uniform draw
    # would make every budget question look equally easy
    u = rng.random(len(take))
    take["price"] = np.round(np.exp(np.log(lo) + u * (np.log(hi) - np.log(lo))) / 10) * 10
    take["currency"] = "TWD"

    dst.mkdir(parents=True, exist_ok=True)
    take.to_parquet(dst / "items.parquet", index=False)

    # images: reuse the source directory rather than copying a second set
    img_src, img_dst = src / "images", dst / "images"
    if img_src.exists() and not img_dst.exists():
        try:
            img_dst.symlink_to(img_src, target_is_directory=True)
        except OSError:
            shutil.copytree(img_src, img_dst)

    (dst / "README.md").write_text(
        "# kagl_priced_fixture — SYNTHETIC PRICES, TESTS ONLY\n\n"
        f"{len(take)} items drawn from `{a.source}` with **invented** prices (log-uniform inside a\n"
        "per-category band, seed 20260919). It exists because the budget path cannot be exercised\n"
        "on a catalog with no prices, and the one real priced sample is smaller than\n"
        "`ArmConfig.min_results` so every filter on it trips the relaxation ladder.\n\n"
        "**No number measured on this catalog may be quoted as a result.** It is a fixture for\n"
        "testing that a budget filters, relaxes and reports correctly — not evidence about prices,\n"
        "assortment or affordability.\n",
        encoding="utf-8")
    print(f"{len(take)} items → {dst}")
    print(f"price: min {take['price'].min():.0f}  median {take['price'].median():.0f}  "
          f"max {take['price'].max():.0f} TWD (synthetic)")


if __name__ == "__main__":
    main()
