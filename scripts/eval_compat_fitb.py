"""Fill-in-the-blank on real Polyvore outfits: which of 4 same-category candidates completes the outfit?

Compares (a) category co-occurrence NPMI — constant within a category, so it can only tie (25%),
(b) mean image-embedding similarity to the anchors (a *similarity*, not compatibility, baseline),
(c) OutfitTransformer compatibility.

  python scripts/eval_compat_fitb.py --catalog data/catalog/polyvore_big --n 200 --device auto
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from engine02.catalog import Catalog  # noqa: E402
from engine02.compat import CategoryCooccurrence, compat_scores  # noqa: E402
from engine02.eval.metrics import bootstrap_ci  # noqa: E402

APPAREL = {"top", "bottom", "outerwear", "dress", "shoes", "bag"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default="data/catalog/polyvore_big")
    ap.add_argument("--cooccurrence", default="data/catalog/polyvore/category_cooccurrence.json")
    ap.add_argument("--encoder", default="marqo-fashionSigLIP")
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--device", default="auto")
    ap.add_argument("--out", default="reports/server/compat_fitb.json")
    args = ap.parse_args()

    from engine02.compat_ot import OutfitTransformerCompat
    from engine02.encoders import cached_image_embeddings
    from engine02.models import TorchEncoder

    cat = Catalog.load(ROOT / args.catalog)
    items = cat.items
    rng = random.Random(0)
    outfits: dict[str, list[int]] = {}
    for pos, ids in enumerate(items["outfit_ids"]):
        for o in (ids if ids is not None else []):
            outfits.setdefault(str(o), []).append(pos)
    by_cat: dict[str, list[int]] = {}
    for pos, c in enumerate(items["category"]):
        by_cat.setdefault(c, []).append(pos)

    questions = []
    for oid, members in outfits.items():
        app = [p for p in members if items.at[p, "category"] in APPAREL]
        if len(app) < 3:
            continue
        hidden = rng.choice(app)
        c = items.at[hidden, "category"]
        pool = [p for p in by_cat[c] if p not in members]
        if len(pool) < 3:
            continue
        cands = [hidden] + rng.sample(pool, 3)
        rng.shuffle(cands)
        questions.append((oid, [p for p in app if p != hidden], cands, cands.index(hidden)))
    rng.shuffle(questions)
    questions = questions[: args.n]

    cooc = CategoryCooccurrence.load(ROOT / args.cooccurrence)
    enc = TorchEncoder(args.encoder, device=args.device)
    emb = cached_image_embeddings(enc, cat.image_paths(), cat.root / "index" / f"img_{enc.name}.npy")
    t0 = time.perf_counter()
    ot = OutfitTransformerCompat(cat, device=args.device)
    load_s = time.perf_counter() - t0

    hits = {"npmi": [], "embedding_similarity": [], "outfit_transformer": []}
    t_ot = 0.0
    for oid, anchors, cands, gold in questions:
        s_npmi = compat_scores([items.at[p, "category"] for p in cands], [items.at[a, "category"] for a in anchors], cooc)
        s_sim = (emb[cands] @ emb[anchors].T).mean(axis=1)
        t = time.perf_counter()
        s_ot = ot.score(anchors, cands)
        t_ot += time.perf_counter() - t
        for name, s in (("npmi", s_npmi), ("embedding_similarity", s_sim), ("outfit_transformer", s_ot)):
            best = np.flatnonzero(s == s.max())
            hits[name].append(1.0 / len(best) if gold in best else 0.0)  # ties split credit
    res = {"n_questions": len(questions), "candidates": 4, "chance": 0.25, "ot_load_s": round(load_s, 1),
           "ot_ms_per_candidate": round(t_ot / max(1, 4 * len(questions)) * 1000, 1)}
    for name, h in hits.items():
        lo, hi = bootstrap_ci(np.array(h))
        res[name] = {"accuracy": round(float(np.mean(h)), 4), "ci95": [round(lo, 4), round(hi, 4)]}
    Path(ROOT / args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(ROOT / args.out).write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
