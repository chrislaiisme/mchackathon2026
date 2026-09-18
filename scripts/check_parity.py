"""Did an optimisation change the ranking? Compare two settings on the same queries.

Every performance change in ENGINE 02 has to be provably output-neutral, otherwise the measured
results in docs/engine02-design.md stop meaning anything. This ranks the same queries twice and
reports where the two runs disagree.

  # float32 dense scoring vs the float64 path it replaced
  python scripts/check_parity.py --catalog data/catalog/kagl_polyvore_filled \
      --encoder marqo-fashionSigLIP --device cuda --n 60 --env ENGINE02_DENSE_F64=1

Reports: share of queries with an identical top-k id list, the first rank where they differ, and
the largest score gap seen at a disagreement (a tie broken differently is not the same thing as a
ranking change).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402


def run_all(engine, reqs, arm):
    out = []
    for r in reqs:
        resp = engine.run(r, arm)
        out.append(([it.item_id for it in resp.items], [it.score for it in resp.items]))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--catalog", default="data/catalog/kagl")
    ap.add_argument("--encoder", default="hash")
    ap.add_argument("--device", default="auto")
    ap.add_argument("--arm", default="full_zclip3")
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--k", type=int, default=20)
    ap.add_argument("--env", action="append", default=[], help="NAME=VALUE applied to the second run")
    ap.add_argument("--out", default="reports/latency")
    a = ap.parse_args()

    from engine02.catalog import Catalog
    from engine02.contracts import Engine02Options, Engine02Request, HardConstraints, Slot, SlotState
    from engine02.eval.tasks import make_queries, random_needs
    from engine02.pipeline import Engine02

    cat = Catalog.load(ROOT / a.catalog)
    if a.encoder == "hash":
        from engine02.encoders import HashEncoder

        enc = HashEncoder(dim=256, captions={Path(p).name: t for p, t in zip(cat.items["image_path"], cat.texts())})
    else:
        from engine02.models import TorchEncoder

        enc = TorchEncoder(a.encoder, device=a.device)
    eng = Engine02(cat, enc, cache_dir=ROOT / a.catalog / "index")

    rng = random.Random(20260918)
    queries = make_queries(cat.items, n=a.n)
    reqs = [Engine02Request(
        session_id=q.qid, retrieval_text=q.text(False),
        constraints=HardConstraints(category=Slot(state=SlotState.VALUE, values=[q.category]),
                                    gender=Slot(state=SlotState.VALUE, values=[q.gender])),
        needs=random_needs(rng, eng.kansei.need_ids),
        options=Engine02Options(top_k=a.k, explain_with_llm=False)) for q in queries]

    before = run_all(eng, reqs, a.arm)
    for kv in a.env:
        k, _, v = kv.partition("=")
        os.environ[k] = v
    eng._emb32 = None  # force the other code path to rebuild whatever it caches
    after = run_all(eng, reqs, a.arm)

    same, first_diffs, score_gaps = 0, [], []
    for (ids_a, sc_a), (ids_b, sc_b) in zip(before, after):
        if ids_a == ids_b:
            same += 1
            continue
        d = next(i for i, (x, y) in enumerate(zip(ids_a, ids_b)) if x != y)
        first_diffs.append(d)
        score_gaps.append(abs(sc_a[d] - sc_b[d]))
    n = len(reqs)
    summary = dict(queries=n, env=a.env, identical_topk=round(same / n, 4),
                   n_differing=n - same,
                   first_diff_rank_min=min(first_diffs) if first_diffs else None,
                   max_score_gap_at_diff=float(max(score_gaps)) if score_gaps else 0.0,
                   max_abs_score_delta=float(max(abs(x - y) for (_, sa), (_, sb) in zip(before, after)
                                                for x, y in zip(sa, sb))) if n else 0.0)
    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    (out / "parity.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    if summary["identical_topk"] == 1.0:
        print("PASS: the two settings rank identically")
    else:
        print("DIFFERS: inspect before trusting previously measured numbers")
    sys.exit(0 if summary["identical_topk"] == 1.0 else 2)


if __name__ == "__main__":
    main()
