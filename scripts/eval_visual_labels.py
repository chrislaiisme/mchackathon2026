"""AUROC of c(i,d) variants against blind visual labels (data/labels/labels_part_*.csv).

  python scripts/eval_visual_labels.py --encoder marqo-fashionSigLIP

Compares concept modes cached under data/catalog/kagl/index (descriptor, random_words,
antonym) and, if present, the VLM tagging parquet. Labels were produced by an LLM
annotator looking at the photos (not by humans) — report them as such.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from engine02.eval.tasks import auroc  # noqa: E402
from engine02.kansei import KanseiTable  # noqa: E402

VARIANTS = {
    "descriptor (PRD)": "descriptor_dn0_mask0",
    "random_words": "random_words_dn1_mask1",
    "antonym+DN": "antonym_dn1_mask0",
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default="data/catalog/kagl")
    ap.add_argument("--encoder", default="marqo-fashionSigLIP")
    ap.add_argument("--out", default="reports/ablation/visual_label_auroc.csv")
    args = ap.parse_args()

    cat = ROOT / args.catalog
    items = pd.read_parquet(cat / "items.parquet")
    pos = {str(i): p for p, i in enumerate(items["item_id"].astype(str))}
    labels = pd.concat([pd.read_csv(f, dtype={"item_id": str, "label": str})
                        for f in sorted((ROOT / "data/labels").glob("labels_part_*.csv"))])
    labels = labels[labels["label"].isin(["0", "1"])].copy()
    labels["y"] = labels["label"].astype(int)
    table = KanseiTable.load()

    scores: dict[str, np.ndarray] = {}
    for name, suffix in VARIANTS.items():
        f = cat / "index" / f"design_{args.encoder}_{table.version}_{suffix}.npy"
        if f.exists():
            scores[f"{args.encoder}:{name}"] = np.load(f)
    vlm_files = sorted(cat.glob("vlm_attributes_*.parquet"))
    if vlm_files:
        vdf = pd.read_parquet(vlm_files[-1]).set_index("item_id")
        m = np.full((len(items), len(table.elements)), np.nan)
        for j, el in enumerate(table.elements):
            if f"c_{el.id}" in vdf.columns:
                col = vdf[f"c_{el.id}"].reindex(items["item_id"].astype(str)).to_numpy(dtype=float)
                m[:, j] = col
        scores[f"VLM:{vlm_files[-1].stem.replace('vlm_attributes_', '')}"] = m

    rows = []
    rng = np.random.default_rng(0)
    for el, g in labels.groupby("element"):
        j = table.element_ids.index(el)
        idx = np.array([pos[i] for i in g["item_id"]])
        y = g["y"].to_numpy()
        for name, mat in scores.items():
            s = mat[idx, j]
            ok = ~np.isnan(s)
            a = auroc(s[ok], y[ok])
            boots = []
            for _ in range(2000):
                b = rng.integers(0, ok.sum(), ok.sum())
                boots.append(auroc(s[ok][b], y[ok][b]))
            rows.append(dict(element=el, scorer=name, auroc=a, ci95_lo=np.nanquantile(boots, 0.025),
                             ci95_hi=np.nanquantile(boots, 0.975), n_pos=int(y[ok].sum()), n_neg=int((1 - y[ok]).sum())))
    df = pd.DataFrame(rows)
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(df.pivot(index="element", columns="scorer", values="auroc").round(3).to_string())
    print(df.groupby("element")[["n_pos", "n_neg"]].first().to_string())


if __name__ == "__main__":
    main()
