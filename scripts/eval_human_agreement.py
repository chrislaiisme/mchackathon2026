"""Human agreement on the visual labels: Cohen's κ vs the LLM annotator, and AUROC on human labels.

The 420 labels in data/labels/labels_part_*.csv were produced by an **LLM annotator**, so every
AUROC that uses them is model-vs-model. This script closes that gap once a human has labelled a
subset with the same three-way scheme (1 / 0 / na).

  # 1. draw a blind subset for a human to label (images are already in the sheets)
  python scripts/eval_human_agreement.py sample --n 120 --out data/labels/human_tasks.csv

  # 2. the human fills in `label` (1 = the element is clearly present, 0 = clearly absent,
  #    na = cannot tell from this photo) without looking at the LLM labels, then:
  python scripts/eval_human_agreement.py score --human data/labels/human_labels.csv \
      --encoder marqo-fashionSigLIP

`score` reports, per design element and overall:
  - Cohen's κ between human and LLM annotator (on items where both gave 1/0)
  - how often each side says "na" (a disagreement about *applicability* is not a labelling error)
  - AUROC of c(i,d) against the human labels, next to the AUROC against the LLM labels on the same
    items — if the human number is much lower, §3.3's AUROCs are optimistic and the slide must say so.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

SEED = 20260918
LABEL_FILES = ("labels_part_a.csv", "labels_part_b.csv")


def load_llm_labels(labels_dir: Path) -> pd.DataFrame:
    frames = [pd.read_csv(labels_dir / f, dtype=str) for f in LABEL_FILES if (labels_dir / f).exists()]
    if not frames:
        raise SystemExit(f"no label files under {labels_dir}")
    df = pd.concat(frames, ignore_index=True)
    df["annotator"] = "llm"
    return df


def cohens_kappa(a: pd.Series, b: pd.Series) -> tuple[float, int]:
    """Two raters, binary labels. Returns (κ, n); κ is nan when a rater is constant."""
    a, b = np.asarray(a, dtype=int), np.asarray(b, dtype=int)
    n = len(a)
    if n == 0:
        return float("nan"), 0
    if len(set(a.tolist())) < 2 or len(set(b.tolist())) < 2:
        return float("nan"), n  # a constant rater makes kappa undefined, not zero
    po = float((a == b).mean())
    pe = float(sum((a == v).mean() * (b == v).mean() for v in (0, 1)))
    return (float("nan") if abs(1 - pe) < 1e-12 else (po - pe) / (1 - pe)), n


def auroc(scores: np.ndarray, y: np.ndarray) -> float:
    pos, neg = scores[y == 1], scores[y == 0]
    if not len(pos) or not len(neg):
        return float("nan")
    r = pd.Series(np.concatenate([pos, neg])).rank().to_numpy()
    return float((r[: len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def cmd_sample(a: argparse.Namespace) -> None:
    llm = load_llm_labels(Path(a.labels_dir))
    tasks = pd.read_csv(Path(a.labels_dir) / "visual_label_tasks.csv", dtype=str)
    # stratify by element so every design element gets human coverage
    per = max(1, a.n // max(1, tasks["element"].nunique()))
    rng = np.random.default_rng(SEED)
    idx: list = []
    for _, g in tasks.groupby("element", sort=True):
        idx += list(g.sample(min(per, len(g)), random_state=int(rng.integers(1 << 31))).index)
    out = tasks.loc[sorted(idx), ["task_id", "element", "item_id", "category", "image_path"]].copy()
    out["label"] = ""          # human fills: 1 / 0 / na
    out["confidence"] = ""     # high / low
    out["note"] = ""
    dst = Path(a.out)
    dst.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(dst, index=False)
    print(f"{len(out)} tasks for a human annotator -> {dst}")
    print(f"(LLM labels exist for {llm['task_id'].nunique()} tasks; they are NOT in this file, keep it blind)")


def cmd_score(a: argparse.Namespace) -> None:
    llm = load_llm_labels(Path(a.labels_dir))
    hum = pd.read_csv(a.human, dtype=str)
    hum = hum[hum["label"].astype(str).str.strip() != ""]
    if hum.empty:
        raise SystemExit("the human label file has no filled-in `label` values")
    key = ["task_id", "element", "item_id"]
    m = hum.merge(llm, on=key, suffixes=("_h", "_llm"))
    print(f"overlap: {len(m)} labelled tasks\n")

    rows = []
    for el, g in m.groupby("element"):
        both = g[(g["label_h"].isin(["0", "1"])) & (g["label_llm"].isin(["0", "1"]))]
        k, n = cohens_kappa(both["label_h"], both["label_llm"])
        rows.append(dict(element=el, n=len(g), n_both_decided=n, kappa=round(k, 3),
                         pos_rate_h=round(float((both["label_h"] == "1").mean()) if n else float("nan"), 3),
                         na_human=round(float((g["label_h"] == "na").mean()), 3),
                         na_llm=round(float((g["label_llm"] == "na").mean()), 3),
                         agree=round(float((both["label_h"] == both["label_llm"]).mean()) if n else float("nan"), 3)))
    both_all = m[(m["label_h"].isin(["0", "1"])) & (m["label_llm"].isin(["0", "1"]))]
    k_all, n_all = cohens_kappa(both_all["label_h"], both_all["label_llm"])
    tab = pd.DataFrame(rows).sort_values("element")
    print(tab.to_string(index=False))
    print(f"\npooled Cohen's kappa = {k_all:.3f} on {n_all} tasks where both raters decided "
          f"(<0.4 poor, 0.4-0.6 moderate, 0.6-0.8 substantial)")
    print("kappa = nan means one rater never used both classes on that element (undefined, not "
          "perfect agreement); read it together with pos_rate_h.")

    if a.encoder:
        from engine02.catalog import Catalog
        from engine02.config import ARMS
        from engine02.encoders import make_encoder
        from engine02.pipeline import Engine02

        cat = Catalog.load(ROOT / "data" / "catalog" / a.catalog)
        eng = Engine02(cat, make_encoder(a.encoder, device=a.device), cache_dir=ROOT / "data" / "catalog" / a.catalog / "index")
        c = eng.design_matrix(ARMS[a.arm])
        ids = {e.id: j for j, e in enumerate(eng.kansei.elements)}
        out = []
        for el, g in m.groupby("element"):
            if el not in ids:
                continue
            g = g[g["label_h"].isin(["0", "1"])]
            pos = [cat.pos(str(i)) for i in g["item_id"]]
            keep = [i for i, p in enumerate(pos) if p is not None]
            if not keep:
                continue
            s = np.array([c[pos[i], ids[el]] for i in keep])
            yh = g["label_h"].to_numpy()[keep].astype(int)
            gl = g["label_llm"].to_numpy()[keep]
            ml = np.isin(gl, ["0", "1"])
            out.append(dict(element=el, n=len(keep), auroc_human=round(auroc(s, yh), 3),
                            auroc_llm=round(auroc(s[ml], gl[ml].astype(int)), 3) if ml.any() else float("nan")))
        if out:
            print("\nAUROC of c(i,d) under each ground truth (same items):")
            print(pd.DataFrame(out).to_string(index=False))
            print("\nIf auroc_human is much lower than auroc_llm, the LLM annotator and the scorer share a\n"
                  "blind spot and every AUROC in §3.3 is optimistic — say so on the slide.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("sample", "score"):
        s = sub.add_parser(name)
        s.add_argument("--labels-dir", default=str(ROOT / "data" / "labels"))
        if name == "sample":
            s.add_argument("--n", type=int, default=120)
            s.add_argument("--out", default=str(ROOT / "data" / "labels" / "human_tasks.csv"))
        else:
            s.add_argument("--human", required=True)
            s.add_argument("--encoder", default="")
            s.add_argument("--catalog", default="kagl")
            s.add_argument("--arm", default="full")
            s.add_argument("--device", default="auto")
    a = ap.parse_args()
    (cmd_sample if a.cmd == "sample" else cmd_score)(a)


if __name__ == "__main__":
    main()
