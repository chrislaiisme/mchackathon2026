"""T7b: damping early preference updates (over-reaction after one click).

Reuses the T7 simulator (scripts/eval_preference.py). Variants of BayesLogistic:
  a  current (rationality 0.5, prior_sd 1.0)            b  prior_sd 0.3 / 0.5
  c  per-element cap |Δβ| ≤ 0.5 / 0.75                   d  shrink Δβ·n/(n+κ), κ ∈ {1, 2}
  e  rationality 0.25                                    + two combinations
References: none, PRD RuleStep (0.25), Rocchio.

Metrics: hidden utility per round (c(i,d) taste = "main", metadata taste = "metadata_utility"),
mean / max |Δβ| used on round 2 (i.e. after one choice), and on real round-2 cards (pipeline with
FeedbackState.design_weight_delta, reason_mode sufficient) the share of cited reasons whose largest
need share is "feedback_adjust" (the card then reads 「你上一輪的回饋」 first).

  python scripts/eval_preference_damping.py --catalog data/catalog/kagl --device cpu \
      --cache-dir <dir>/index_kagl --users 200 --out <dir>/out/kagl
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from eval_preference import CONDITIONS, LEARN_ARM, MemoBM25, MemoText, Method, Sim  # noqa: E402

from engine02.catalog import Catalog  # noqa: E402
from engine02.contracts import FeedbackState  # noqa: E402
from engine02.eval.metrics import bootstrap_ci, paired_permutation_test  # noqa: E402
from engine02.preference import BayesLogistic, NoLearning, PreferenceEngine02, RuleStep  # noqa: E402

B = dict(rationality=0.5, prior_sd=1.0)
VARIANTS = {
    "a_current": BayesLogistic(**B),
    "b_sd0.3": BayesLogistic(rationality=0.5, prior_sd=0.3),
    "b_sd0.5": BayesLogistic(rationality=0.5, prior_sd=0.5),
    "c_cap0.5": BayesLogistic(**B, max_abs_delta=0.5),
    "c_cap0.75": BayesLogistic(**B, max_abs_delta=0.75),
    "d_kappa1": BayesLogistic(**B, shrink_kappa=1.0),
    "d_kappa2": BayesLogistic(**B, shrink_kappa=2.0),
    "e_lambda0.25": BayesLogistic(rationality=0.25, prior_sd=1.0),
    "x_kappa1_cap0.75": BayesLogistic(**B, shrink_kappa=1.0, max_abs_delta=0.75),
    "x_sd0.5_cap0.75": BayesLogistic(rationality=0.5, prior_sd=0.5, max_abs_delta=0.75),
}
REFS = [Method("none", NoLearning()), Method("rulestep_prd", RuleStep(step_size=0.25)),
        Method("rocchio", NoLearning(), rocchio=True)]


def round2_reasons(sim: Sim, user, cond, learner, history) -> dict:
    """Real pipeline run for round 2 with the learned Δβ in the request."""
    probs = sim.probs(user, cond)
    beta0 = sim.space.prior_mean(probs, LEARN_ARM.need_scale)
    delta = learner.update(history[:1], sim.F, beta0).delta
    fb = FeedbackState(design_weight_delta=sim.space.to_dict(delta))
    req = sim.request(user, probs, fb, 2)
    req.options.top_k = 5
    resp = sim.e.run(req, LEARN_ARM)
    n_cited = n_fb = cards_fb = 0
    for it in resp.items:
        card_fb = False
        for c in it.contributions:
            if not (c.cited and c.contribution > 0):
                continue
            n_cited += 1
            if c.group == "design" and c.need_shares:
                top = max(c.need_shares.items(), key=lambda kv: kv[1])[0]
                if top == "feedback_adjust":
                    n_fb += 1
                    card_fb = True
        cards_fb += card_fb
    return dict(reason_fb_share=n_fb / n_cited if n_cited else 0.0,
                cards_with_fb_reason=cards_fb / max(1, len(resp.items)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default="data/catalog/kagl")
    ap.add_argument("--encoder", default="marqo-fashionSigLIP")
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--cache-dir", default=None)
    ap.add_argument("--users", type=int, default=200)
    ap.add_argument("--rounds", type=int, default=5)
    ap.add_argument("--n-candidates", type=int, default=100)
    ap.add_argument("--status", default=None)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    status = Path(args.status) if args.status else out / "status.txt"
    t0 = time.perf_counter()

    def note(msg):
        line = f"[{time.perf_counter() - t0:.0f}s] {args.catalog} {msg}"
        print(line, flush=True)
        with open(status, "a") as f:
            f.write(line + "\n")

    cat = Catalog.load(ROOT / args.catalog)
    if args.encoder == "hash":
        from engine02.encoders import HashEncoder

        enc = HashEncoder(dim=128, captions={Path(p).name: t for p, t in zip(cat.items["image_path"], cat.texts())})
    else:
        from engine02.models import TorchEncoder

        enc = TorchEncoder(args.encoder, device=args.device)
    engine = PreferenceEngine02(cat, MemoText(enc), cache_dir=args.cache_dir)
    engine.bm25 = MemoBM25(engine.bm25)
    sim = Sim(engine, args.n_candidates, 5, args.rounds, 0)
    users = sim.build_users(args.users, offset=0)
    note(f"setup done, {len(users)} users")

    conds = [c for c in CONDITIONS if c.name in ("main", "metadata_utility", "needs_informed")]
    rows, reason_rows = [], []
    for cond in conds:
        for m in REFS:
            for u in users:
                rows += sim.simulate(u, cond, m)
                if m.name == "rulestep_prd":
                    reason_rows.append(dict(condition=cond.name, method=m.name, uid=u["uid"],
                                            **round2_reasons(sim, u, cond, m.learner, sim.last_history)))
        note(f"{cond.name} refs done")
        for name, learner in VARIANTS.items():
            m = Method(name, learner)
            for u in users:
                rows += sim.simulate(u, cond, m)
                reason_rows.append(dict(condition=cond.name, method=name, uid=u["uid"],
                                        **round2_reasons(sim, u, cond, learner, sim.last_history)))
            note(f"{cond.name} {name} done")
    df = pd.DataFrame(rows)
    rr = pd.DataFrame(reason_rows)
    df[["condition", "method", "uid", "round", "util", "attr_ndcg", "dmean_abs", "dmax_abs"]].to_csv(
        out / "rounds.csv.gz", index=False, float_format="%.4f")
    rr.to_csv(out / "reasons_round2.csv.gz", index=False, float_format="%.4f")

    summ = []
    for cond, sub in df.groupby("condition"):
        piv5 = sub[sub["round"] == args.rounds].pivot(index="uid", columns="method", values="util")
        r2 = sub[sub["round"] == 2].pivot(index="uid", columns="method", values="dmax_abs")
        r2m = sub[sub["round"] == 2].pivot(index="uid", columns="method", values="dmean_abs")
        rs = rr[rr.condition == cond].pivot(index="uid", columns="method", values="reason_fb_share")
        rc = rr[rr.condition == cond].pivot(index="uid", columns="method", values="cards_with_fb_reason")
        curve = sub.groupby(["method", "round"])["util"].mean().unstack("round")
        attr5 = sub[sub["round"] == args.rounds].groupby("method")["attr_ndcg"].mean()
        for m in piv5.columns:
            x = piv5[m].to_numpy()
            row = dict(condition=cond, method=m, **{f"util_r{r}": curve.loc[m, r] for r in curve.columns},
                       attr_ndcg_r5=attr5[m], dmean_abs_r2=r2m[m].mean(), dmax_abs_r2=r2[m].mean(),
                       reason_fb_share_r2=rs[m].mean() if m in rs else np.nan,
                       cards_fb_r2=rc[m].mean() if m in rc else np.nan)
            util25 = sub[sub["round"] >= 2].groupby(["uid", "method"])["util"].mean().unstack("method")
            row["util_r2_5"] = util25[m].mean()
            for ref in ("a_current", "rulestep_prd"):
                if m == ref:
                    continue
                d = x - piv5[ref].to_numpy()
                lo, hi = bootstrap_ci(d)
                row[f"d5_vs_{ref}"] = d.mean()
                row[f"ci5_vs_{ref}"] = f"[{lo:.3f}, {hi:.3f}]"
                row[f"p5_vs_{ref}"] = paired_permutation_test(x, piv5[ref].to_numpy())
                d25 = util25[m].to_numpy() - util25[ref].to_numpy()
                row[f"d25_vs_{ref}"] = d25.mean()
                row[f"p25_vs_{ref}"] = paired_permutation_test(util25[m].to_numpy(), util25[ref].to_numpy())
                if m in rs and ref in rs:
                    row[f"p_reason_vs_{ref}"] = paired_permutation_test(rs[m].to_numpy(), rs[ref].to_numpy())
            summ.append(row)
    pd.DataFrame(summ).to_csv(out / "summary.csv", index=False, float_format="%.4f")
    (out / "meta.json").write_text(json.dumps(dict(n_users=len(users), variants={k: repr(v) for k, v in VARIANTS.items()},
                                                   n_candidates=args.n_candidates), indent=1))
    note("ALL DONE")


if __name__ == "__main__":
    main()
