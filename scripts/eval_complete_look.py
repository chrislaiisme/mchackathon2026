"""Complete-the-look on real Polyvore outfits (engine02/complete_look.py).

Ground truth: an outfit a Polyvore user actually assembled. For every outfit with ≥3 apparel items
one apparel item is held out; the remaining apparel items are the anchors.

(1) Category selection: is the held-out item's coarse category among the top-2 complementary categories
    predicted from the anchors' categories (NPMI from outfits *excluding all question outfits*)?
    Baselines: category popularity (same exclusion) and uniform random.
(2) Item ranking: candidates = held-out item + 99 random items of the same coarse category from other
    outfits. Recall@1/5/10, MRR (ties → expected rank). Methods: random, similarity (Marqo-FashionSigLIP),
    OutfitTransformer compatibility (ot), ot + w·similarity (w chosen on a dev split), OT complementary head (ot_cir).

Caveats: OutfitTransformer was trained on Polyvore Outfits (Vasileva et al. 2018); this catalog is the
Maryland Polyvore scrape (Han et al. 2017) — same site, possibly overlapping outfits/images, so OT numbers
may be optimistic. Random negatives from the same coarse category are easier than real alternatives.

  python scripts/eval_complete_look.py --catalog data/catalog/polyvore_big --n-dev 150 --n-test 500 --out reports/agents/slate/complete_look
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
import pandas as pd  # noqa: E402

from engine02.catalog import Catalog  # noqa: E402
from engine02.complete_look import APPAREL, CompleteTheLook, cooccurrence_from_outfits, outfits_of, rank_categories  # noqa: E402
from engine02.eval.metrics import bootstrap_ci, paired_permutation_test  # noqa: E402
from engine02.fusion import zscore  # noqa: E402

SIM_WEIGHTS = (0.25, 0.5, 1.0, 2.0)


def expected_rank(s: np.ndarray, gold: int) -> float:
    g = s[gold]
    return 1.0 + float((s > g).sum()) + float((s == g).sum() - 1) / 2.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default="data/catalog/polyvore_big")
    ap.add_argument("--emb", default=None, help="Marqo-FashionSigLIP image embeddings .npy (default <catalog>/index)")
    ap.add_argument("--n-dev", type=int, default=150)
    ap.add_argument("--n-test", type=int, default=500)
    ap.add_argument("--n-neg", type=int, default=99)
    ap.add_argument("--device", default="auto")
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    from engine02.complete_look import FastOutfitTransformer

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cat = Catalog.load(ROOT / args.catalog)
    items = cat.items
    cats = items["category"].tolist()
    emb = np.load(args.emb or (cat.root / "index" / "img_marqo-fashionSigLIP.npy"))
    assert emb.shape[0] == len(items)

    rng = random.Random(args.seed)
    outfits = outfits_of(items)
    by_cat: dict[str, list[int]] = {}
    for p, c in enumerate(cats):
        by_cat.setdefault(c, []).append(p)
    questions = []
    for oid in sorted(outfits):
        members = outfits[oid]
        app = [p for p in members if cats[p] in APPAREL]
        if len(app) < 3:
            continue
        hidden = rng.choice(app)
        pool = [p for p in by_cat[cats[hidden]] if p not in set(members)]
        if len(pool) < args.n_neg:
            continue
        cands = [hidden] + rng.sample(pool, args.n_neg)
        rng.shuffle(cands)
        questions.append(dict(oid=oid, anchors=[p for p in app if p != hidden], hidden=hidden, cands=cands,
                              gold=cands.index(hidden)))
    n_eligible = len(questions)
    rng.shuffle(questions)
    questions = questions[: args.n_dev + args.n_test]
    for i, q in enumerate(questions):
        q["split"] = "dev" if i < args.n_dev else "test"

    # (1) category selection — NPMI / popularity without any question outfit
    held = {q["oid"] for q in questions}
    cooc = cooccurrence_from_outfits(items, exclude_outfits=held)
    pop: dict[str, int] = {}
    for oid, members in outfits.items():
        if oid not in held:
            for p in members:
                pop[cats[p]] = pop.get(cats[p], 0) + 1

    import torch

    t0 = time.perf_counter()
    ot = FastOutfitTransformer(cat, device=args.device, heads=("compatibility", "complementary"), batch_size=args.batch,
                               cache_file=out / "ot_item_emb.npz")
    load_s = time.perf_counter() - t0
    need = sorted({p for q in questions for p in q["anchors"] + q["cands"]})
    t0 = time.perf_counter()
    ot.ensure_embeddings(need)
    ot.save_cache()
    emb_s = time.perf_counter() - t0
    ctl = CompleteTheLook(cat, emb, cooc, ot=ot, seed=args.seed)

    rows = []
    t_ot = t_cir = 0.0
    for qi, q in enumerate(questions):
        anchors, cands, gold = q["anchors"], q["cands"], q["gold"]
        anchor_cats = [cats[a] for a in anchors]
        hc = cats[q["hidden"]]
        ranked = [c for c, _ in rank_categories(anchor_cats, cooc)]
        own = set(anchor_cats)
        pop_rank = [c for c in sorted(APPAREL, key=lambda c: -pop.get(c, 0)) if c not in own]
        n_allowed = len([c for c in APPAREL if c not in own])
        row = dict(oid=q["oid"], split=q["split"], hidden_category=hc, n_anchors=len(anchors),
                   hidden_cat_in_anchor_cats=hc in own,
                   cat_top2_npmi=float(hc in ranked[:2]), cat_top1_npmi=float(hc in ranked[:1]),
                   cat_top2_popularity=float(hc in pop_rank[:2]),
                   cat_top2_random=(min(2, n_allowed) / n_allowed if (n_allowed and hc not in own) else 0.0))
        rng_np = np.random.default_rng([args.seed, qi])
        scores = {"random": rng_np.random(len(cands))}
        scores["similarity"] = (emb[cands] @ emb[anchors].T).mean(axis=1)
        t = time.perf_counter()
        scores["ot"] = ot.compatibility(anchors, cands)
        t_ot += time.perf_counter() - t
        t = time.perf_counter()
        scores["ot_cir"] = ot.complementary(anchors, cands, hc)
        t_cir += time.perf_counter() - t
        # reuse the OT scores above instead of recomputing them inside ctl.score_items (checked below)
        for w in SIM_WEIGHTS:
            scores[f"ot_sim_w{w:g}"] = zscore(scores["ot"]) + w * zscore(scores["similarity"])
        for name, s in scores.items():
            r = expected_rank(np.asarray(s, dtype=np.float64), gold)
            row[f"rank_{name}"] = r
        rows.append(row)
    df = pd.DataFrame(rows)

    # sanity: score_items path == inline path on one question
    q0 = questions[0]
    ctl.sim_weight = 0.5
    s_api = ctl.score_items(q0["anchors"], q0["cands"], "ot_sim")[0]
    s_inline = zscore(ot.compatibility(q0["anchors"], q0["cands"])) + 0.5 * zscore(
        (emb[q0["cands"]] @ emb[q0["anchors"]].T).mean(axis=1))
    api_ok = bool(np.allclose(s_api, s_inline, atol=1e-5))
    # sanity: precomputed-embedding path == the repo's image path (engine02/compat_ot.py style) on 16 candidates
    m = ot.models["compatibility"]
    with torch.inference_mode():
        a_items = [ot._raw_item(p) for p in q0["anchors"]]
        qs = [ot.CQuery(outfit=a_items + [ot._raw_item(p)]) for p in q0["cands"][:16]]
        s_img = m.predict_score(qs).float().cpu().numpy().reshape(-1)
    precompute_max_abs_diff = float(np.abs(s_img - ot.compatibility(q0["anchors"], q0["cands"][:16])).max())

    dev = df[df.split == "dev"]
    best_w = max(SIM_WEIGHTS, key=lambda w: float((1.0 / dev[f"rank_ot_sim_w{w:g}"]).mean()))
    df["rank_ot_sim"] = df[f"rank_ot_sim_w{best_w:g}"]
    df.to_csv(out / "per_question.csv", index=False)

    test = df[df.split == "test"]
    methods = ["random", "similarity", "ot", "ot_sim", "ot_cir"] + [f"ot_sim_w{w:g}" for w in SIM_WEIGHTS]
    per = {}
    for m in methods:
        r = test[f"rank_{m}"].to_numpy()
        per[m] = {"rr": 1.0 / r, **{f"r@{k}": (r <= k).astype(float) for k in (1, 5, 10)}}
    res = dict(n_eligible_outfits=n_eligible, n_dev=int((df.split == "dev").sum()), n_test=len(test),
               candidates=args.n_neg + 1, chosen_sim_weight_on_dev=best_w, score_items_consistency=api_ok,
               precompute_vs_image_path_max_abs_diff=precompute_max_abs_diff,
               shared_item_encoder=ot.shared_item_encoder,
               ot_load_s=round(load_s, 1), ot_item_embedding_s=round(emb_s, 1), n_items_embedded=len(need),
               ot_ms_per_question_100cands=round(t_ot / len(df) * 1000, 2),
               cir_ms_per_question_100cands=round(t_cir / len(df) * 1000, 2),
               peak_vram_gb=round(torch.cuda.max_memory_allocated() / 1e9, 2) if torch.cuda.is_available() else None,
               item_ranking={}, paired_tests={}, category_selection={})
    for m in methods:
        d = {}
        for key, x in per[m].items():
            lo, hi = bootstrap_ci(x)
            d[key] = [round(float(x.mean()), 4), round(lo, 4), round(hi, 4)]
        res["item_ranking"][m] = d  # [mean, ci_lo, ci_hi]
    for a, b in [("ot", "similarity"), ("ot_sim", "ot"), ("ot_sim", "similarity"), ("ot_cir", "ot"),
                 ("ot_cir", "similarity"), ("similarity", "random"), ("ot", "random")]:
        t = {}
        for key in ("rr", "r@1", "r@5", "r@10"):
            diff = per[a][key] - per[b][key]
            lo, hi = bootstrap_ci(diff)
            t[key] = dict(diff=round(float(diff.mean()), 4), ci95=[round(lo, 4), round(hi, 4)],
                          p=round(paired_permutation_test(per[a][key], per[b][key]), 4))
        res["paired_tests"][f"{a}_vs_{b}"] = t
    for key in ("cat_top2_npmi", "cat_top1_npmi", "cat_top2_popularity", "cat_top2_random"):
        x = df[key].to_numpy()
        lo, hi = bootstrap_ci(x)
        res["category_selection"][key] = [round(float(x.mean()), 4), round(lo, 4), round(hi, 4)]
    res["category_selection"]["n_questions"] = len(df)
    res["category_selection"]["hidden_category_same_as_an_anchor"] = round(float(df.hidden_cat_in_anchor_cats.mean()), 4)
    x, y = df.cat_top2_npmi.to_numpy(), df.cat_top2_popularity.to_numpy()
    res["category_selection"]["p_npmi_vs_popularity"] = round(paired_permutation_test(x, y), 4)
    x2 = df[~df.hidden_cat_in_anchor_cats]
    res["category_selection"]["top2_npmi_when_category_not_already_in_anchors"] = round(float(x2.cat_top2_npmi.mean()), 4)
    res["category_selection"]["top2_popularity_when_category_not_already_in_anchors"] = round(
        float(x2.cat_top2_popularity.mean()), 4)
    res["category_selection"]["by_hidden_category_top2_npmi"] = {
        c: [round(float(g.cat_top2_npmi.mean()), 3), int(len(g))] for c, g in df.groupby("hidden_category")}
    (out / "results.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
