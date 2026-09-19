"""T11 — what the trend-keyword term actually does to the ranking.

  python scripts/eval_trends.py --catalog data/catalog/kagl_polyvore --encoder marqo-fashionSigLIP \
      --out reports/agents/audit/trends_kagl_polyvore

The PRD asks for a small trend bonus (§6.6) and `ArmConfig` has carried `use_trend=True`,
`w_trend=0.2` from the start — but nothing ever called `Engine02.set_trends`, so the term was
never present in any measured arm. Before switching it on we have to know the price.

Design
------
* Base arm: the serving default (`--arm full_zclip3`); only `w_trend` changes, so the comparison
  is paired per query and every other term is identical.
* Keyword sources: the shipped hand-maintained list (`manual`), the catalog-derived
  `curated_lift` list, and a **random-token control** drawn from the catalog vocabulary with a
  matched document-frequency profile. The control is the point: a "trend" list of random words
  would move the ranking just as much if the term were only adding noise (the same logic as the
  random-descriptor control for c(i,d) in T3).
* Metrics per query: NDCG@5/@10 against the attribute ground truth (T1's grades — the trend term
  is *not* part of that ground truth, so any NDCG change is a cost, not a gain), the share of the
  top-5 that changed versus w_trend=0, the share of cards that cite the trend term as a reason,
  and the mean trend-BM25 z of the top-5 (did the term actually buy trend alignment?).
* Statistics: paired permutation test (10,000 flips) and bootstrap 95% CI over queries, vs the
  same queries at w_trend=0. Seeds fixed.

Ground-truth caveat: NDCG grades come from catalog metadata, and "trend alignment" is measured
with our own trend list — it is circular in the same way T6's need alignment is, and can only
show that the term moves the ranking, never that the result is more fashionable.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from engine02.catalog import Catalog  # noqa: E402
from engine02.config import ARMS  # noqa: E402
from engine02.contracts import Engine02Options, Engine02Request  # noqa: E402
from engine02.encoders import HashEncoder  # noqa: E402
from engine02.eval import tasks  # noqa: E402
from engine02.eval.metrics import bootstrap_ci, ndcg_at_k, paired_permutation_test  # noqa: E402
from engine02.pipeline import Engine02  # noqa: E402
from engine02.sparse import tokenize  # noqa: E402
from engine02.trends import (  # noqa: E402
    GENERIC,
    TrendClippedEngine02,
    TrendKeywords,
    TrendTerm,
    attach_trends,
    derive_trends,
    load_trends,
    trend_coverage,
)


def random_control(engine, reference: TrendKeywords, seed: int = 0) -> TrendKeywords:
    """Random catalog tokens with a document-frequency profile matched to `reference`."""
    rng = np.random.default_rng(seed)
    texts = engine.catalog.texts()
    df: dict[str, int] = {}
    for t in texts:
        for w in set(tokenize(t)):
            if len(w) > 2 and not w.isdigit() and w not in GENERIC:
                df[w] = df.get(w, 0) + 1
    vocab = sorted(df)
    if not vocab:
        return TrendKeywords(terms=[], source="random_words")
    targets = [t.df if t.df else max(1, len(texts) // 200) for t in reference.terms]
    arr = np.array([df[w] for w in vocab], dtype=np.float64)
    chosen: list[str] = []
    for tgt in targets:
        # nearest document frequency, sampled among the 20 closest so the list is not deterministic
        order = np.argsort(np.abs(arr - tgt))
        pool = [vocab[i] for i in order[:20] if vocab[i] not in chosen]
        if pool:
            chosen.append(str(rng.choice(pool)))
    return TrendKeywords(terms=[TrendTerm(term=w, score=float(len(chosen) - i), df=df[w])
                                for i, w in enumerate(chosen)],
                         source="random_words", notes=["對照組：從商品庫詞彙隨機抽、文件頻率對齊"])


def sources(engine, catalog: Catalog, top_n: int, seed: int) -> dict[str, TrendKeywords]:
    out: dict[str, TrendKeywords] = {"manual": load_trends()}
    try:
        out["curated_lift"] = derive_trends(catalog.items, "curated_lift", catalog=catalog.name, top_n=top_n)
    except ValueError as e:
        print(json.dumps({"curated_lift_unavailable": str(e)}), flush=True)
    out["random_words"] = random_control(engine, out.get("curated_lift", out["manual"]), seed=seed)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default="data/catalog/kagl_polyvore")
    ap.add_argument("--cooccurrence", default="data/catalog/polyvore/category_cooccurrence.json")
    ap.add_argument("--encoder", default="marqo-fashionSigLIP")
    ap.add_argument("--device", default="auto")
    ap.add_argument("--arm", default="full_zclip3")
    ap.add_argument("--weights", default="0,0.1,0.2,0.5")
    ap.add_argument("--n-queries", type=int, default=100)
    ap.add_argument("--top-n", type=int, default=30, help="keywords installed per source")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--cache-dir", default=None)
    ap.add_argument("--clip-trend", action="store_true",
                    help="also clip the trend z at arm.z_clip (the pipeline clips dense/bm25 but "
                         "not trend; see engine02.trends.TrendClippedEngine02)")
    ap.add_argument("--out", default="reports/agents/audit/trends")
    args = ap.parse_args()

    out = Path(args.out if Path(args.out).is_absolute() else ROOT / args.out)
    out.mkdir(parents=True, exist_ok=True)
    cat = Catalog.load(ROOT / args.catalog)
    if args.encoder == "hash":
        enc = HashEncoder(dim=256, captions={Path(p).name: t for p, t in zip(cat.items["image_path"], cat.texts())})
    else:
        from engine02.models import TorchEncoder

        enc = TorchEncoder(args.encoder, device=args.device)
    from engine02.compat import CategoryCooccurrence

    cooc_path = ROOT / args.cooccurrence
    cls = TrendClippedEngine02 if args.clip_trend else Engine02
    engine = cls(cat, enc, cache_dir=args.cache_dir,
                 cooccurrence=CategoryCooccurrence.load(cooc_path) if cooc_path.exists() else None)
    base = ARMS[args.arm]
    weights = [float(w) for w in args.weights.split(",")]
    queries = tasks.make_queries(cat.items, n=args.n_queries, seed=args.seed)
    keyword_sets = sources(engine, cat, args.top_n, args.seed)

    meta = {"catalog": cat.name, "n_items": len(cat), "encoder": enc.name, "arm": base.name,
            "n_queries": len(queries), "weights": weights, "seed": args.seed,
            "clip_trend": bool(args.clip_trend), "z_clip": base.z_clip,
            "sources": {k: {"source": v.source, "keywords": v.keywords(args.top_n), "notes": v.notes}
                        for k, v in keyword_sets.items()}}
    print(json.dumps({"setup": {k: v for k, v in meta.items() if k != "sources"}}, ensure_ascii=False), flush=True)

    rows: list[dict] = []
    coverage: dict[str, dict] = {}
    for src, tk in keyword_sets.items():
        words = attach_trends(engine, tk, top_n=args.top_n)
        coverage[src] = trend_coverage(engine, words)
        wordset = set(words)
        trend_all = engine.bm25.scores(" ".join(words)) if words else np.zeros(len(cat))
        tmean, tstd = float(trend_all.mean()), float(trend_all.std() or 1.0)
        for q in queries:
            grades = q.grades(cat.items)
            overlap = len(set(tokenize(q.text(False))) & wordset)
            top0: list[str] | None = None
            for w in weights:
                arm = replace(base, name=f"{base.name}_trend{w:g}", w_trend=w, use_trend=True)
                req = Engine02Request(
                    session_id=q.qid, retrieval_text=q.text(False),
                    options=Engine02Options(top_k=10, n_candidates=100, explain_with_llm=False,
                                            counterfactual_check=False),
                )
                resp = engine.run(req, arm)
                ids = [it.item_id for it in resp.items]
                if top0 is None:
                    top0 = ids[:5]
                pos = engine.catalog.positions(ids[:5])
                cited = np.mean([any(cb.group == "trend" and cb.cited for cb in it.contributions)
                                 for it in resp.items[:5]]) if resp.items else float("nan")
                rows.append(dict(
                    source=src, w_trend=w, qid=q.qid, query_overlap=overlap,
                    ndcg5=ndcg_at_k(ids, grades, 5), ndcg10=ndcg_at_k(ids, grades, 10),
                    changed_vs_w0=len(set(ids[:5]) - set(top0)) / max(1, len(top0)),
                    trend_cited_share=float(cited),
                    trend_z_top5=float(((trend_all[pos] - tmean) / tstd).mean()) if pos else float("nan"),
                ))
        print(f"{src} done", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(out / "t11_trends.csv", index=False)

    summary = []
    for src, sub in df.groupby("source"):
        piv = {m: sub.pivot(index="qid", columns="w_trend", values=m) for m in
               ("ndcg5", "ndcg10", "changed_vs_w0", "trend_cited_share", "trend_z_top5")}
        for w in weights:
            lo, hi = bootstrap_ci(piv["ndcg5"][w].to_numpy())
            summary.append({
                "source": src, "w_trend": w,
                "ndcg5": float(piv["ndcg5"][w].mean()), "ndcg5_ci95_lo": lo, "ndcg5_ci95_hi": hi,
                "ndcg5_delta_vs_w0": float((piv["ndcg5"][w] - piv["ndcg5"][weights[0]]).mean()),
                "p_ndcg5_vs_w0": paired_permutation_test(piv["ndcg5"][w].to_numpy(),
                                                         piv["ndcg5"][weights[0]].to_numpy()),
                "ndcg10": float(piv["ndcg10"][w].mean()),
                "top5_changed": float(piv["changed_vs_w0"][w].mean()),
                "trend_cited_share": float(piv["trend_cited_share"][w].mean()),
                "trend_z_top5": float(piv["trend_z_top5"][w].mean()),
                "p_trend_z_vs_w0": paired_permutation_test(piv["trend_z_top5"][w].to_numpy(),
                                                           piv["trend_z_top5"][weights[0]].to_numpy()),
            })
    sdf = pd.DataFrame(summary)
    sdf.to_csv(out / "t11_summary.csv", index=False)
    (out / "t11_summary.json").write_text(json.dumps(
        {"setup": meta, "coverage": coverage, "queries_with_keyword_overlap":
            float((df.groupby(["source", "qid"])["query_overlap"].first() > 0).mean()),
         "summary": sdf.round(4).to_dict(orient="records")},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(sdf.round(4).to_string(index=False), flush=True)
    print(f"wrote {out}", flush=True)


if __name__ == "__main__":
    main()
