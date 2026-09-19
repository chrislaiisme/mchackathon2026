"""What did filling the missing attributes actually buy? (§3.17, with a file behind it)

The claim in the design doc is that model-filled attributes take four-constraint queries from
"almost always needs the relaxation ladder" to "almost never". That comparison only means something
if **the same queries** hit both catalogs: queries generated from each catalog's own metadata are
not comparable, because the unfilled catalog can only ask about items whose attributes it has.

So: generate the query set once, from the filled catalog, and run the identical set against both.

  python scripts/eval_fill_effect.py --before data/catalog/kagl_polyvore \
      --after data/catalog/kagl_polyvore_filled --encoder marqo-fashionSigLIP --device cuda \
      --n-queries 100 --out reports/server/fill_effect

Reported per catalog: mean candidates after the hard filter, how often the ladder had to relax
anything, hard-constraint satisfaction, and how many of the surviving candidates come from the
Polyvore half (the half that had no attributes at all before filling).
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
    ap.add_argument("--before", default="data/catalog/kagl_polyvore")
    ap.add_argument("--after", default="data/catalog/kagl_polyvore_filled")
    ap.add_argument("--encoder", default="hash")
    ap.add_argument("--device", default="auto")
    ap.add_argument("--arm", default="full")
    ap.add_argument("--n-queries", type=int, default=100)
    ap.add_argument("--out", default="reports/ablation/fill_effect")
    a = ap.parse_args()

    from engine02.catalog import Catalog
    from engine02.contracts import Engine02Options, Engine02Request, HardConstraints, Slot, SlotState
    from engine02.eval.tasks import make_queries
    from engine02.pipeline import Engine02

    def load(path: str):
        cat = Catalog.load(ROOT / path)
        if a.encoder == "hash":
            from engine02.encoders import HashEncoder

            enc = HashEncoder(dim=256, captions={Path(p).name: t for p, t in
                                                 zip(cat.items["image_path"], cat.texts())})
        else:
            from engine02.models import TorchEncoder

            enc = TorchEncoder(a.encoder, device=a.device)
        return cat, Engine02(cat, enc, cache_dir=ROOT / path / "index")

    cat_after, eng_after = load(a.after)
    cat_before, eng_before = load(a.before)
    # the query set comes from the filled catalog, so both catalogs answer the same questions
    queries = make_queries(cat_after.items, n=a.n_queries)

    def slot(v):
        return Slot(state=SlotState.VALUE, values=[v]) if v else Slot()

    def polyvore_share(cat, n_after: int, mask_ids: list[str]) -> float:
        if "source" not in cat.items.columns or not mask_ids:
            return float("nan")
        src = cat.items.set_index("item_id")["source"].astype(str)
        hit = [i for i in mask_ids if i in src.index and "polyvore" in src.loc[i].lower()]
        return len(hit)

    rows = []
    for label, cat, eng in (("before", cat_before, eng_before), ("after", cat_after, eng_after)):
        for q in queries:
            c = HardConstraints(category=slot(q.category), color=slot(q.color),
                                gender=slot(q.gender), occasion=slot(q.occasion))
            req = Engine02Request(session_id=q.qid, retrieval_text=q.text(False), constraints=c,
                                  options=Engine02Options(top_k=5, explain_with_llm=False,
                                                          counterfactual_check=False))
            resp = eng.run(req, a.arm)
            shown = [it.item_id for it in resp.items]
            rows.append(dict(catalog=label, qid=q.qid,
                             satisfaction=resp.metrics.hard_constraint_satisfaction,
                             n_after_filter=resp.constraint_report.n_after_filter,
                             relaxed=";".join(resp.constraint_report.relaxed),
                             n_items=len(shown),
                             polyvore_in_top=polyvore_share(cat, len(shown), shown)))
        print(f"{label}: done {len(queries)} queries", flush=True)

    df = pd.DataFrame(rows)
    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "fill_effect.csv", index=False)

    summary = []
    for label, g in df.groupby("catalog", sort=False):
        summary.append(dict(catalog=label,
                            mean_after_filter=round(float(g.n_after_filter.mean()), 2),
                            median_after_filter=float(g.n_after_filter.median()),
                            relaxed_rate=round(float((g.relaxed != "").mean()), 4),
                            satisfaction=round(float(g.satisfaction.mean()), 4),
                            polyvore_in_top5=round(float(np.nanmean(g.polyvore_in_top)), 2)))
    s = pd.DataFrame(summary).set_index("catalog").reindex(["before", "after"])
    print("\n=== same 100 four-constraint queries, both catalogs")
    print(s.to_string())
    (out / "fill_effect.json").write_text(json.dumps(
        {"setup": dict(before=a.before, after=a.after, encoder=a.encoder, arm=a.arm,
                       n_queries=len(queries), queries_generated_from=a.after),
         "summary": s.reset_index().to_dict(orient="records")}, indent=1), encoding="utf-8")
    print(f"\nwrote {out / 'fill_effect.json'}")


if __name__ == "__main__":
    main()
