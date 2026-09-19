"""How much do the hand-set numbers in the Kansei table K[n,d] actually matter? (T13)

The K cells come from the literature (kansei_v1_literature.json, 32 sources), but each cell is a
judgement call, and nobody has calibrated them against human ratings. Rather than pretend the
numbers are exact, this measures how sensitive the served ranking is to them:

  python scripts/eval_kansei_sensitivity.py --catalog data/catalog/kagl --encoder marqo-fashionSigLIP \
      --n-queries 60 --trials 20 --noise 0.2

For each trial the non-zero cells of K are multiplied by (1 + eps), eps ~ U(-noise, noise), and the
same queries are ranked again. Reported per noise level:
  - top-5 overlap with the unperturbed ranking (1.0 = the numbers do not matter at all)
  - Kendall's tau of the top-20 order
  - NDCG@5 against the same metadata ground truth as T1, so a shaken table that keeps quality is
    distinguishable from one that quietly degrades it
  - how often the *cited reasons* change, which is what the user actually sees

Read it the other way round too: if overlap stays ~1.0 at ±50%, the K numbers are doing less work
than the slide claims, and the honest statement is "the direction matters, the magnitude does not".
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

from engine02.catalog import Catalog  # noqa: E402
from engine02.config import ARMS  # noqa: E402
from engine02.pipeline import Engine02  # noqa: E402

SEED = 20260918


def kendall_tau(a: list[str], b: list[str]) -> float:
    """Tau over the items present in both lists (ties dropped); nan if fewer than 2 overlap."""
    common = [x for x in a if x in set(b)]
    if len(common) < 2:
        return float("nan")
    ra = {x: i for i, x in enumerate(a)}
    rb = {x: i for i, x in enumerate(b)}
    conc = disc = 0
    for i in range(len(common)):
        for j in range(i + 1, len(common)):
            s = (ra[common[i]] - ra[common[j]]) * (rb[common[i]] - rb[common[j]])
            conc += s > 0
            disc += s < 0
    return (conc - disc) / (conc + disc) if conc + disc else float("nan")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--catalog", default="data/catalog/kagl")
    ap.add_argument("--encoder", default="marqo-fashionSigLIP")
    ap.add_argument("--device", default="auto")
    ap.add_argument("--arm", default="full_zclip3")
    ap.add_argument("--n-queries", type=int, default=60)
    ap.add_argument("--trials", type=int, default=20)
    ap.add_argument("--noise", type=float, nargs="+", default=[0.2, 0.5])
    ap.add_argument("--out", default="reports/ablation")
    a = ap.parse_args()

    import random

    from engine02.contracts import Engine02Options, Engine02Request, HardConstraints
    from engine02.eval.tasks import make_queries, ndcg_at_k, random_needs, _slot

    cat = Catalog.load(ROOT / a.catalog)
    if a.encoder == "hash":
        from engine02.encoders import HashEncoder

        enc = HashEncoder(dim=256, captions={Path(p).name: t for p, t in zip(cat.items["image_path"], cat.texts())})
    else:
        from engine02.models import TorchEncoder

        enc = TorchEncoder(a.encoder, device=a.device)
    eng = Engine02(cat, enc, cache_dir=ROOT / a.catalog / "index")
    queries = make_queries(cat.items, n=a.n_queries)
    rng0 = random.Random(SEED)
    # K only does anything when the request carries needs, so every query gets three (as in T6)
    reqs, grades = [], []
    for q in queries:
        reqs.append(Engine02Request(
            session_id=q.qid, retrieval_text=q.text(False), needs=random_needs(rng0, eng.kansei.need_ids),
            constraints=HardConstraints(category=_slot([q.category]), gender=_slot([q.gender])),
            options=Engine02Options(top_k=5, explain_with_llm=False, counterfactual_check=False)))
        grades.append(q.grades(cat.items))

    base = [eng.run(r, a.arm) for r in reqs]
    base_top = [[it.item_id for it in r.items] for r in base]
    base_reasons = [[tuple(sorted(c.term for c in it.contributions if c.cited)) for it in r.items] for r in base]
    base_ndcg = [ndcg_at_k(t, g, 5) for t, g in zip(base_top, grades)]
    print(f"baseline NDCG@5 = {np.mean(base_ndcg):.3f} over {len(reqs)} queries with needs")

    K0 = eng.kansei.K.copy()
    nz = K0 != 0
    rng = np.random.default_rng(SEED)
    rows = []
    for noise in a.noise:
        ov, taus, changed, ndcg_delta = [], [], [], []
        for _ in range(a.trials):
            eps = rng.uniform(-noise, noise, size=K0.shape)
            # c(i,d) does not depend on K, so the design-matrix cache stays valid
            eng.kansei.K = np.where(nz, np.clip(K0 * (1 + eps), -1, 1), 0.0)
            for i, r in enumerate(reqs):
                out = eng.run(r, a.arm)
                top = [it.item_id for it in out.items]
                ov.append(len(set(top[:5]) & set(base_top[i][:5])) / max(1, len(base_top[i][:5])))
                taus.append(kendall_tau(top, base_top[i]))
                now = [tuple(sorted(c.term for c in it.contributions if c.cited)) for it in out.items]
                changed.append(float(now[:5] != base_reasons[i][:5]))
                ndcg_delta.append(ndcg_at_k(top, grades[i], 5) - base_ndcg[i])
        rows.append(dict(noise=noise, trials=a.trials, queries=len(reqs),
                         top5_overlap=round(float(np.mean(ov)), 3),
                         kendall_tau_top20=round(float(np.nanmean(taus)), 3),
                         reasons_changed=round(float(np.mean(changed)), 3),
                         ndcg5_delta=round(float(np.mean(ndcg_delta)), 4),
                         ndcg5_delta_p05=round(float(np.percentile(ndcg_delta, 5)), 4)))
        print(rows[-1])
    eng.kansei.K = K0

    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_csv(out / f"kansei_sensitivity_{a.encoder}.csv", index=False)
    (out / f"kansei_sensitivity_{a.encoder}.json").write_text(
        json.dumps({"arm": a.arm, "catalog": a.catalog, "kansei_version": eng.kansei.version,
                    "rows": rows}, indent=2), encoding="utf-8")
    print(f"\n{df.to_string(index=False)}\nwrote {out}")


if __name__ == "__main__":
    main()
