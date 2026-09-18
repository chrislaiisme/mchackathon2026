"""Latency of a live round: per-stage p50/p95 for /rank, /view and /complete-look.

The demo is judged live (query → cards → feedback → query again), so the number that matters is
"how long after the judge hits enter". This measures it the way the API serves it, in-process:

  python scripts/bench_latency.py --catalog data/catalog/kagl_polyvore_filled \
      --encoder marqo-fashionSigLIP --device cuda --n 30 --complete-look --out reports/latency

Reports, per endpoint: p50 / p95 / max wall clock, plus the pipeline's own stage timings
(filter / retrieve / fuse / rerank / counterfactual / explain) so a regression can be attributed.
Also measures the *second* round (with feedback: rejected items, a critique, learned weights), which
is the path the judges actually exercise and which does more work than round 1.

Cold start is reported separately (`--cold`): process-local first call, including lazy imports and
the first CUDA kernel, because on stage that is what the first query pays.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics as st
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

SEED = 20260918


def _pct(xs: list[float], p: float) -> float:
    return float(np.percentile(xs, p)) if xs else float("nan")


def _summary(name: str, wall: list[float], stages: list[dict]) -> dict:
    out = {"endpoint": name, "n": len(wall), "p50_ms": round(_pct(wall, 50), 1),
           "p95_ms": round(_pct(wall, 95), 1), "max_ms": round(max(wall), 1) if wall else None,
           "mean_ms": round(st.fmean(wall), 1) if wall else None}
    keys = sorted({k for s in stages for k in s})
    for k in keys:
        vals = [s[k] for s in stages if k in s]
        out[f"{k}_p50"] = round(_pct(vals, 50), 1)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--catalog", default="data/catalog/kagl")
    ap.add_argument("--encoder", default="hash")
    ap.add_argument("--device", default="auto")
    ap.add_argument("--arm", default="full_zclip3")
    ap.add_argument("--n", type=int, default=30, help="queries per endpoint")
    ap.add_argument("--warmup", type=int, default=3)
    ap.add_argument("--complete-look", action="store_true", help="also time /complete-look (loads the OT)")
    ap.add_argument("--ot-cache", default="", help="npz cache of OutfitTransformer item embeddings")
    ap.add_argument("--out", default="reports/latency")
    a = ap.parse_args()

    t_import = time.perf_counter()
    from engine02.catalog import Catalog
    from engine02.complete_look import CompleteTheLook
    from engine02.compat import CategoryCooccurrence
    from engine02.composed import ComposedEngine02
    from engine02.contracts import (Critique, Engine02Options, Engine02Request, FeedbackState,
                                    HardConstraints, Slot, SlotState)
    from engine02.diversify import DiversityConfig
    from engine02.eval.tasks import make_queries, random_needs
    from engine02.service import Engine02Service
    import_ms = (time.perf_counter() - t_import) * 1000

    t0 = time.perf_counter()
    cat = Catalog.load(ROOT / a.catalog)
    if a.encoder == "hash":
        from engine02.encoders import HashEncoder

        enc = HashEncoder(dim=256, captions={Path(p).name: t for p, t in zip(cat.items["image_path"], cat.texts())})
    else:
        from engine02.models import TorchEncoder

        enc = TorchEncoder(a.encoder, device=a.device)
    cooc_file = ROOT / a.catalog / "category_cooccurrence.json"
    eng = ComposedEngine02(cat, enc, cooccurrence=CategoryCooccurrence.load(cooc_file) if cooc_file.exists() else None,
                           cache_dir=ROOT / a.catalog / "index")
    build_ms = (time.perf_counter() - t0) * 1000

    ctl = None
    ot_load_ms = None
    if a.complete_look and eng.cooc is not None:
        t1 = time.perf_counter()
        from engine02.complete_look import FastOutfitTransformer

        heads = tuple(h for h in ("complementary", "compatibility") if h in FastOutfitTransformer.checkpoints())
        cache = Path(a.ot_cache) if a.ot_cache else ROOT / a.catalog / "index" / "ot_items.npz"
        ot = FastOutfitTransformer(cat, device=a.device, heads=heads, cache_file=cache) if heads else None
        ctl = CompleteTheLook(cat, eng.image_emb, eng.cooc, ot=ot)
        ot_load_ms = (time.perf_counter() - t1) * 1000
    svc = Engine02Service(eng, ctl)

    rng = random.Random(SEED)
    queries = make_queries(cat.items, n=max(a.n, 5))
    if len(queries) < a.n:
        queries = (queries * (a.n // max(1, len(queries)) + 1))[:a.n]

    def _slot(vals):
        return Slot(state=SlotState.VALUE, values=list(vals))

    def request(q, round_no=0, prev_ids=None):
        fb = FeedbackState()
        if round_no:
            fb = FeedbackState(rejected_item_ids=list(prev_ids[1:3]), chosen_item_ids=[prev_ids[0]],
                               design_adjust_steps={"formal_style": -1})
        return Engine02Request(
            session_id=q.qid, round=round_no, retrieval_text=q.text(False),
            constraints=HardConstraints(category=_slot([q.category]), gender=_slot([q.gender]),
                                        color=_slot([q.color])),
            needs=random_needs(rng, eng.kansei.need_ids), feedback=fb,
            options=Engine02Options(top_k=5, explain_with_llm=False))

    results = []
    cold = None
    for i, q in enumerate(queries[: a.warmup + a.n]):
        if i == 0:
            t = time.perf_counter()
            svc.rank(request(q), a.arm)
            cold = (time.perf_counter() - t) * 1000

    # ---- round 1 (fresh request) and round 2 (with feedback), through the service layer
    for label, with_fb in (("rank_round1", False), ("rank_round2", True)):
        wall, stages, ids_cache = [], [], {}
        for q in queries[: a.n]:
            req = request(q)
            if with_fb:
                r1 = svc.rank(req, a.arm)
                req = request(q, 1, [it.item_id for it in r1.items])
            t = time.perf_counter()
            resp = svc.rank(req, a.arm)
            wall.append((time.perf_counter() - t) * 1000)
            stages.append(dict(resp.timings_ms))
            ids_cache[q.qid] = [it.item_id for it in resp.items]
        results.append(_summary(label, wall, stages))
        print(results[-1], flush=True)

    # ---- the /view path (rank + panels), since that is what a real frontend calls
    from engine02.panels import build_view, view_labels

    wall, stages = [], []
    labels = view_labels(eng)
    for q in queries[: a.n]:
        req = request(q)
        t = time.perf_counter()
        resp = svc.rank(req, a.arm)
        build_view(req, resp, **labels)
        wall.append((time.perf_counter() - t) * 1000)
        stages.append(dict(resp.timings_ms))
    results.append(_summary("view", wall, stages))
    print(results[-1], flush=True)

    # ---- complete-the-look
    if ctl is not None:
        anchors = [str(x) for x in cat.items["item_id"].head(200)]
        wall = []
        for i in range(min(a.n, 10)):
            t = time.perf_counter()
            svc.complete_look([anchors[i % len(anchors)]], n_categories=2, k=5)
            wall.append((time.perf_counter() - t) * 1000)
        results.append(_summary(f"complete_look[{svc.complete_look_method()}]", wall, []))
        print(results[-1], flush=True)

    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    meta = dict(catalog=a.catalog, n_items=len(cat), encoder=eng.encoder.name, arm=a.arm,
                import_ms=round(import_ms, 1), build_ms=round(build_ms, 1),
                ot_load_ms=round(ot_load_ms, 1) if ot_load_ms else None,
                first_call_ms=round(cold, 1) if cold else None)
    df = pd.DataFrame(results)
    df.to_csv(out / f"latency_{Path(a.catalog).name}_{eng.encoder.name}.csv", index=False)
    (out / f"latency_{Path(a.catalog).name}_{eng.encoder.name}.json").write_text(
        json.dumps({"meta": meta, "rows": results}, indent=1), encoding="utf-8")
    print("\n" + json.dumps(meta, indent=1))
    print(df.to_string(index=False))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
