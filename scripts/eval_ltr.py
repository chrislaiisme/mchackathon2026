"""T10: learned (non-negative, additive) ranking weights vs hand-set ones — 5-fold CV by query.

Stages (run in order; `all` = capture → ranx → learn → integrate):

  PY=/tmp/neil/mchackathon2026/.venv/bin/python
  $PY scripts/eval_ltr.py --stage capture   --catalog data/catalog/kagl --out $OUT/kagl --cache-dir $A/index_kagl
  PYTHONPATH=$A/pylib $PY scripts/eval_ltr.py --stage ranx --out $OUT/kagl     # separate process: ranx pulls its own numpy
  $PY scripts/eval_ltr.py --stage learn     --out $OUT/kagl
  $PY scripts/eval_ltr.py --stage integrate --catalog data/catalog/kagl --out $OUT/kagl --cache-dir $A/index_kagl

Ground truth = catalog metadata grades from engine02.eval.tasks.Query.grades (3: subcategory+color+gender+
occasion, 2: subcategory+color, 1: subcategory). It is a proxy and partly lexical (see the report).
"""

from __future__ import annotations

import argparse
import gzip
import json
import pickle
import random
import sys
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FOLDS = 5


def fold_of(groups: list[str], seed: int = 0) -> dict[str, int]:
    g = sorted(set(groups))
    random.Random(seed).shuffle(g)
    return {x: i % FOLDS for i, x in enumerate(g)}


