"""T19: when should the lexical side be switched off? (the paraphrase collapse, diagnosed)

T1 says adding BM25 to a paraphrased query is not a small cost, it is a collapse: pure dense scores
0.366 NDCG@5 while every hybrid arm lands between 0.067 and 0.150. We already ship a gate
(`bm25_adaptive`: scale w_bm25 by the share of query tokens present in the catalog, and drop to
dense-only below `bm25_min_coverage`), and it does not fix it (0.110). This measures **why**, and
which signal a gate should actually use.

  python scripts/eval_bm25_gate.py --catalog data/catalog/kagl_polyvore_filled \
      --encoder marqo-fashionSigLIP --device cuda --n-queries 60

For every query, in both wordings, it records:
  coverage        the share of query tokens that exist in the catalog (what we gate on today)
  content_cov     the same, ignoring tokens that appear in more than `--common` of all documents
                  ("men", "shirt" are present in a paraphrase too, so they keep the gate open)
  bm25_max_z      the top BM25 score in units of that query's own score distribution
  gold_in_bm25    whether any grade-3 item is in the BM25 top-50 at all
  ndcg dense / hybrid / full, so each signal can be checked against the actual damage

Then it asks the only question that matters: **is there a threshold on any of these that separates
"BM25 helps" from "BM25 hurts"?** If yes, that is the gate. If no, the honest answer is that the
lexical side cannot be rescued at query time and the contract with ENGINE 01 is the fix.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--catalog", default="data/catalog/kagl")
    ap.add_argument("--encoder", default="hash")
    ap.add_argument("--device", default="auto")
    ap.add_argument("--n-queries", type=int, default=60)
    ap.add_argument("--common", type=float, default=0.10,
                    help="a token in more than this share of documents is not content")
    ap.add_argument("--out", default="reports/ablation")
    a = ap.parse_args()

    from engine02.catalog import Catalog
    from engine02.contracts import Engine02Options, Engine02Request
    from engine02.eval.metrics import ndcg_at_k
    from engine02.eval.tasks import make_queries
    from engine02.pipeline import Engine02
    from engine02.sparse import tokenize

    cat = Catalog.load(ROOT / a.catalog)
    if a.encoder == "hash":
        from engine02.encoders import HashEncoder

        enc = HashEncoder(dim=256, captions={Path(p).name: t for p, t in zip(cat.items["image_path"], cat.texts())})
    else:
        from engine02.models import TorchEncoder

        enc = TorchEncoder(a.encoder, device=a.device)
    eng = Engine02(cat, enc, cache_dir=ROOT / a.catalog / "index")
    bm = eng.bm25
    n_docs = bm.corpus_size
    # document frequency per token, so we can tell content words from ones every product has
    df = {t: len(idx) for t, (idx, _) in bm.postings.items()}

    queries = make_queries(cat.items, n=a.n_queries)
    rows = []
    for q in queries:
        grades = q.grades(cat.items)
        for paraphrase in (False, True):
            text = q.text(paraphrase)
            toks = tokenize(text)
            in_vocab = [t for t in toks if t in bm.vocab]
            content = [t for t in toks if df.get(t, 0) <= a.common * n_docs]
            content_hit = [t for t in content if t in bm.vocab]
            scores = bm.scores(text)
            top = np.argsort(-scores)[:50]
            sd = float(scores.std()) or 1e-9
            gold = {i for i, g in grades.items() if g >= 3}
            ids = cat.column("item_id")
            row = dict(qid=q.qid, wording="paraphrase" if paraphrase else "lexical",
                       n_tokens=len(toks),
                       coverage=round(len(in_vocab) / max(1, len(toks)), 4),
                       content_cov=round(len(content_hit) / max(1, len(content)), 4) if content else 0.0,
                       n_content=len(content),
                       bm25_max=round(float(scores.max()), 4),
                       bm25_max_z=round(float((scores.max() - scores.mean()) / sd), 3),
                       gold_in_bm25_top50=int(any(str(ids[p]) in gold for p in top)))
            for arm in ("dense", "hybrid_rrf", "full_zclip3", "full_adaptive_bm25"):
                req = Engine02Request(session_id=q.qid, retrieval_text=text,
                                      options=Engine02Options(top_k=10, n_candidates=100,
                                                              explain_with_llm=False,
                                                              counterfactual_check=False))
                resp = eng.run(req, arm)
                row[f"ndcg5_{arm}"] = ndcg_at_k([it.item_id for it in resp.items], grades, 5)
            row["hybrid_cost"] = row["ndcg5_dense"] - row["ndcg5_full_zclip3"]
            rows.append(row)
            print(f"{row['qid']:>6} {row['wording']:<10} cov {row['coverage']:.2f} "
                  f"content {row['content_cov']:.2f} bm25z {row['bm25_max_z']:.1f} "
                  f"gold@bm25 {row['gold_in_bm25_top50']} cost {row['hybrid_cost']:+.3f}", flush=True)

    df_rows = pd.DataFrame(rows)
    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    tag = f"bm25_gate_{Path(a.catalog).name}_{enc.name}"
    df_rows.to_csv(out / f"{tag}.csv", index=False)

    print("\n=== per wording (mean)")
    cols = ["coverage", "content_cov", "bm25_max_z", "gold_in_bm25_top50",
            "ndcg5_dense", "ndcg5_hybrid_rrf", "ndcg5_full_zclip3", "ndcg5_full_adaptive_bm25",
            "hybrid_cost"]
    print(df_rows.groupby("wording")[cols].mean().round(3).to_string())

    # Can any single signal separate "the lexical side helps" from "it hurts"?
    # A threshold chosen on the rows it is scored on is not a result, so split by QUERY — both
    # wordings of a query go to the same side, otherwise the split leaks.
    helps = df_rows["hybrid_cost"] < 0  # dense worse than hybrid → BM25 helped
    qids = sorted(df_rows["qid"].unique())
    rng = np.random.default_rng(SEED)
    rng.shuffle(qids)
    dev_ids = set(qids[: len(qids) // 2])
    dev = df_rows[df_rows["qid"].isin(dev_ids)]
    test = df_rows[~df_rows["qid"].isin(dev_ids)]
    print(f"\n=== which signal predicts that adding BM25 hurts?  (dev {dev['qid'].nunique()} queries, "
          f"test {test['qid'].nunique()})")

    def gated_mean(frame, sig, thr):
        return float(np.where(frame[sig] >= thr, frame["ndcg5_full_zclip3"], frame["ndcg5_dense"]).mean())

    report = {}
    for sig in ("coverage", "content_cov", "bm25_max_z", "gold_in_bm25_top50"):
        cands = list(np.quantile(dev[sig], np.linspace(0.05, 0.95, 19)))
        if sig in ("coverage", "content_cov"):
            cands.append(0.999)  # "every query token exists in the catalog" — the natural rule
        best = max(cands, key=lambda t: gated_mean(dev, sig, t))
        report[sig] = dict(threshold_from_dev=round(float(best), 4),
                           dev_ndcg5=round(gated_mean(dev, sig, best), 4),
                           test_ndcg5=round(gated_mean(test, sig, best), 4),
                           corr_with_hurt=round(float(np.corrcoef(df_rows[sig], (~helps).astype(float))[0, 1]), 3))
        print(f"  {sig:<20} thr {best:.3f} (dev) → dev {report[sig]['dev_ndcg5']:.4f} "
              f"test {report[sig]['test_ndcg5']:.4f}  (corr with 'BM25 hurts' {report[sig]['corr_with_hurt']:+.2f})")

    def baselines(frame, label):
        return dict(split=label,
                    always_hybrid=round(float(frame["ndcg5_full_zclip3"].mean()), 4),
                    always_dense=round(float(frame["ndcg5_dense"].mean()), 4),
                    shipped_gate=round(float(frame["ndcg5_full_adaptive_bm25"].mean()), 4),
                    oracle=round(float(np.maximum(frame["ndcg5_full_zclip3"], frame["ndcg5_dense"]).mean()), 4))

    always = [baselines(df_rows, "all"), baselines(dev, "dev"), baselines(test, "test")]
    for b in always:
        print(f"  [{b['split']:>4}] always hybrid {b['always_hybrid']:.4f} | always dense {b['always_dense']:.4f} "
              f"| shipped adaptive gate {b['shipped_gate']:.4f} | oracle {b['oracle']:.4f}")
    (out / f"{tag}.json").write_text(json.dumps(
        {"setup": dict(catalog=a.catalog, encoder=enc.name, queries=len(queries), common=a.common),
         "per_wording": df_rows.groupby("wording")[cols].mean().round(4).to_dict(),
         "gates": report, "baselines": always}, indent=1), encoding="utf-8")
    print(f"\nwrote {out / (tag + '.json')}")
    print("\nRead it as: a gate is only worth shipping if its gated NDCG@5 beats BOTH 'always hybrid'\n"
          "and 'always dense'. The oracle row is the ceiling any per-query gate could reach.")


if __name__ == "__main__":
    main()
