"""T8 composed retrieval / critiquing on a reference item ("this one, but navy blue / more formal").

Triplets come from KAGL metadata (no LLM, no human labels):
  reference r (apparel, gender+subcategory+color+occasion known)
  variant color    : to_value = a colour from a different colour family, other attrs (occasion) kept
  variant occasion : Casual→Formal/Sports, Formal→Casual, Sports→Casual, colour kept
  targets T        : items with r's gender + subcategory + other attribute and the new value (r excluded)
  graded NDCG      : 3 = T and same season, 2 = T, 1 = gender+subcategory+new value only
  hard targets     : top-N of T by image similarity to r measured with the *other* encoder
                     (avoids rewarding the method's own embedding space)

Methods (engine02/composed.py): critique_filter (current pipeline, arm `full`), text_rewrite (title / meta
template), image_plus_text (α sweep, target text = rewrite or modifier word), vector_arithmetic (λ sweep),
ref_plus_filter, image_plus_text_filter (α sweep), plus option 6 through the pipeline with BM25 on the
rewritten text (arm hybrid_rrf). α/λ picked on the dev half by mean NDCG@10 over both variants.

    python scripts/eval_composed.py --catalog data/catalog/kagl --encoder marqo-fashionSigLIP \
        --other-encoder fashion-clip --cache-dir /tmp/neil/agents/composed/index_kagl --out reports/composed/kagl_marqo
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine02.catalog import Catalog  # noqa: E402
from engine02.composed import (  # noqa: E402
    COLOR_FAMILY,
    ComposedEngine02,
    ComposedQuery,
    Critique,
    TemplateRewriter,
    direction_phrases,
    modifier_phrase,
)
from engine02.config import ARMS  # noqa: E402
from engine02.constraints import filter_with_relaxation  # noqa: E402
from engine02.contracts import Engine02Options, Engine02Request, HardConstraints, Slot, SlotState  # noqa: E402
from engine02.encoders import HashEncoder  # noqa: E402
from engine02.eval.metrics import bootstrap_ci, ndcg_at_k, paired_permutation_test  # noqa: E402

APPAREL = {"top", "bottom", "outerwear", "dress", "shoes", "bag"}
OCC_MOVES = {"Casual": ["Formal", "Sports"], "Formal": ["Casual"], "Sports": ["Casual"]}
# image-image cosines (~0.5-0.9) dwarf text-image cosines (~0.05-0.3) (modality gap), so α is dense near 0
ALPHAS = [0.0, 0.01, 0.02, 0.03, 0.05, 0.075, 0.1, 0.15, 0.2, 0.3, 0.5, 0.7, 1.0]
LAMBDAS = [0.0, 0.5, 1.0, 2.0, 4.0, 8.0, 12.0, 16.0, 24.0, 32.0, 64.0]
MIN_RESULTS = ARMS["full"].min_results  # same relaxation ladder threshold as the pipeline


def _slot(v):
    return Slot(state=SlotState.VALUE, values=[v])


def build_triplets(items: pd.DataFrame, n: int, seed: int) -> list[dict]:
    df = items[items["category"].isin(APPAREL)].dropna(subset=["gender", "subcategory", "color", "occasion"])
    cnt = df.groupby(["gender", "subcategory", "occasion", "color"]).size()
    rng = random.Random(seed)
    out: list[dict] = []
    for variant in ("color", "occasion"):
        idx = list(df.index)
        rng.shuffle(idx)
        got = 0
        for pos in idx:
            r = df.loc[pos]
            key = (r.gender, r.subcategory)
            if variant == "color":
                if r.color not in COLOR_FAMILY:
                    continue
                sub = cnt.get(key + (r.occasion,))
                if sub is None:
                    continue
                opts = [c for c, k in sub.items() if c in COLOR_FAMILY and COLOR_FAMILY[c] != COLOR_FAMILY[r.color] and k >= 1]
                if not opts:
                    continue
                to = rng.choice(sorted(opts))
                crit = dict(attribute="color", to_value=to, from_value=r.color, direction=None)
                other = "occasion"
            else:
                moves = [o for o in OCC_MOVES.get(r.occasion, []) if cnt.get(key + (o, r.color), 0) >= 1]
                if not moves:
                    continue
                to = rng.choice(moves)
                direction = {"Formal": "more_formal", "Casual": "more_casual", "Sports": "sportier"}[to]
                crit = dict(attribute="occasion", to_value=to, from_value=r.occasion, direction=direction)
                other = "color"
            out.append(dict(tid=f"{variant[0]}{pos}", variant=variant, ref_pos=int(pos), other=other, **crit,
                            split="dev" if got % 2 == 0 else "test"))
            got += 1
            if got >= n:
                break
    return out


def target_sets(cols: dict[str, np.ndarray], t: dict, sim_other: np.ndarray, hard_tops: list[int]):
    p = t["ref_pos"]
    base = (cols["gender"] == cols["gender"][p]) & (cols["subcategory"] == cols["subcategory"][p])
    newv = cols[t["attribute"]] == t["to_value"]
    keep = cols[t["other"]] == cols[t["other"]][p]
    rel = base & newv & keep
    rel[p] = False
    g = np.where(rel & (cols["season"] == cols["season"][p]), 3, np.where(rel, 2, np.where(base & newv, 1, 0)))
    g[p] = 0
    rel_pos = np.flatnonzero(rel)
    grades = {int(i): float(g[i]) for i in np.flatnonzero(g > 0)}
    hard = {}
    order = rel_pos[np.argsort(-sim_other[rel_pos], kind="stable")]
    for h in hard_tops:
        hard[h] = set(int(i) for i in order[:h])
    return set(int(i) for i in rel_pos), grades, hard


def metrics_row(top: list[int], cols, t, rel, grades, hard, sim_other) -> dict:
    p = t["ref_pos"]
    top5 = top[:5]
    ids = [str(i) for i in top]
    row = dict(
        hit5=float(any(i in rel for i in top[:5])), hit10=float(any(i in rel for i in top[:10])),
        recall10=len(set(top[:10]) & rel) / len(rel) if rel else 0.0,
        ndcg10=ndcg_at_k(ids, {str(k): v for k, v in grades.items()}, 10),
        preservation5=float(np.mean([cols[t["other"]][i] == cols[t["other"]][p] for i in top5])) if top5 else 0.0,
        change5=float(np.mean([cols[t["attribute"]][i] == t["to_value"] for i in top5])) if top5 else 0.0,
        both5=float(np.mean([i in rel for i in top5])) if top5 else 0.0,
        # visual preservation measured with the other encoder (continuous, independent of metadata)
        vis_sim5=float(np.mean(sim_other[top5])) if top5 else 0.0,
        top10=" ".join(str(cols["item_id"][i]) for i in top[:10]),
    )
    for h, hs in hard.items():
        row[f"hard{h}_hit10"] = float(any(i in hs for i in top[:10]))
        row[f"hard{h}_ndcg10"] = ndcg_at_k(ids, {str(k): 1.0 for k in hs}, 10)
    return row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default="data/catalog/kagl")
    ap.add_argument("--encoder", default="marqo-fashionSigLIP")
    ap.add_argument("--other-encoder", default="fashion-clip", help="defines 'visually similar' hard targets")
    ap.add_argument("--device", default="auto")
    ap.add_argument("--cache-dir", default=None)
    ap.add_argument("--n-per-variant", type=int, default=600)
    ap.add_argument("--hard-tops", default="50,5,1")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--latency-n", type=int, default=50)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    cat = Catalog.load(ROOT / args.catalog)
    out = Path(args.out or f"reports/composed/{cat.name}_{args.encoder}")
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    if args.encoder == "hash":
        enc = HashEncoder(dim=256, captions={Path(p).name: tx for p, tx in zip(cat.items["image_path"], cat.texts())})
    else:
        from engine02.models import TorchEncoder

        enc = TorchEncoder(args.encoder, device=args.device)
    engine = ComposedEngine02(cat, enc, cache_dir=args.cache_dir)
    other_file = cat.root / "index" / f"img_{args.other_encoder.replace('/', '__')}.npy"
    if other_file.exists() and np.load(other_file, mmap_mode="r").shape[0] == len(cat):
        other_emb, other_name = np.load(other_file), args.other_encoder
    else:
        other_emb, other_name = engine.image_emb, enc.name
        print(f"WARNING: {other_file} missing, hard targets use the same encoder", flush=True)
    setup = dict(catalog=cat.name, n_items=len(cat), encoder=enc.name, hard_target_encoder=other_name,
                 setup_s=round(time.perf_counter() - t0, 1), seed=args.seed)
    print(json.dumps(setup), flush=True)

    items = cat.items
    cols = {c: items[c].astype(object).where(items[c].notna(), None).to_numpy() for c in
            ("item_id", "gender", "subcategory", "color", "occasion", "season")}
    hard_tops = [int(h) for h in args.hard_tops.split(",")]
    trips = build_triplets(items, args.n_per_variant, args.seed)
    pd.DataFrame(trips).to_csv(out / "triplets.csv", index=False)
    print({v: sum(t["variant"] == v for t in trips) for v in ("color", "occasion")}, flush=True)

    comp_title = engine.composer(TemplateRewriter("title"))
    comp_meta = engine.composer(TemplateRewriter("meta"))
    comp_meta._memo = comp_title._memo  # shared text cache
    # pre-encode every text once
    texts = []
    for t in trips:
        row = items.iloc[t["ref_pos"]]
        c = Critique(t["attribute"], t["to_value"], t["from_value"], t["direction"])
        texts += [comp_title.rewriter.rewrite(row, c), comp_meta.rewriter.rewrite(row, c), modifier_phrase(c),
                  *direction_phrases(row, c)]
    comp_title.txt(texts)

    configs = [("text_rewrite", {}, comp_title), ("text_rewrite_meta", {}, comp_meta), ("ref_plus_filter", {}, comp_title)]
    configs += [(f"image_plus_text[a={a}]", dict(alpha=a), comp_title) for a in ALPHAS]
    configs += [(f"image_plus_text_mod[a={a}]", dict(alpha=a, text_source="modifier"), comp_title) for a in ALPHAS]
    configs += [(f"image_plus_text_meta[a={a}]", dict(alpha=a), comp_meta) for a in ALPHAS]
    configs += [(f"image_plus_text_filter[a={a}]", dict(alpha=a), comp_title) for a in ALPHAS]
    configs += [(f"vector_arithmetic[l={lam}]", dict(lam=lam), comp_title) for lam in LAMBDAS]

    rows = []
    for n, t in enumerate(trips):
        p = t["ref_pos"]
        sim_o = other_emb @ other_emb[p]
        rel, grades, hard = target_sets(cols, t, sim_o, hard_tops)
        base = HardConstraints(category=_slot(cols["subcategory"][p]), gender=_slot(cols["gender"][p]))
        filt = base.model_copy(deep=True)
        setattr(filt, t["attribute"], _slot(t["to_value"]))
        pool_base = np.flatnonzero(filter_with_relaxation(items, base, MIN_RESULTS, [p]).mask)
        fr = filter_with_relaxation(items, filt, MIN_RESULTS, [p])
        pool_filt = np.flatnonzero(fr.mask)
        crit = Critique(t["attribute"], t["to_value"], t["from_value"], t["direction"])
        common = dict(tid=t["tid"], variant=t["variant"], split=t["split"], n_targets=len(rel),
                      filter_relaxed=";".join(fr.relaxed))
        for name, kw, comp in configs:
            method = name.split("[")[0].replace("_mod", "").replace("_meta", "")
            cq: ComposedQuery = comp.compose(p, crit, f"{cols['gender'][p]} {cols['subcategory'][p]}", method, **kw)
            pool = pool_filt if cq.constraint_updates else pool_base
            s = engine.image_emb[pool] @ cq.query_embedding
            top = [int(i) for i in pool[np.argsort(-s, kind="stable")[:10]]]
            rows.append(dict(common, config=name, family=name.split("[")[0], **metrics_row(top, cols, t, rel, grades, hard, sim_o)))
        if n % 100 == 0:
            print(f"fast path {n}/{len(trips)}", flush=True)
    fast = pd.DataFrame(rows)

    # --- choose α/λ on dev (mean NDCG@10 pooled over both variants) ---
    dev = fast[fast["split"] == "dev"].groupby(["family", "config"])["ndcg10"].mean().reset_index()
    best = {f: g.sort_values("ndcg10", ascending=False).iloc[0]["config"] for f, g in dev.groupby("family")}
    # alternative selection that rewards "keep everything else": the single most visually similar target
    vis_key = f"hard{min(hard_tops)}_ndcg10"
    dev_v = fast[fast["split"] == "dev"].groupby(["family", "config"])[vis_key].mean().reset_index()
    best_vis = {f: g.sort_values(vis_key, ascending=False).iloc[0]["config"] for f, g in dev_v.groupby("family")}
    sweep = fast.groupby(["variant", "split", "family", "config"])[
        ["ndcg10", "hit10", "preservation5", "change5", "vis_sim5"] + [f"hard{h}_ndcg10" for h in hard_tops]].mean().reset_index()
    sweep.to_csv(out / "sweep.csv", index=False)
    print("best on dev:", best, "best_vis:", best_vis, flush=True)

    def param(cfg: str, key: str, default: float) -> float:
        return float(cfg.split(f"[{key}=")[1].rstrip("]")) if f"[{key}=" in cfg else default

    a_best = param(best["image_plus_text"], "a", 0.5)
    af_best = param(best["image_plus_text_filter"], "a", 0.5)

    # --- pipeline runs on the test half: current system + option 6 hybrids ---
    pipe_cfgs = [
        ("critique_filter", "critique_filter", {}, ARMS["full"]),
        ("text_rewrite+bm25_rrf", "text_rewrite", {}, ARMS["hybrid_rrf"]),
        (f"image_plus_text+bm25_rrf[a={a_best}]", "image_plus_text", dict(alpha=a_best), ARMS["hybrid_rrf"]),
        (f"image_plus_text_filter+bm25_rrf[a={af_best}]", "image_plus_text_filter", dict(alpha=af_best),
         ARMS["hybrid_rrf"]),
    ]
    for fam in ("image_plus_text", "image_plus_text_filter"):
        av = param(best_vis[fam], "a", 0.5)
        name = f"{fam}+bm25_rrf[a={av}]"
        if name not in [c[0] for c in pipe_cfgs]:
            pipe_cfgs.append((name, fam, dict(alpha=av), ARMS["hybrid_rrf"]))
    prow = []
    test = [t for t in trips if t["split"] == "test"]
    for n, t in enumerate(test):
        p = t["ref_pos"]
        sim_o = other_emb @ other_emb[p]
        rel, grades, hard = target_sets(cols, t, sim_o, hard_tops)
        base = HardConstraints(category=_slot(cols["subcategory"][p]), gender=_slot(cols["gender"][p]))
        crit = Critique(t["attribute"], t["to_value"], t["from_value"], t["direction"])
        bq = f"{cols['gender'][p]} {cols['subcategory'][p]}"
        req = Engine02Request(session_id=t["tid"], retrieval_text=bq, constraints=base,
                              options=Engine02Options(top_k=10, n_candidates=50, explain_with_llm=False,
                                                      counterfactual_check=False))
        for name, method, kw, arm in pipe_cfgs:
            cq = comp_title.compose(p, crit, bq, method, **kw)
            resp = engine.run_composed(req, cq, replace(arm, counterfactual=False))
            top = cat.positions([it.item_id for it in resp.items])
            prow.append(dict(tid=t["tid"], variant=t["variant"], split="test", n_targets=len(rel), config=name,
                             family=name.split("[")[0], pipeline_ms=sum(resp.timings_ms.values()),
                             filter_relaxed=";".join(resp.constraint_report.relaxed),
                             **metrics_row(top, cols, t, rel, grades, hard, sim_o)))
        if n % 100 == 0:
            print(f"pipeline {n}/{len(test)}", flush=True)
    pipe = pd.DataFrame(prow)

    # --- latency: compose (fresh text encoding, no memo) + filter + rank, single query ---
    lat = []
    for t in test[: args.latency_n]:
        p = t["ref_pos"]
        crit = Critique(t["attribute"], t["to_value"], t["from_value"], t["direction"])
        base = HardConstraints(category=_slot(cols["subcategory"][p]), gender=_slot(cols["gender"][p]))
        for method, kw in [("text_rewrite", {}), ("image_plus_text", dict(alpha=a_best)),
                           ("vector_arithmetic", dict(lam=param(best["vector_arithmetic"], "l", 1.0))),
                           ("ref_plus_filter", {}), ("image_plus_text_filter", dict(alpha=af_best))]:
            fresh = engine.composer()
            ts = time.perf_counter()
            cq = fresh.compose(p, crit, "", method, **kw)
            tc = time.perf_counter()
            c2 = base.model_copy(deep=True)
            for attr, vals in cq.constraint_updates.items():
                setattr(c2, attr, Slot(state=SlotState.VALUE, values=vals))
            pool = np.flatnonzero(filter_with_relaxation(items, c2, MIN_RESULTS, [p]).mask)
            s = engine.image_emb[pool] @ cq.query_embedding
            _ = pool[np.argsort(-s)[:10]]
            te = time.perf_counter()
            lat.append(dict(method=method, compose_ms=(tc - ts) * 1000, filter_rank_ms=(te - tc) * 1000,
                            total_ms=(te - ts) * 1000))
    latency = pd.DataFrame(lat).groupby("method").median().round(2)
    latency.loc["critique_filter(pipeline full)"] = [np.nan, np.nan, float(
        pipe[pipe["config"] == "critique_filter"]["pipeline_ms"].median())]
    for name in pipe["config"].unique():
        if name != "critique_filter":
            latency.loc[f"{name}(pipeline)"] = [np.nan, np.nan, float(pipe[pipe["config"] == name]["pipeline_ms"].median())]
    latency.to_csv(out / "latency.csv")

    # --- test summary with paired statistics ---
    chosen = ["text_rewrite", "text_rewrite_meta", "ref_plus_filter", best["image_plus_text"],
              best["image_plus_text_mod"], best["image_plus_text_meta"], best["image_plus_text_filter"],
              best["vector_arithmetic"]] + list(best_vis.values())
    chosen = list(dict.fromkeys(chosen))
    test_fast = fast[(fast["split"] == "test") & fast["config"].isin(chosen)]
    allt = pd.concat([test_fast, pipe.drop(columns=["pipeline_ms"])], ignore_index=True)
    allt.to_csv(out / "test_rows.csv", index=False)
    fast.to_csv(out / "fast_rows.csv.gz", index=False)
    mets = ["hit5", "hit10", "recall10", "ndcg10", "preservation5", "change5", "both5"]
    mets += ["vis_sim5"] + [f"hard{h}_{m}" for h in hard_tops for m in ("hit10", "ndcg10")]
    summ = []
    for variant, sub in list(allt.groupby("variant")) + [("all", allt)]:
        for m in mets:
            piv = sub.pivot(index="tid", columns="config", values=m)
            for cfg in piv.columns:
                x = piv[cfg].to_numpy()
                lo, hi = bootstrap_ci(x, n_boot=5000)
                summ.append(dict(
                    variant=variant, metric=m, config=cfg, mean=float(x.mean()), ci95_lo=lo, ci95_hi=hi, n=len(x),
                    p_vs_critique_filter=paired_permutation_test(x, piv["critique_filter"].to_numpy())
                    if cfg != "critique_filter" else np.nan,
                    p_vs_text_rewrite=paired_permutation_test(x, piv["text_rewrite"].to_numpy())
                    if cfg != "text_rewrite" else np.nan,
                ))
    summ = pd.DataFrame(summ)
    summ.to_csv(out / "summary.csv", index=False)
    tsz = fast[fast["config"] == "text_rewrite"][["variant", "n_targets"]]
    report = dict(setup, best_on_dev=best, best_on_dev_visual=best_vis, n_triplets=pd.DataFrame(trips).groupby(["variant", "split"]).size()
                  .reset_index().to_dict(orient="records"),
                  target_set_size=tsz.groupby("variant")["n_targets"].describe().round(1).to_dict(orient="index"),
                  critique_filter_relaxed_rate=float((pipe[pipe["config"] == "critique_filter"]["filter_relaxed"] != "")
                                                     .mean()),
                  latency_ms=latency.reset_index().to_dict(orient="records"))
    (out / "summary.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    piv = summ[summ["metric"].isin(["ndcg10", "hit10", "preservation5", "change5", "vis_sim5", "hard1_ndcg10"])]
    print(piv.pivot_table(index=["variant", "config"], columns="metric", values="mean").round(3).to_string())
    print(json.dumps(report, default=str)[:2000])


if __name__ == "__main__":
    main()
