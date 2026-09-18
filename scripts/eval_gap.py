"""T14: does the design-element gap panel actually find a gap? (injection holdout + control)

`panels.element_gap` claims "this element is in demand and the catalog barely has it". That claim
is testable without any sales data: take an element d, remove the catalog items that express it,
and check that d rises to the top of the gap ranking. The control is the part that makes it
falsifiable — remove the *same number* of random items and d must NOT rise.

  python scripts/eval_gap.py --catalog data/catalog/kagl_full --encoder marqo-fashionSigLIP \
      --device cuda --sessions 60 --trials 20

Reported per condition: MRR of the injected element in the gap ranking (with a uniform-random
baseline for the same number of elements), how often it lands first, and a paired permutation test
between the injected and control conditions.

What this does NOT show: that the gap predicts real sales. The demand side here is our own query
distribution, so the panel measures "what was asked of this catalog", nothing more.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

SEED = 20260918


def paired_permutation(a: list[float], b: list[float], n: int = 10000, seed: int = 0) -> float:
    a, b = np.asarray(a), np.asarray(b)
    d = a - b
    obs = abs(d.mean())
    rng = np.random.default_rng(seed)
    flips = rng.choice([-1.0, 1.0], size=(n, len(d)))
    return float((np.abs((flips * d).mean(axis=1)) >= obs).mean())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--catalog", default="data/catalog/kagl")
    ap.add_argument("--encoder", default="hash")
    ap.add_argument("--device", default="auto")
    ap.add_argument("--arm", default="full_zclip3")
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--sessions", type=int, default=60, help="synthetic demand sessions per trial")
    ap.add_argument("--trials", type=int, default=20)
    ap.add_argument("--out", default="reports/ablation")
    a = ap.parse_args()

    from engine02.catalog import Catalog
    from engine02.config import ARMS
    from engine02.panels import element_gap
    from engine02.pipeline import Engine02

    cat = Catalog.load(ROOT / a.catalog)
    if a.encoder == "hash":
        from engine02.encoders import HashEncoder

        enc = HashEncoder(dim=256, captions={Path(p).name: t for p, t in zip(cat.items["image_path"], cat.texts())})
    else:
        from engine02.models import TorchEncoder

        enc = TorchEncoder(a.encoder, device=a.device)
    eng = Engine02(cat, enc, cache_dir=ROOT / a.catalog / "index")
    c = eng.design_matrix(ARMS[a.arm])
    ids = eng.kansei.element_ids
    n_items = len(c)
    rng = random.Random(SEED)

    def rank_of(report, element: str) -> int:
        order = [e.element for e in report.elements]
        return order.index(element) + 1 if element in order else len(ids)

    # Demand has to spread over many elements or the ranking is uncontested: with only one
    # element carrying demand it is trivially rank 1 whatever the supply, and all three conditions
    # come out identical (the first version of this script did exactly that and measured nothing).
    from engine02.eval.tasks import random_needs

    rows = []
    for trial in range(a.trials):
        rr_rng = random.Random(SEED + trial)
        sessions = [({n.need_id: n.prob for n in random_needs(rr_rng, eng.kansei.need_ids)}, {})
                    for _ in range(a.sessions)]
        base_report = element_gap(eng, sessions, a.arm, a.threshold)
        wanted = [e.element for e in base_report.elements if e.direction == "wanted"]
        if not wanted:
            continue
        d = wanted[trial % len(wanted)]
        j = ids.index(d)

        expressing = np.flatnonzero(c[:, j] > a.threshold)
        if len(expressing) < 10 or len(expressing) > n_items * 0.9:
            continue  # nothing to remove, or removing it would empty the catalog

        keep_injected = np.ones(n_items, dtype=bool)
        keep_injected[expressing] = False
        keep_control = np.ones(n_items, dtype=bool)
        keep_control[rng.sample(range(n_items), len(expressing))] = False

        base = base_report
        inj = element_gap(eng, sessions, a.arm, a.threshold, mask=keep_injected)
        ctl = element_gap(eng, sessions, a.arm, a.threshold, mask=keep_control)
        rows.append(dict(trial=trial, element=d, n_removed=int(len(expressing)),
                         rank_base=rank_of(base, d), rank_injected=rank_of(inj, d),
                         rank_control=rank_of(ctl, d),
                         supply_base=next((e.supply for e in base.elements if e.element == d), None),
                         supply_injected=next((e.supply for e in inj.elements if e.element == d), None),
                         supply_control=next((e.supply for e in ctl.elements if e.element == d), None)))
        print(rows[-1], flush=True)

    df = pd.DataFrame(rows)
    if df.empty:
        raise SystemExit("no usable elements (every one was too rare or too common in this catalog)")
    rr = {k: (1.0 / df[f"rank_{k}"]).tolist() for k in ("base", "injected", "control")}
    n_el = len(ids)
    summary = dict(
        catalog=a.catalog, encoder=eng.encoder.name, arm=a.arm, threshold=a.threshold,
        trials=len(df), n_elements=n_el,
        random_baseline_mrr=round(float(np.mean([1 / r for r in range(1, n_el + 1)])), 4),
        mrr_base=round(float(np.mean(rr["base"])), 4),
        mrr_injected=round(float(np.mean(rr["injected"])), 4),
        mrr_control=round(float(np.mean(rr["control"])), 4),
        first_place_injected=round(float((df.rank_injected == 1).mean()), 4),
        first_place_control=round(float((df.rank_control == 1).mean()), 4),
        p_injected_vs_control=paired_permutation(rr["injected"], rr["control"], seed=SEED),
        p_control_vs_base=paired_permutation(rr["control"], rr["base"], seed=SEED),
    )
    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / f"gap_{Path(a.catalog).name}_{eng.encoder.name}.csv", index=False)
    (out / f"gap_{Path(a.catalog).name}_{eng.encoder.name}.json").write_text(
        json.dumps({"summary": summary, "rows": rows}, indent=1), encoding="utf-8")
    print("\n" + json.dumps(summary, indent=1))
    print("\nRead it as: injected MRR should beat both the control and the random baseline, and\n"
          "p_control_vs_base should be non-significant — otherwise removing any items moves the\n"
          "ranking and the panel is measuring catalog size, not a gap.")


if __name__ == "__main__":
    main()
