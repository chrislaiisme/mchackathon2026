"""Run the ENGINE 02 offline ablation (T1–T5) on a prepared catalog.

  python scripts/run_ablation.py --catalog data/catalog/kagl --encoder marqo-fashionSigLIP \
      --tasks t1,t2,t3,t4,t5 --out reports/ablation/kagl_marqo-fashionSigLIP

Use `--encoder hash` for a model-free smoke test. Works on CPU; `--device cuda` on a GPU box.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from engine02.catalog import Catalog  # noqa: E402
from engine02.compat import CategoryCooccurrence  # noqa: E402
from engine02.encoders import HashEncoder  # noqa: E402
from engine02.eval import tasks  # noqa: E402
from engine02.pipeline import Engine02  # noqa: E402

T1_ARMS = ["bm25", "dense", "hybrid_rrf", "hybrid_convex", "full", "hybrid_rrf_adaptive",
           "full_adaptive_bm25", "full_zclip3", "full_zclip3_nogate", "full_zclip3_ground",
           "full_zclip3_ground_both"]
T3_ARMS = ["full_concept_descriptor", "full_concept_random", "full", "full_concept_no_mask", "prd_original"]
T4_ARMS = ["full_reason_necessity", "full_reason_contrastive", "full", "prd_original"]
T5_ARMS = {
    "no_feedback": {"arm": "full", "use_choice": False, "use_critique": False},
    "critique_only": {"arm": "full_no_rocchio", "use_choice": False, "use_critique": True},
    "choice_only_rocchio": {"arm": "full", "use_choice": True, "use_critique": False},
    "critique+rocchio": {"arm": "full", "use_choice": True, "use_critique": True},
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default="data/catalog/kagl")
    ap.add_argument("--cooccurrence", default="data/catalog/polyvore/category_cooccurrence.json")
    ap.add_argument("--encoder", default="marqo-fashionSigLIP")
    ap.add_argument("--device", default="auto")
    ap.add_argument("--tasks", default="t1,t2,t3,t4,t5")
    ap.add_argument("--n-queries", type=int, default=60)
    ap.add_argument("--n-targets", type=int, default=100)
    ap.add_argument("--reranker", default=None, help="e.g. Qwen3-VL-Reranker-2B (adds full_cross_reranker to T1)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    out = Path(args.out or f"reports/ablation/{Path(args.catalog).name}_{args.encoder}")
    out.mkdir(parents=True, exist_ok=True)
    cat = Catalog.load(ROOT / args.catalog)
    cooc_path = ROOT / args.cooccurrence
    cooc = CategoryCooccurrence.load(cooc_path) if cooc_path.exists() else None

    t0 = time.perf_counter()
    if args.encoder == "hash":
        enc = HashEncoder(dim=256, captions={Path(p).name: t for p, t in zip(cat.items["image_path"], cat.texts())})
    else:
        from engine02.models import TorchEncoder

        enc = TorchEncoder(args.encoder, device=args.device)
    reranker = None
    if args.reranker:
        from engine02.models import CrossEncoderReranker

        reranker = CrossEncoderReranker(args.reranker, cat, device=args.device)
    engine = Engine02(cat, enc, cooccurrence=cooc, cross_reranker=reranker)
    setup = {"reranker": args.reranker, "encoder": enc.name, "catalog": str(args.catalog), "n_items": len(cat),
             "setup_s": round(time.perf_counter() - t0, 1)}
    print(json.dumps(setup), flush=True)

    queries = tasks.make_queries(cat.items, n=args.n_queries)
    summary: dict = {"setup": setup, "n_queries": len(queries)}
    todo = set(args.tasks.split(","))

    t1_arms = T1_ARMS + (["full_cross_reranker"] if reranker else [])
    t3_arms = T3_ARMS + (["full_concept_vlm", "full_concept_hybrid"] if any(cat.root.glob("vlm_attributes_*.parquet")) else [])
    if "t1" in todo:
        df = tasks.t1_retrieval(engine, queries, t1_arms)
        df.to_csv(out / "t1_retrieval.csv", index=False)
        s = pd.concat([tasks.summarize_paired(df, m, "dense") for m in ("ndcg10", "ndcg5", "mrr_exact")])
        s.to_csv(out / "t1_summary.csv", index=False)
        summary["t1"] = s.round(4).to_dict(orient="records")
        summary["latency_ms_mean"] = df.groupby("arm")["latency_ms"].mean().round(1).to_dict()
        print("t1 done", flush=True)
    if "t2" in todo:
        df = tasks.t2_constraints(engine, queries)
        df.to_csv(out / "t2_constraints.csv", index=False)
        summary["t2"] = {
            "satisfaction_mean": float(df["satisfaction"].mean()),
            "relaxed_rate": float((df["relaxed"] != "").mean()),
            "median_pool": float(df["n_after_filter"].median()),
        }
        print("t2 done", flush=True)
    if "t3" in todo:
        df = tasks.t3_concepts(engine, t3_arms)
        df.to_csv(out / "t3_concepts.csv", index=False)
        summary["t3"] = df.round(4).to_dict(orient="records")
        print("t3 done", flush=True)
    if "t4" in todo:
        df = tasks.t4_faithfulness(engine, queries[:40], T4_ARMS)
        df.to_csv(out / "t4_faithfulness.csv", index=False)
        agg = df.groupby("arm").agg(
            coverage=("has_reason", "mean"), n_cited=("n_cited", "mean"),
            comprehensive=("comprehensive", "mean"), rand_comprehensive=("rand_comprehensive", "mean"),
            sufficient=("sufficient", "mean"), rand_sufficient=("rand_sufficient", "mean"),
        )
        agg.to_csv(out / "t4_summary.csv")
        summary["t4"] = agg.round(4).reset_index().to_dict(orient="records")
        print("t4 done", flush=True)
    if "t5" in todo:
        df = tasks.t5_feedback(engine, T5_ARMS, n_targets=args.n_targets)
        df.to_csv(out / "t5_feedback.csv", index=False)
        sr = df.groupby(["arm", "round"])["success"].mean().unstack()
        sr.to_csv(out / "t5_summary.csv")
        final = df[df["round"] == df["round"].max()].pivot(index="target", columns="arm", values="success").astype(float)
        from engine02.eval.metrics import paired_permutation_test

        summary["t5"] = {
            "SR_at_t": sr.round(4).to_dict(orient="index"),
            "p_final_vs_no_feedback": {a: paired_permutation_test(final[a].to_numpy(), final["no_feedback"].to_numpy())
                                       for a in final.columns if a != "no_feedback"},
        }
        print("t5 done", flush=True)

    if "t6" in todo:
        df = tasks.t6_need_tradeoff(engine, queries)
        df.to_csv(out / "t6_need_tradeoff.csv", index=False)
        agg = df.groupby("gamma")[["ndcg5", "need_alignment", "changed"]].mean()
        agg.to_csv(out / "t6_summary.csv")
        summary["t6"] = agg.round(4).reset_index().to_dict(orient="records")
        print("t6 done", flush=True)

    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"wrote {out}", flush=True)


if __name__ == "__main__":
    main()
