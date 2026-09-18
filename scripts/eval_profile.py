"""§3.32: does the three-question profile actually help round 1, or is it just the shrinkage?

A simulated user has a hidden target item. The profile questions are answered **as that target
would answer them**: for each asked axis, the side (high/low) is the side the target item sits on.
Then round 1 runs with no feedback at all, which is exactly where a profile is supposed to matter.

Arms, and what each one can kill:
  none          no profile. The baseline.
  p3            three answers from the target. The proposal.
  p3_shuffled   the SAME three answers, permuted across axes — the soul control. If p3_shuffled
                scores like p3, the gain never came from the content of the profile, only from
                kappa0 nudging the design weights, and the feature is a fraud.
  p3_rand       three answers drawn at random. Separates "profile content" from "any profile".
  p5 / p10      more questions, to see whether 3 was leaving value on the table.

  python scripts/eval_profile.py --catalog data/catalog/kagl_polyvore_filled \
      --encoder marqo-fashionSigLIP --device cuda --targets 120

Reported: rank of the hidden target in round 1 (MRR and hit@5), paired permutation tests against
`none` and against `p3_shuffled`, and bootstrap CIs on the differences.
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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--catalog", default="data/catalog/kagl")
    ap.add_argument("--encoder", default="hash")
    ap.add_argument("--device", default="auto")
    ap.add_argument("--arm", default="full_zclip3")
    ap.add_argument("--targets", type=int, default=120)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--depth", type=int, default=50, help="how deep to look for the target")
    ap.add_argument("--out", default="reports/ablation/profile")
    a = ap.parse_args()

    from engine02.catalog import Catalog
    from engine02.config import ARMS
    from engine02.contracts import Engine02Options, Engine02Request, HardConstraints, ProfilePrior, Slot, SlotState
    from engine02.eval.metrics import bootstrap_ci, paired_permutation_test
    from engine02.panels import profile_questions
    from engine02.pipeline import Engine02

    cat = Catalog.load(ROOT / a.catalog)
    if a.encoder == "hash":
        from engine02.encoders import HashEncoder

        enc = HashEncoder(dim=256, captions={Path(p).name: t for p, t in
                                             zip(cat.items["image_path"], cat.texts())})
    else:
        from engine02.models import TorchEncoder

        enc = TorchEncoder(a.encoder, device=a.device)
    eng = Engine02(cat, enc, cache_dir=ROOT / a.catalog / "index")
    arm_cfg = ARMS[a.arm]
    c_mat = np.asarray(eng.design_matrix(arm_cfg), dtype=np.float64)
    mu, sd = c_mat.mean(axis=0), np.where(c_mat.std(axis=0) > 1e-9, c_mat.std(axis=0), 1.0)
    el_ids = eng.kansei.element_ids

    # the question set does not depend on the user, so it is asked once (that is also true on stage)
    questions = {n: profile_questions(eng, a.arm, n=n) for n in (3, 5, 10)}
    rng = random.Random(SEED)
    items = cat.items
    pool = items[items["category"].isin({"top", "bottom", "dress", "outerwear"})].dropna(
        subset=["gender", "subcategory"])
    if pool.empty:
        pool = items.dropna(subset=["subcategory"])
    targets = rng.sample(list(pool.index), min(a.targets, len(pool)))

    def truthful(qs, tpos: int) -> dict[str, float]:
        """How the hidden target would answer: the pole it actually sits on, in catalog z units."""
        out = {}
        for q in qs:
            j = el_ids.index(q["axis"])
            z = (c_mat[tpos, j] - mu[j]) / sd[j]
            out[q["axis"]] = 1.0 if z >= 0 else -1.0
        return out

    def shuffled(w: dict[str, float]) -> dict[str, float]:
        vals = list(w.values())
        rng.shuffle(vals)
        return dict(zip(w.keys(), vals))

    def randomised(qs) -> dict[str, float]:
        return {q["axis"]: rng.choice([1.0, -1.0]) for q in qs}

    rows = []
    for n_t, tpos in enumerate(targets):
        target = items.loc[tpos]
        tid = str(target["item_id"])
        # the round-1 query is vague on purpose: a profile is meant to matter when the words do not
        text = f"{target['gender']} {target['category']}"
        cons = HardConstraints(category=Slot(state=SlotState.VALUE, values=[str(target["category"])]),
                               gender=Slot(state=SlotState.VALUE, values=[str(target["gender"])]))
        w3 = truthful(questions[3], tpos)
        arms = {
            "none": None,
            "p3": w3,
            "p3_shuffled": shuffled(dict(w3)),
            "p3_rand": randomised(questions[3]),
            "p5": truthful(questions[5], tpos),
            "p10": truthful(questions[10], tpos),
        }
        for name, weights in arms.items():
            req = Engine02Request(
                session_id=f"p{tpos}", retrieval_text=text, constraints=cons,
                profile=None if weights is None else ProfilePrior(weights=weights, n_answers=len(weights)),
                options=Engine02Options(top_k=a.depth, explain_with_llm=False, counterfactual_check=False))
            resp = eng.run(req, a.arm)
            ids = [it.item_id for it in resp.items]
            rank = ids.index(tid) + 1 if tid in ids else 0
            rows.append(dict(target=tid, arm=name, rank=rank,
                             rr=1.0 / rank if rank else 0.0, hit_at_k=int(0 < rank <= a.k)))
        if n_t % 20 == 0:
            print(f"{n_t}/{len(targets)}", flush=True)

    df = pd.DataFrame(rows)
    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    tag = f"profile_{Path(a.catalog).name}_{enc.name}"
    df.to_csv(out / f"{tag}.csv", index=False)

    piv_rr = df.pivot(index="target", columns="arm", values="rr")
    piv_hit = df.pivot(index="target", columns="arm", values="hit_at_k")
    print(f"\n=== round 1, hidden target among top {a.depth} ({len(piv_rr)} simulated users)")
    print(f"{'arm':<13} {'MRR':>7} {'hit@' + str(a.k):>7}   {'vs none':>22}   {'vs p3_shuffled':>22}")
    report = {}
    for arm in ("none", "p3", "p3_shuffled", "p3_rand", "p5", "p10"):
        if arm not in piv_rr:
            continue
        line = f"{arm:<13} {piv_rr[arm].mean():7.4f} {piv_hit[arm].mean():7.3f}"
        cmp_ = {}
        for base in ("none", "p3_shuffled"):
            if arm == base or base not in piv_rr:
                line += f"   {'—':>22}"
                continue
            d = (piv_rr[arm] - piv_rr[base]).to_numpy()
            p = paired_permutation_test(piv_rr[arm].to_numpy(), piv_rr[base].to_numpy(), n_perm=20000)
            lo, hi = bootstrap_ci(d)
            cmp_[base] = dict(delta=round(float(d.mean()), 4), ci=[round(lo, 4), round(hi, 4)], p=round(p, 5))
            line += f"   {d.mean():+.4f} p={p:<9.5f}"
        report[arm] = dict(mrr=round(float(piv_rr[arm].mean()), 4),
                           hit_at_k=round(float(piv_hit[arm].mean()), 4), vs=cmp_)
        print(line)

    (out / f"{tag}.json").write_text(json.dumps(
        {"setup": dict(catalog=a.catalog, encoder=enc.name, arm=a.arm, targets=len(piv_rr),
                       depth=a.depth, k=a.k), "arms": report}, indent=1), encoding="utf-8")
    print(f"\nwrote {out / (tag + '.json')}")
    print("\nRead it as: p3 must beat BOTH none and p3_shuffled. If p3 is level with p3_shuffled, the gain is the\n"
          "shrinkage alone and the profile content is doing nothing — the feature should be dropped.")


if __name__ == "__main__":
    main()
