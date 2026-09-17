"""T12 — the generated-concept-image branch, measured with a stand-in image.

  python scripts/eval_concept_image.py --catalog data/catalog/kagl_polyvore \
      --encoder marqo-fashionSigLIP --out reports/agents/audit/concept_image_kagl_polyvore

`FeedbackState.concept_image_embedding` and the arm `full_concept_image`
(`concept_image_weight=0.2`) have existed since the first commit but were never run: the
generation branch has no images yet, so docs/engine02-design.md §3.6 lists the arm as "not run".
The literature says naive fusion of a generated image into the query is at best neutral and can
be worse than text alone (Category-level Text-to-Image Retrieval Improved, BMVC 2025,
arXiv 2509.00177: text 62.7 mAP, generated image 41.4, naive 0.5/0.5 fusion 61.0; Imagine and
Seek / IP-CIR, CVPR 2025, arXiv 2411.16752: Fashion IQ R@10 45.11 → 45.74). So the weight must be
measured before the demo relies on it.

Stand-in protocol (no image generation needed)
----------------------------------------------
For each of `--n-targets` hidden target items:
  * the user's words are **vague** — `retrieval_text = "{gender} {category}"`, hard constraints
    category + gender, exactly the round-1 setting of T5;
  * the "generated concept image" is a **held-out catalog image**, and the target item itself is
    put in `excluded_item_ids`, so the concept image can never be answered by returning the image
    it came from;
  * three concept sources:
      `oracle`      the target's own image — the *best case* a perfect generator could produce.
                    If fusion does not help here it cannot help with a real generated image.
      `neighbour`   the most similar *other* item to the target: a realistic generator that gets
                    the idea roughly right.
      `mismatched`  a random other item: the control. If `oracle` and `mismatched` move the
                    ranking by the same amount, the weight is adding noise, not information.
  * weights: `--weights 0,0.1,0.2` (0 = today's default, 0.2 = the `full_concept_image` arm).

Metrics per target: NDCG@5/@10 and HitRate@5 against the target's attributes (subcategory, colour,
gender, occasion — the same grading as T1, and the encoder never sees those columns), plus the
mean cosine of the top-5 to the concept embedding (did the query actually move toward the image?).
Paired permutation test and bootstrap CI over targets, versus weight 0 on the same targets.

Caveat to state on the slide: a catalog photo is a white-background product shot, while a real
generated concept image is a model/lifestyle render, and FashionCLIP-family encoders prefer
product shots (model card, PRD [112]). So `oracle` here is an **upper bound** on what the real
generation branch can deliver — a negative result is therefore conclusive, a positive one is not.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from engine02.catalog import Catalog  # noqa: E402
from engine02.config import ARMS  # noqa: E402
from engine02.contracts import (  # noqa: E402
    Engine02Options,
    Engine02Request,
    FeedbackState,
    HardConstraints,
    Slot,
    SlotState,
)
from engine02.encoders import HashEncoder  # noqa: E402
from engine02.eval.metrics import bootstrap_ci, hit_at_k, ndcg_at_k, paired_permutation_test  # noqa: E402
from engine02.eval.tasks import APPAREL, Query  # noqa: E402
from engine02.pipeline import Engine02  # noqa: E402

SOURCES = ("oracle", "neighbour", "mismatched")


def _slot(values):
    return Slot(state=SlotState.VALUE, values=list(values))


def concept_positions(engine, targets: list[int], rng: random.Random) -> dict[str, dict[int, int]]:
    """For every target, the catalog position whose image stands in for the concept image."""
    emb = np.asarray(engine.image_emb, dtype=np.float64)
    out: dict[str, dict[int, int]] = {s: {} for s in SOURCES}
    n = len(emb)
    for t in targets:
        sims = emb @ emb[t]
        sims[t] = -np.inf
        out["oracle"][t] = t
        out["neighbour"][t] = int(np.argmax(sims))
        other = rng.randrange(n)
        while other == t:
            other = rng.randrange(n)
        out["mismatched"][t] = other
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default="data/catalog/kagl_polyvore")
    ap.add_argument("--encoder", default="marqo-fashionSigLIP")
    ap.add_argument("--device", default="auto")
    ap.add_argument("--arm", default="full_zclip3")
    ap.add_argument("--weights", default="0,0.1,0.2")
    ap.add_argument("--n-targets", type=int, default=150)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--cache-dir", default=None)
    ap.add_argument("--out", default="reports/agents/audit/concept_image")
    args = ap.parse_args()

    out = Path(args.out if Path(args.out).is_absolute() else ROOT / args.out)
    out.mkdir(parents=True, exist_ok=True)
    cat = Catalog.load(ROOT / args.catalog)
    if args.encoder == "hash":
        enc = HashEncoder(dim=256, captions={Path(p).name: t for p, t in zip(cat.items["image_path"], cat.texts())})
    else:
        from engine02.models import TorchEncoder

        enc = TorchEncoder(args.encoder, device=args.device)
    engine = Engine02(cat, enc, cache_dir=args.cache_dir)
    base = ARMS[args.arm]
    weights = [float(w) for w in args.weights.split(",")]
    items = cat.items

    rng = random.Random(args.seed)
    pool = items[items["category"].isin(APPAREL)].dropna(subset=["gender", "color", "subcategory", "occasion"])
    targets = rng.sample(list(pool.index), min(args.n_targets, len(pool)))
    concepts = concept_positions(engine, targets, rng)
    emb = np.asarray(engine.image_emb, dtype=np.float64)

    print(json.dumps({"setup": {"catalog": cat.name, "n_items": len(cat), "encoder": enc.name,
                                "arm": base.name, "n_targets": len(targets), "weights": weights,
                                "seed": args.seed}}, ensure_ascii=False), flush=True)

    rows: list[dict] = []
    for t in targets:
        row = items.loc[t]
        tid = str(row["item_id"])
        q = Query(qid=tid, gender=str(row["gender"]), color=str(row["color"]),
                  subcategory=str(row["subcategory"]), category=str(row["category"]),
                  occasion=str(row["occasion"]))
        grades = {i: g for i, g in q.grades(items).items() if i != tid}
        close = {i for i, g in grades.items() if g >= 2}
        c = HardConstraints(category=_slot([row["category"]]), gender=_slot([row["gender"]]))
        vague = f"{row['gender']} {row['category']}"
        for src in SOURCES:
            cpos = concepts[src][t]
            ce = emb[cpos]
            for w in weights:
                arm = replace(base, name=f"{base.name}_ci{w:g}", concept_image_weight=w)
                req = Engine02Request(
                    session_id=tid, retrieval_text=vague, constraints=c,
                    feedback=FeedbackState(excluded_item_ids=[tid],
                                           concept_image_embedding=[float(x) for x in ce]),
                    options=Engine02Options(top_k=10, n_candidates=100, explain_with_llm=False,
                                            counterfactual_check=False),
                )
                resp = engine.run(req, arm)
                ids = [it.item_id for it in resp.items]
                assert tid not in ids, "the target item must be excluded"
                pos5 = engine.catalog.positions(ids[:5])
                rows.append(dict(
                    concept_source=src, w=w, target=tid, concept_item=str(items.at[cpos, "item_id"]),
                    ndcg5=ndcg_at_k(ids, grades, 5), ndcg10=ndcg_at_k(ids, grades, 10),
                    hit5=hit_at_k(ids, close, 5),
                    cos_to_concept=float((emb[pos5] @ ce).mean()) if pos5 else float("nan"),
                ))
        if len(rows) % 300 == 0:
            print(f"{len(rows)} rows", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(out / "t12_concept_image.csv", index=False)

    summary = []
    for src, sub in df.groupby("concept_source"):
        piv = {m: sub.pivot(index="target", columns="w", values=m)
               for m in ("ndcg5", "ndcg10", "hit5", "cos_to_concept")}
        for w in weights:
            lo, hi = bootstrap_ci(piv["ndcg5"][w].to_numpy())
            summary.append({
                "concept_source": src, "w": w,
                "ndcg5": float(piv["ndcg5"][w].mean()), "ndcg5_ci95_lo": lo, "ndcg5_ci95_hi": hi,
                "ndcg5_delta_vs_w0": float((piv["ndcg5"][w] - piv["ndcg5"][weights[0]]).mean()),
                "p_ndcg5_vs_w0": paired_permutation_test(piv["ndcg5"][w].to_numpy(),
                                                         piv["ndcg5"][weights[0]].to_numpy()),
                "ndcg10": float(piv["ndcg10"][w].mean()),
                "hit5": float(piv["hit5"][w].mean()),
                "hit5_delta_vs_w0": float((piv["hit5"][w] - piv["hit5"][weights[0]]).mean()),
                "p_hit5_vs_w0": paired_permutation_test(piv["hit5"][w].to_numpy(),
                                                        piv["hit5"][weights[0]].to_numpy()),
                "cos_to_concept": float(piv["cos_to_concept"][w].mean()),
            })
    sdf = pd.DataFrame(summary)
    sdf.to_csv(out / "t12_summary.csv", index=False)
    (out / "t12_summary.json").write_text(json.dumps(
        {"setup": {"catalog": cat.name, "encoder": enc.name, "arm": base.name, "seed": args.seed,
                   "n_targets": len(targets), "weights": weights, "sources": list(SOURCES)},
         "summary": sdf.round(4).to_dict(orient="records")},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(sdf.round(4).to_string(index=False), flush=True)
    print(f"wrote {out}", flush=True)


if __name__ == "__main__":
    main()
