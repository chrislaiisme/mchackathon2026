"""Merge prepared catalogs into one (e.g. KAGL with Polyvore apparel for more outerwear/knitwear).

  python scripts/merge_catalogs.py --inputs data/catalog/kagl data/catalog/polyvore_big \
      --keep-categories top,bottom,outerwear,dress,shoes,bag --out data/catalog/kagl_polyvore

Item ids are prefixed with the source catalog name to stay unique; image files are
hard-linked (copied if linking fails) into <out>/images/<catalog>/.
"""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path

import pandas as pd


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", nargs="+", required=True)
    ap.add_argument("--keep-categories", default="")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    keep = {c for c in args.keep_categories.split(",") if c}
    out = Path(args.out)
    frames = []
    for inp in map(Path, args.inputs):
        df = pd.read_parquet(inp / "items.parquet")
        if keep:
            df = df[df["category"].isin(keep)].copy()
        name = inp.name
        (out / "images" / name).mkdir(parents=True, exist_ok=True)
        new_paths = []
        for rel in df["image_path"]:
            src = inp / rel
            dst_rel = f"images/{name}/{Path(rel).name}"
            dst = out / dst_rel
            if not dst.exists():
                try:
                    os.link(src, dst)
                except OSError:
                    shutil.copy2(src, dst)
            new_paths.append(dst_rel)
        df["image_path"] = new_paths
        df["item_id"] = name + ":" + df["item_id"].astype(str)
        frames.append(df)
        print(f"{name}: {len(df)} items kept", flush=True)
    merged = pd.concat(frames, ignore_index=True)
    merged.to_parquet(out / "items.parquet", index=False)
    (out / "README.md").write_text(
        "Merged catalog: " + ", ".join(args.inputs) + f"\nKeep categories: {sorted(keep) or 'all'}\n"
        + merged.groupby(["source", "category"]).size().to_string() + "\n",
        encoding="utf-8",
    )
    print(merged.groupby(["source", "category"]).size().to_string())


if __name__ == "__main__":
    main()
