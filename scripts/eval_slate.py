"""T9 slate diversification: relevance vs diversity trade-off of MMR / DPP / xQuAD (engine02/diversify.py).

Setup (same query family as T4/T6): queries from eval.tasks.make_queries, lexical wording, hard
category+gender filter, random need profile (3 needs) per query, arm "full". One pipeline call per
query returns the top-`depth` relevance candidates; every diversification config re-orders only those.

Metrics per query (k=5):
- ndcg5            attribute grades (subcategory+colour+gender+occasion = 3, subcat+colour = 2, subcat = 1)
- ild5             1 − mean pairwise image cosine (Marqo-FashionSigLIP embeddings — the same space MMR/DPP use,
                   so this is partly self-referential)
- n_subcat5 / n_color5  distinct metadata values (independent of the embeddings)
- neardup5         share of the 10 pairs with cosine > 0.95
- alpha_ndcg5      need-aspect coverage, α=0.5, intent-aware weights P(n); J(i,n)=1 iff P(i|n) ≥ 0.5.
                   Built from our own K table and c(i,d) → xQuAD optimises it directly (self-referential)
- rel_kept         mean min-max relevance of the slate relative to the relevance-only slate
- promoted         share of cards not in the relevance top-5 (cards that say「為了多樣性而納入」)

  python scripts/eval_slate.py --catalog data/catalog/kagl --n-queries 150 --out reports/agents/slate/kagl
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
from engine02.contracts import Engine02Options, Engine02Request, HardConstraints  # noqa: E402
from engine02.diversify import (  # noqa: E402
    DiversityConfig,
    alpha_ndcg,
    deep_request,
    diversify_response,
    ild,
    near_duplicate_rate,
    need_aspects,
    select,
)
from engine02.eval.metrics import bootstrap_ci, ndcg_at_k, paired_permutation_test  # noqa: E402
from engine02.eval.tasks import _slot, make_queries, random_needs  # noqa: E402
from engine02.fusion import minmax  # noqa: E402
from engine02.pipeline import Engine02  # noqa: E402

CONFIGS = (
    [DiversityConfig("none")]
    + [DiversityConfig("mmr", lam) for lam in (0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1)]
    + [DiversityConfig("dpp", th) for th in (0.95, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1)]
    + [DiversityConfig("xquad", lam) for lam in (0.1, 0.3, 0.5, 0.7, 0.9)]
)
METRICS = ["ndcg5", "ild5", "n_subcat5", "n_color5", "neardup5", "alpha_ndcg5", "rel_kept", "promoted"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default="data/catalog/kagl")
    ap.add_argument("--encoder", default="marqo-fashionSigLIP")
    ap.add_argument("--device", default="auto")
    ap.add_argument("--cache-dir", default=None)
    ap.add_argument("--n-queries", type=int, default=150)
    ap.add_argument("--depth", type=int, default=20)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    from engine02.models import TorchEncoder

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cat = Catalog.load(ROOT / args.catalog)
    enc = TorchEncoder(args.encoder, device=args.device)
    engine = Engine02(cat, enc, cache_dir=args.cache_dir)
    items = cat.items
    queries = make_queries(items, n=args.n_queries, seed=args.seed)
    rng = random.Random(args.seed)
    k, depth = args.k, args.depth
    rows, checks, lat = [], [], {c.method: [] for c in CONFIGS}
    faith = []
    for qi, q in enumerate(queries):
        needs = random_needs(rng, engine.kansei.need_ids)
        req = Engine02Request(session_id=q.qid, retrieval_text=q.text(False), needs=needs,
                              constraints=HardConstraints(category=_slot([q.category]), gender=_slot([q.gender])),
                              options=Engine02Options(top_k=k, n_candidates=50, explain_with_llm=False,
                                                      counterfactual_check=False))
        deep = engine.run(deep_request(req, depth), "full")
        cands = deep.items[:depth]
        if len(cands) < k + 1:
            continue
        ids = [it.item_id for it in cands]
        pos = cat.positions(ids)
        emb = np.asarray(engine.image_emb[pos], dtype=np.float64)
        sims = emb @ emb.T
        rel = np.array([it.score for it in cands])
        reln = minmax(rel)
        probs = {n.need_id: n.prob for n in needs}
        need_ids = engine.kansei.need_ids
        share = np.array([[it.need_contributions.get(n, 0.0) for n in need_ids] for it in cands])
        aspects, P, w = need_aspects(probs, share, need_ids, 3)
        J = (P >= 0.5).astype(float)
        grades = q.grades(items)
        subc = items["subcategory"].to_numpy()[pos]
        col = items["color"].to_numpy()[pos]
        base_rel = None
        for cfg in CONFIGS:
            t = time.perf_counter()
            sel = select(cfg, rel, emb, k, P, w)
            lat[cfg.method].append((time.perf_counter() - t) * 1000)
            s = sims[np.ix_(sel, sel)]
            kept = float(reln[sel].mean())
            if cfg.method == "none":
                base_rel = kept
            rows.append(dict(
                qid=q.qid, config=cfg.label, method=cfg.method, param=cfg.param,
                ndcg5=ndcg_at_k([ids[i] for i in sel], grades, k), ild5=ild(s),
                n_subcat5=len(set(subc[sel])), n_color5=len(set(col[sel])), neardup5=near_duplicate_rate(s),
                alpha_ndcg5=alpha_ndcg(J, sel, k, 0.5, w), rel_kept=kept / base_rel if base_rel else float("nan"),
                promoted=float(np.mean([i >= k for i in sel])),
            ))
        if qi < 20:  # reuse check: diversify.mmr(λ=0.7, depth 20) must equal the pipeline's full_mmr arm
            mmr_ids = [ids[i] for i in select(DiversityConfig("mmr", 0.7), rel, emb, k)]
            arm_ids = [it.item_id for it in engine.run(req, "full_mmr").items]
            checks.append(mmr_ids == arm_ids)
            for cfg in (DiversityConfig("mmr", 0.5), DiversityConfig("dpp", 0.7), DiversityConfig("xquad", 0.5)):
                r = diversify_response(engine, req, deep, cfg)
                cut = deep.items[k].score
                for it in r.items:
                    ok = abs(sum(c.contribution for c in it.contributions) - it.score) < 1e-6
                    if it.promoted_by_diversity:
                        ok &= it.reasons[0].startswith("為了多樣性而納入")
                    else:
                        ok &= sum(c.contribution for c in it.contributions if c.cited) > cut
                    faith.append(dict(qid=q.qid, config=cfg.label, promoted=it.promoted_by_diversity, ok=bool(ok)))
    df = pd.DataFrame(rows)
    df.to_csv(out / "per_query.csv", index=False)

    summ = []
    for cfg in CONFIGS:
        a = df[df.config == cfg.label].set_index("qid")
        b = df[df.config == "none"].set_index("qid").loc[a.index]
        row = dict(config=cfg.label, method=cfg.method, param=cfg.param, n_queries=len(a))
        for m in METRICS:
            x = a[m].to_numpy(dtype=float)
            y = b[m].to_numpy(dtype=float)
            ok = ~(np.isnan(x) | np.isnan(y))
            row[m] = float(np.nanmean(x))
            if m in ("ndcg5", "ild5", "n_subcat5", "n_color5", "neardup5", "alpha_ndcg5"):
                d = x[ok] - y[ok]
                lo, hi = bootstrap_ci(d)
                row[f"d_{m}"] = float(d.mean())
                row[f"d_{m}_ci"] = f"[{lo:.3f}, {hi:.3f}]"
                row[f"p_{m}"] = paired_permutation_test(x[ok], y[ok]) if cfg.method != "none" else float("nan")
        summ.append(row)
    sdf = pd.DataFrame(summ)
    sdf.to_csv(out / "summary.csv", index=False)
    meta = dict(catalog=args.catalog, encoder=args.encoder, n_queries=int(df.qid.nunique()), depth=depth, k=k,
                full_mmr_reuse_check=f"{sum(checks)}/{len(checks)}",
                faithfulness_check=f"{sum(f['ok'] for f in faith)}/{len(faith)}",
                promoted_cards_checked=int(sum(f["promoted"] for f in faith)),
                select_latency_ms={m: round(float(np.mean(v)), 3) for m, v in lat.items()},
                mean_pairwise_cos_none=float(1 - df[df.config == "none"].ild5.mean()))
    (out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    pd.set_option("display.width", 250)
    print(json.dumps(meta, indent=2))
    print(sdf[["config", "ndcg5", "d_ndcg5", "p_ndcg5", "ild5", "p_ild5", "n_subcat5", "n_color5", "neardup5",
               "p_neardup5", "alpha_ndcg5", "p_alpha_ndcg5", "promoted"]].round(4).to_string())


if __name__ == "__main__":
    main()
