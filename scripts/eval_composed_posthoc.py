"""Post-hoc tables for T8 (scripts/eval_composed.py outputs): headline table, the subgroup where the
current critique filter was NOT relaxed, and α(NDCG-selected) vs α(visual-selected) for the hybrid.

    python scripts/eval_composed_posthoc.py reports/agents/composed/kagl_marqo-fashionSigLIP [...more dirs]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine02.eval.metrics import bootstrap_ci, paired_permutation_test  # noqa: E402

METRICS = ["ndcg10", "hit10", "hard1_ndcg10", "hard5_hit10", "preservation5", "change5", "both5", "vis_sim5"]


def main() -> None:
    out = {}
    for d in map(Path, sys.argv[1:]):
        rows = pd.read_csv(d / "test_rows.csv")
        summ = json.loads((d / "summary.json").read_text(encoding="utf-8"))
        hyb = [c for c in rows["config"].unique() if c.startswith("image_plus_text_filter+bm25_rrf")]
        a_ndcg = f"image_plus_text_filter+bm25_rrf[a={float(summ['best_on_dev']['image_plus_text_filter'].split('=')[1].rstrip(']'))}]"
        res: dict = {"hybrid_configs": hyb, "hybrid_ndcg_selected": a_ndcg}
        cf = rows[rows["config"] == "critique_filter"].set_index("tid")
        relaxed = cf["filter_relaxed"].fillna("") != ""
        res["critique_filter_relaxed_rate"] = {v: float(relaxed[cf["variant"] == v].mean()) for v in ("color", "occasion")}
        for name, mask in [("all", None), ("not_relaxed", ~relaxed), ("relaxed", relaxed)]:
            tids = cf.index if mask is None else cf.index[mask]
            sub = rows[rows["tid"].isin(tids)]
            tab = {}
            for m in METRICS:
                piv = sub.pivot(index="tid", columns="config", values=m)
                for c in piv.columns:
                    lo, hi = bootstrap_ci(piv[c].to_numpy(), n_boot=2000)
                    tab.setdefault(c, {})[m] = (round(float(piv[c].mean()), 3), round(lo, 3), round(hi, 3),
                                                round(paired_permutation_test(piv[c].to_numpy(), piv["critique_filter"].to_numpy()), 4)
                                                if c != "critique_filter" else None)
            res[name] = {"n": int(len(tids)), "table": tab}
        # α comparison inside the hybrid
        if len(hyb) == 2:
            for m in ("ndcg10", "hard1_ndcg10", "vis_sim5", "preservation5"):
                piv = rows.pivot(index="tid", columns="config", values=m)
                res.setdefault("alpha_compare", {})[m] = {
                    "means": {h: round(float(piv[h].mean()), 4) for h in hyb},
                    "p": paired_permutation_test(piv[hyb[0]].to_numpy(), piv[hyb[1]].to_numpy())}
        out[d.name] = res
        print(f"== {d.name}  relaxed={res['critique_filter_relaxed_rate']}")
        for name in ("all", "not_relaxed"):
            t = pd.DataFrame({c: {m: v[0] for m, v in ms.items()} for c, ms in res[name]["table"].items()}).T
            print(name, "n=", res[name]["n"])
            print(t.round(3).to_string())
        print(json.dumps(res.get("alpha_compare"), indent=0))
    Path(sys.argv[1]).parent.joinpath("posthoc.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