# ---------------------------------------------------------------------------
def stage_capture(args) -> None:
    import numpy as np

    from engine02.catalog import Catalog
    from engine02.eval import tasks
    from engine02.ltr import CapturingEngine02, capture_query
    from engine02.contracts import Engine02Options, Engine02Request

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cat = Catalog.load(ROOT / args.catalog)
    if args.encoder == "hash":
        from engine02.encoders import HashEncoder

        enc = HashEncoder(dim=256, captions={Path(p).name: t for p, t in zip(cat.items["image_path"], cat.texts())})
    else:
        from engine02.models import TorchEncoder

        enc = TorchEncoder(args.encoder, device=args.device)
    t0 = time.perf_counter()
    eng = CapturingEngine02(cat, enc, cache_dir=args.cache_dir)
    # make_queries only shuffles the (gender, color, subcategory, category, occasion) groups by seed, so several
    # seeds give the same pool in another order; union them and deduplicate by qid (= group index).
    seen, queries = set(), []
    for seed in range(args.n_seeds):
        for q in tasks.make_queries(cat.items, n=10**6, seed=seed):
            if q.qid not in seen:
                seen.add(q.qid)
                queries.append(q)
    random.Random(0).shuffle(queries)
    queries = queries[: args.n_queries]
    print(json.dumps({"n_items": len(cat), "n_queries": len(queries), "setup_s": round(time.perf_counter() - t0, 1)}),
          flush=True)
    items = cat.items
    qfs = []
    val_arms = ["hybrid_rrf", "hybrid_convex", "dense", "bm25", "full_adaptive_bm25"]
    for n, q in enumerate(queries):
        grades = q.grades(items)
        for para in (False, True):
            wording = "paraphrase" if para else "lexical"
            qf = capture_query(eng, f"{q.qid}|{wording}", q.qid, wording, q.text(para), grades, depth=args.depth)
            if n < args.n_validate:
                for arm in val_arms:
                    req = Engine02Request(session_id=q.qid, retrieval_text=q.text(para),
                                          options=Engine02Options(top_k=10, n_candidates=100, explain_with_llm=False,
                                                                  counterfactual_check=False))
                    qf.engine_top[arm] = [it.item_id for it in eng.run(req, arm).items]
            qfs.append(qf)
        if n % 50 == 0:
            print(f"captured {n}/{len(queries)} {time.perf_counter() - t0:.0f}s", flush=True)
    with gzip.open(out / "features.pkl.gz", "wb") as f:
        pickle.dump(qfs, f)
    # ranx input: each retriever contributes its own top-100 (raw scores), grades as qrels
    folds = fold_of([qf.group for qf in qfs])
    runs = {"dense": {}, "bm25": {}}
    qrels, meta = {}, {}
    for qf in qfs:
        for name, raw, rank in (("dense", qf.dense_raw, qf.dense_rank), ("bm25", qf.bm25_raw, qf.bm25_rank)):
            sel = np.flatnonzero(rank <= 100)
            runs[name][qf.qid] = {qf.item_ids[i]: float(raw[i]) for i in sel}
        qrels[qf.qid] = {i: int(g) for i, g in zip(qf.item_ids, qf.grades) if g > 0}
        if not qrels[qf.qid]:  # ranx rejects empty qrels; U missed every relevant item
            qrels[qf.qid] = {"__none__": 1}
        meta[qf.qid] = {"fold": folds[qf.group], "coverage": qf.coverage, "wording": qf.wording}
    (out / "ranx_input.json").write_text(json.dumps({"runs": runs, "qrels": qrels, "meta": meta}), encoding="utf-8")
    cov = {w: [qf.coverage for qf in qfs if qf.wording == w] for w in ("lexical", "paraphrase")}
    info = {"catalog": args.catalog, "encoder": enc.name, "n_items": len(cat), "n_queries": len(queries),
            "n_records": len(qfs), "depth": args.depth, "capture_s": round(time.perf_counter() - t0, 1),
            "coverage": {w: {"mean": float(np.mean(v)), "share_ge_0.5": float(np.mean(np.array(v) >= 0.5)),
                             "min": float(np.min(v)), "max": float(np.max(v))} for w, v in cov.items()},
            "mean_U": float(np.mean([len(qf.item_ids) for qf in qfs]))}
    (out / "capture_info.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    print(json.dumps(info), flush=True)


# ---------------------------------------------------------------------------
def stage_ranx(args) -> None:
    from ranx import Qrels, Run, fuse, optimize_fusion

    out = Path(args.out)
    d = json.loads((out / "ranx_input.json").read_text(encoding="utf-8"))
    meta = d["meta"]
    res = {"rankings": {}, "params": {}}

    def sub(dct, keys):
        return {k: dct[k] for k in keys}

    def runs_for(keys):
        return [Run(sub(d["runs"]["dense"], keys), name="dense"), Run(sub(d["runs"]["bm25"], keys), name="bm25")]

    def put(name, fused, keys):
        dd = fused.to_dict()
        for k in keys:
            s = dd.get(k, {})
            res["rankings"].setdefault(name, {})[k] = [i for i, _ in sorted(s.items(), key=lambda x: -x[1])[:10]]

    metric = "ndcg_burges@5"  # gains 2^g − 1, as engine02.eval.metrics.ndcg_at_k
    for fold in range(FOLDS):
        train = [k for k, m in meta.items() if m["fold"] != fold]
        test = [k for k, m in meta.items() if m["fold"] == fold]
        for method, norm in (("sum", "min-max"), ("mnz", "min-max")):  # unsupervised
            put(f"ranx_comb{method}", fuse(runs=runs_for(test), norm=norm, method=method), test)
        for method, norm in (("wsum", "min-max"), ("rrf", "min-max")):
            p = optimize_fusion(qrels=Qrels(sub(d["qrels"], train)), runs=runs_for(train), norm=norm, method=method,
                                metric=metric)
            res["params"].setdefault(f"ranx_{method}", []).append({k: [float(x) for x in v] if isinstance(v, (tuple, list))
                                                                  else float(v) for k, v in p.items()})
            put(f"ranx_{method}", fuse(runs=runs_for(test), norm=norm, method=method, params=p), test)
            if method == "wsum":
                wsum_global = p
        # type-aware wsum: separate weights for covered / uncovered queries; θ chosen on the training folds
        from ranx import evaluate

        best = None
        for th in (0.5, 0.75, 1.0):
            params, fused_train = {}, {}
            for grp in ("covered", "uncovered"):
                tr = [k for k in train if (meta[k]["coverage"] >= th) == (grp == "covered")]
                if not tr:
                    continue
                params[grp] = optimize_fusion(qrels=Qrels(sub(d["qrels"], tr)), runs=runs_for(tr), norm="min-max",
                                              method="wsum", metric=metric)
                fused_train.update(fuse(runs=runs_for(tr), norm="min-max", method="wsum", params=params[grp]).to_dict())
            v = evaluate(Qrels(sub(d["qrels"], train)), Run(fused_train), metric)
            if best is None or v > best[0] + 1e-9:
                best = (v, th, params)
        _, th, params = best
        for grp in ("covered", "uncovered"):
            p = params.get(grp, wsum_global)
            res["params"].setdefault(f"ranx_wsum_typeaware:{grp}", []).append(
                dict({k: [float(x) for x in v] for k, v in p.items()}, threshold=th))
            te = [k for k in test if (meta[k]["coverage"] >= th) == (grp == "covered")]
            if te:
                put("ranx_wsum_typeaware", fuse(runs=runs_for(te), norm="min-max", method="wsum", params=p), te)
        print(f"ranx fold {fold} done", flush=True)
    (out / "ranx_output.json").write_text(json.dumps(res), encoding="utf-8")


# ---------------------------------------------------------------------------
def _holm(pvals: dict[str, float]) -> dict[str, float]:
    items = sorted(pvals.items(), key=lambda x: x[1])
    m, out, run = len(items), {}, 0.0
    for i, (k, p) in enumerate(items):
        run = max(run, min(1.0, (m - i) * p))
        out[k] = run
    return out


def _metrics_for(qf, ids):
    from engine02.eval.metrics import dcg, mrr

    grades = {i: float(g) for i, g in zip(qf.item_ids, qf.grades) if g > 0}

    # same as ndcg_at_k, but the ideal DCG is catalog-wide (U may miss relevant items)
    def nd(k):
        return dcg([grades.get(i, 0.0) for i in ids[:k]], k) / qf.idcg[k] if qf.idcg[k] > 0 else 0.0

    rel3 = {i for i, g in grades.items() if g >= 3}
    return dict(ndcg5=nd(5), ndcg10=nd(10), mrr_exact=mrr(ids[:10], rel3))


def stage_learn(args) -> None:
    import numpy as np
    import pandas as pd

    from engine02.eval.metrics import bootstrap_ci, paired_permutation_test
    from engine02.ltr import (
        CORE_FEATURES,
        EXT_FEATURES,
        LinearRanker,
        TypeAwareRanker,
        learn_grid_convex,
        learn_grid_full,
        learn_grid_rrf,
        learn_linear,
        learn_type_aware,
    )

    out = Path(args.out)
    with gzip.open(out / "features.pkl.gz", "rb") as f:
        qfs = pickle.load(f)
    folds = fold_of([qf.group for qf in qfs])

    # 1) the offline simulation must reproduce the engine
    sims = {"full": LinearRanker(), "hybrid_rrf": LinearRanker(weights=()),
            "hybrid_convex": LinearRanker(weights=(), fusion="convex"), "dense": LinearRanker(weights=(), fusion="dense"),
            "bm25": LinearRanker(weights=(), fusion="bm25"), "full_adaptive_bm25": LinearRanker(adaptive_bm25=True)}
    # untrained routing control: hand-set full weights when every query token is in the catalog vocabulary,
    # otherwise dense only. Separates "learning the weights" from "routing by coverage".
    route = {"full_route_dense": TypeAwareRanker(covered=LinearRanker(),
                                                 uncovered=LinearRanker(weights=(("dense", 1.5),), fusion="dense"),
                                                 threshold=1.0)}
    val = {}
    for arm, r in sims.items():
        rows = [(r.rank(qf, 10) == qf.engine_top[arm]) for qf in qfs if arm in qf.engine_top]
        val[arm] = {"n": len(rows), "exact_top10_match": float(np.mean(rows)) if rows else None}
    print("validation", json.dumps(val), flush=True)

    learners = {
        "grid_rrf_k": lambda tr: learn_grid_rrf(tr),
        "grid_convex_alpha": lambda tr: learn_grid_convex(tr),
        "grid_full": lambda tr: learn_grid_full(tr),
        "grid_full_typeaware": lambda tr: learn_type_aware(tr, learn_grid_full),
        "ca_core": lambda tr: learn_linear(tr, "ca", CORE_FEATURES),
        "ca_ext": lambda tr: learn_linear(tr, "ca", EXT_FEATURES),
        "ranknet_core": lambda tr: learn_linear(tr, "pairwise", CORE_FEATURES),
        "ranknet_ext": lambda tr: learn_linear(tr, "pairwise", EXT_FEATURES),
        "ca_core_typeaware": lambda tr: learn_type_aware(tr, learn_linear, method="ca", features=CORE_FEATURES),
        "ca_ext_typeaware": lambda tr: learn_type_aware(tr, learn_linear, method="ca", features=EXT_FEATURES),
        "ranknet_core_typeaware": lambda tr: learn_type_aware(tr, learn_linear, method="pairwise",
                                                              features=CORE_FEATURES),
    }
    rows, wrows = [], []
    for fold in range(FOLDS):
        tr = [qf for qf in qfs if folds[qf.group] != fold]
        te = [qf for qf in qfs if folds[qf.group] == fold]
        models = dict(sims, **route)
        t0 = time.perf_counter()
        for name, fn in learners.items():
            models[name] = fn(tr)
            parts = ([("covered", models[name].covered), ("uncovered", models[name].uncovered)]
                     if isinstance(models[name], TypeAwareRanker) else [("all", models[name])])
            for grp, lr in parts:
                wrows.append(dict(fold=fold, method=name, group=grp, fusion=lr.fusion, rrf_k=lr.rrf_k,
                                  threshold=getattr(models[name], "threshold", None),
                                  convex_alpha=lr.convex_alpha, **{f"w_{k}": v for k, v in lr.weights},
                                  nonneg=all(v >= 0 for _, v in lr.weights)))
        print(f"fold {fold} trained in {time.perf_counter() - t0:.0f}s", flush=True)
        for qf in te:
            for name, m in models.items():
                rows.append(dict(qid=qf.group, wording=qf.wording, fold=fold, method=name, coverage=qf.coverage,
                                 **_metrics_for(qf, m.rank(qf, 10))))
    ranx_path = out / "ranx_output.json"
    if ranx_path.exists():
        rx = json.loads(ranx_path.read_text(encoding="utf-8"))
        by_key = {qf.qid: qf for qf in qfs}
        for name, ranks in rx["rankings"].items():
            for key, ids in ranks.items():
                qf = by_key[key]
                rows.append(dict(qid=qf.group, wording=qf.wording, fold=folds[qf.group], method=name,
                                 coverage=qf.coverage, **_metrics_for(qf, ids)))
        for name, plist in rx["params"].items():
            for fold, p in enumerate(plist):
                wrows.append(dict(fold=fold, method=name.split(":")[0], group=(name.split(":") + ["all"])[1],
                                  fusion="ranx", **{f"ranx_{k}": v for k, v in p.items()}))
    df = pd.DataFrame(rows)
    df.to_csv(out / "t10_per_query.csv", index=False)
    wdf = pd.DataFrame(wrows)
    wdf.to_csv(out / "t10_weights_per_fold.csv", index=False)

    summ = []
    for metric in ("ndcg5", "ndcg10", "mrr_exact"):
        for wording in ("lexical", "paraphrase", "all"):
            sub = df if wording == "all" else df[df.wording == wording]
            piv = sub.pivot_table(index=["qid", "wording"], columns="method", values=metric)
            piv = piv.dropna(axis=1)
            for base in ("full", "hybrid_rrf"):
                ps = {m: paired_permutation_test(piv[m].to_numpy(), piv[base].to_numpy()) for m in piv.columns if m != base}
                holm = _holm(ps)
                for m in piv.columns:
                    if base == "full":
                        lo, hi = bootstrap_ci(piv[m].to_numpy())
                        summ.append(dict(metric=metric, wording=wording, method=m, mean=piv[m].mean(), ci95_lo=lo,
                                         ci95_hi=hi, n=len(piv)))
                    rec = next(r for r in summ if r["metric"] == metric and r["wording"] == wording and r["method"] == m)
                    rec[f"diff_vs_{base}"] = piv[m].mean() - piv[base].mean()
                    rec[f"p_vs_{base}"] = ps.get(m, float("nan"))
                    rec[f"p_holm_vs_{base}"] = holm.get(m, float("nan"))
    s = pd.DataFrame(summ)
    s.to_csv(out / "t10_summary.csv", index=False)
    wcols = [c for c in wdf.columns if c.startswith("w_") or c in ("rrf_k", "convex_alpha", "threshold")]
    stab = wdf.groupby(["method", "group", "fusion"], dropna=False)[wcols].agg(["mean", "std"]) if wcols else None
    if stab is not None:
        stab.to_csv(out / "t10_weight_stability.csv")
    (out / "t10_validation.json").write_text(json.dumps(val, indent=2), encoding="utf-8")
    print(s[s.metric == "ndcg5"].round(4).to_string(), flush=True)


# ---------------------------------------------------------------------------
def stage_final(args) -> None:
    """Fit the chosen learners on ALL queries of this catalog → learned-weights JSON (the integration
    artefact), plus transfer to another catalog's features if --transfer is given."""
    import numpy as np
    import pandas as pd

    from engine02.ltr import CORE_FEATURES, learn_grid_full, learn_linear, learn_type_aware, ranker_to_json

    out = Path(args.out)
    with gzip.open(out / "features.pkl.gz", "rb") as f:
        qfs = pickle.load(f)
    fits = {
        "grid_full_typeaware": learn_type_aware(qfs, learn_grid_full),
        "ca_core_typeaware": learn_type_aware(qfs, learn_linear, method="ca", features=CORE_FEATURES),
        "grid_full": learn_grid_full(qfs),
    }
    for name, r in fits.items():
        js = ranker_to_json(r, {"method": name, "catalog": args.catalog, "n_records": len(qfs),
                                "trained_on": "all queries (after 5-fold CV)", "features": list(CORE_FEATURES)})
        (out / f"learned_weights_{name}.json").write_text(json.dumps(js, indent=2), encoding="utf-8")
        print(name, json.dumps(js["groups"]), flush=True)
    if args.transfer:
        with gzip.open(Path(args.transfer) / "features.pkl.gz", "rb") as f:
            other = pickle.load(f)
        from engine02.ltr import LinearRanker

        rows = []
        models = dict(fits, full=LinearRanker(), hybrid_rrf=LinearRanker(weights=()),
                      dense=LinearRanker(weights=(), fusion="dense"))
        for qf in other:
            for name, m in models.items():
                rows.append(dict(qid=qf.group, wording=qf.wording, method=name, **_metrics_for(qf, m.rank(qf, 10))))
        df = pd.DataFrame(rows)
        from engine02.eval.metrics import paired_permutation_test

        res = []
        for w, sub in df.groupby("wording"):
            piv = sub.pivot(index="qid", columns="method", values="ndcg5")
            for m in piv.columns:
                res.append(dict(wording=w, method=m, ndcg5=piv[m].mean(),
                                p_vs_full=paired_permutation_test(piv[m].to_numpy(), piv["full"].to_numpy())))
        t = pd.DataFrame(res)
        t.to_csv(out / f"transfer_to_{Path(args.transfer).name}.csv", index=False)
        print(t.round(4).to_string(), flush=True)
        del np


def stage_integrate(args) -> None:
    """Run the real LearnedWeightsEngine: explanation integrity (contributions sum to score, non-negative
    retrieval weights, share of cards with ≥1 cited reason) with random hidden needs, vs the hand-set full arm.
    Also checks that the engine's NDCG@5 without needs equals the simulated one."""
    import numpy as np
    import pandas as pd

    from engine02.catalog import Catalog
    from engine02.contracts import Engine02Options, Engine02Request
    from engine02.eval import tasks
    from engine02.eval.metrics import ndcg_at_k, paired_permutation_test
    from engine02.ltr import LearnedWeightsEngine
    from engine02.models import TorchEncoder

    out = Path(args.out)
    js = json.loads((out / f"learned_weights_{args.method}.json").read_text(encoding="utf-8"))
    cat = Catalog.load(ROOT / args.catalog)
    eng = LearnedWeightsEngine(cat, TorchEncoder(args.encoder, device=args.device), cache_dir=args.cache_dir,
                               learned=js)
    queries = tasks.make_queries(cat.items, n=args.n_integrate, seed=123)
    rng = random.Random(0)
    rows = []
    for q in queries:
        grades = q.grades(cat.items)
        needs = tasks.random_needs(rng, eng.kansei.need_ids)
        for para in (False, True):
            for with_needs in (False, True):
                for arm in ("full", "full_ltr"):
                    req = Engine02Request(session_id=q.qid, retrieval_text=q.text(para), needs=needs if with_needs else [],
                                          options=Engine02Options(top_k=5, n_candidates=100, explain_with_llm=False,
                                                                  counterfactual_check=False))
                    resp = eng.run(req, "full") if arm == "full_ltr" else super(LearnedWeightsEngine, eng).run(req, "full")
                    ids = [it.item_id for it in resp.items]
                    sums_ok = all(abs(sum(c.contribution for c in it.contributions) - it.score) < 1e-8 for it in resp.items)
                    nonneg = all(c.weight >= 0 for it in resp.items for c in it.contributions
                                 if c.group in ("dense", "bm25"))
                    rows.append(dict(qid=q.qid, wording="paraphrase" if para else "lexical", needs=with_needs, arm=arm,
                                     ndcg5=ndcg_at_k(ids, grades, 5), sums_ok=sums_ok, nonneg=nonneg,
                                     reason_coverage=float(np.mean([any(c.cited for c in it.contributions)
                                                                    for it in resp.items])),
                                     n_cited=float(np.mean([sum(c.cited for c in it.contributions) for it in resp.items])),
                                     design_share=float(np.mean([sum(abs(c.contribution) for c in it.contributions
                                                                     if c.group == "design") /
                                                                 max(1e-12, sum(abs(c.contribution) for c in it.contributions))
                                                                 for it in resp.items]))))
    df = pd.DataFrame(rows)
    df.to_csv(out / f"integrate_{args.method}.csv", index=False)
    agg = df.groupby(["wording", "needs", "arm"])[["ndcg5", "sums_ok", "nonneg", "reason_coverage", "n_cited",
                                                   "design_share"]].mean()
    print(agg.round(4).to_string(), flush=True)
    tests = {}
    for (w, n), sub in df.groupby(["wording", "needs"]):
        piv = sub.pivot(index="qid", columns="arm", values="ndcg5")
        tests[f"{w}|needs={n}"] = {"ltr": piv["full_ltr"].mean(), "full": piv["full"].mean(),
                                   "p": paired_permutation_test(piv["full_ltr"].to_numpy(), piv["full"].to_numpy())}
    agg.to_csv(out / f"integrate_{args.method}_summary.csv")
    (out / f"integrate_{args.method}_tests.json").write_text(json.dumps(tests, indent=2), encoding="utf-8")
    print(json.dumps(tests, indent=2), flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True, choices=["capture", "ranx", "learn", "final", "integrate"])
    ap.add_argument("--catalog", default="data/catalog/kagl")
    ap.add_argument("--encoder", default="marqo-fashionSigLIP")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--cache-dir", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--n-queries", type=int, default=400)
    ap.add_argument("--n-seeds", type=int, default=3)
    ap.add_argument("--n-validate", type=int, default=40)
    ap.add_argument("--depth", type=int, default=500)
    ap.add_argument("--transfer", default=None, help="features dir of another catalog (stage final)")
    ap.add_argument("--method", default="grid_full_typeaware")
    ap.add_argument("--n-integrate", type=int, default=60)
    args = ap.parse_args()
    {"capture": stage_capture, "ranx": stage_ranx, "learn": stage_learn, "final": stage_final,
     "integrate": stage_integrate}[args.stage](args)


if __name__ == "__main__":
    main()
