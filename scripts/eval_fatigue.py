"""T15: should "shown earlier but not chosen" be a ranking term by default?

The demo is judged over rounds, and without this term round 2 can replay round 1 unchanged — the
judges would see the same cards after giving feedback. The term is cheap, but it can also push
away an item the user simply had not got to yet, so it needs both numbers:

  novelty@k    share of the shown slate that was not shown in an earlier round   (should go UP)
  utility@k    hidden utility of the shown slate in the last round               (must NOT go down)

  python scripts/eval_fatigue.py --catalog data/catalog/kagl_full --encoder marqo-fashionSigLIP \
      --device cuda --users 60 --rounds 4 --weights 0,0.15,0.3,0.5,1.0

Simulated user, same assumptions as T7 (docs/research/recsys-preference.md): a hidden taste vector
over design elements, utility = attribute relevance + strength · z(taste · c(i)), choice =
argmax(utility/τ + Gumbel). **Circular by construction**: the simulator scores items with the same
c(i,d) features the ranker uses, so treat the utility column as "does the term break the ranking",
not as a user study. The user ignores everything except their pick, which is exactly the signal
this term reads.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

SEED = 20260918


def paired_permutation(a, b, n: int = 10000, seed: int = 0) -> float:
    d = np.asarray(a, dtype=float) - np.asarray(b, dtype=float)
    if not len(d) or not np.any(d):
        return 1.0
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
    ap.add_argument("--users", type=int, default=60)
    ap.add_argument("--rounds", type=int, default=4)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--weights", default="0,0.15,0.3,0.5,1.0")
    ap.add_argument("--decay", type=float, default=0.5)
    ap.add_argument("--tau", type=float, default=0.3, help="choice temperature (0 = argmax)")
    ap.add_argument("--strength", type=float, default=1.0, help="weight of taste vs attribute relevance")
    ap.add_argument("--out", default="reports/ablation")
    a = ap.parse_args()

    from engine02.catalog import Catalog
    from engine02.config import ARMS
    from engine02.contracts import (ChoiceRecord, Engine02Options, Engine02Request, FeedbackState,
                                    HardConstraints, Slot, SlotState)
    from engine02.eval.tasks import make_queries
    from engine02.pipeline import Engine02

    cat = Catalog.load(ROOT / a.catalog)
    if a.encoder == "hash":
        from engine02.encoders import HashEncoder

        enc = HashEncoder(dim=256, captions={Path(p).name: t for p, t in zip(cat.items["image_path"], cat.texts())})
    else:
        from engine02.models import TorchEncoder

        enc = TorchEncoder(a.encoder, device=a.device)
    eng = Engine02(cat, enc, cache_dir=ROOT / a.catalog / "index")
    base_arm = ARMS[a.arm]
    c_mat = eng.design_matrix(base_arm)
    K = eng.kansei.K

    queries = make_queries(cat.items, n=a.users)
    rng = np.random.default_rng(SEED)
    users = []
    for q in queries:
        p_star = rng.dirichlet(np.full(len(eng.kansei.need_ids), 0.3))
        taste = p_star @ K + 0.3 * rng.normal(size=K.shape[1])
        grades = q.grades(cat.items)
        users.append(dict(q=q, taste=taste, grades=grades,
                          gumbel=rng.gumbel(size=len(cat))))

    def utility(user) -> np.ndarray:
        raw = c_mat @ user["taste"]
        z = (raw - raw.mean()) / (raw.std() + 1e-9)
        rel = np.zeros(len(cat))
        ids = cat.column("item_id")
        pos_by_id = {str(v): i for i, v in enumerate(ids)}
        for iid, g in user["grades"].items():
            i = pos_by_id.get(str(iid))
            if i is not None:
                rel[i] = g
        return rel + a.strength * z

    def _slot(vals):
        return Slot(state=SlotState.VALUE, values=list(vals))

    weights = [float(w) for w in a.weights.split(",")]
    rows = []
    for w in weights:
        arm = replace(base_arm, name=f"{a.arm}_fat{w}", use_fatigue=w > 0, w_fatigue=w,
                      fatigue_decay=a.decay)
        for ui, user in enumerate(users):
            q = user["q"]
            u = utility(user)
            history: list[ChoiceRecord] = []
            seen: set[str] = set()
            per_round = []
            for rnd in range(a.rounds):
                fb = FeedbackState(choice_history=list(history),
                                   chosen_item_ids=[history[-1].chosen_item_id] if history and
                                   history[-1].chosen_item_id else [])
                req = Engine02Request(
                    session_id=f"u{ui}", round=rnd, retrieval_text=q.text(False),
                    constraints=HardConstraints(category=_slot([q.category]), gender=_slot([q.gender])),
                    feedback=fb,
                    options=Engine02Options(top_k=a.k, explain_with_llm=False, counterfactual_check=False))
                resp = eng.run(req, arm)
                shown = [it.item_id for it in resp.items]
                if not shown:
                    break
                pos = [cat.pos(i) for i in shown]
                pos = [p for p in pos if p is not None]
                novel = sum(i not in seen for i in shown) / len(shown)
                util = float(np.mean([u[p] for p in pos])) if pos else float("nan")
                best = float(np.max([u[p] for p in pos])) if pos else float("nan")
                # the user picks by noisy utility; everything else shown is simply ignored
                scores = [u[p] / max(a.tau, 1e-9) + (user["gumbel"][p] if a.tau > 0 else 0.0) for p in pos]
                pick = shown[int(np.argmax(scores))]
                per_round.append(dict(round=rnd, novelty=novel, utility_mean=util, utility_max=best,
                                      found_target=float(any(user["grades"].get(i, 0) >= 3 for i in shown))))
                seen.update(shown)
                history.append(ChoiceRecord(shown_item_ids=shown, chosen_item_id=pick))
            for r in per_round:
                rows.append(dict(w_fatigue=w, user=ui, **r))
        print(f"w={w} done", flush=True)

    df = pd.DataFrame(rows)
    last = df[df["round"] == df["round"].max()]
    piv_nov = last.pivot_table(index="user", columns="w_fatigue", values="novelty")
    piv_util = last.pivot_table(index="user", columns="w_fatigue", values="utility_mean")
    piv_found = last.pivot_table(index="user", columns="w_fatigue", values="found_target")
    base_w = weights[0]
    summary = []
    for w in weights:
        summary.append(dict(
            w_fatigue=w,
            novelty_last=round(float(piv_nov[w].mean()), 4),
            novelty_all_rounds=round(float(df[df.w_fatigue == w]["novelty"].mean()), 4),
            utility_last=round(float(piv_util[w].mean()), 4),
            found_target_last=round(float(piv_found[w].mean()), 4),
            p_novelty_vs_off=paired_permutation(piv_nov[w], piv_nov[base_w], seed=SEED),
            p_utility_vs_off=paired_permutation(piv_util[w], piv_util[base_w], seed=SEED),
        ))
    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    tag = f"fatigue_{Path(a.catalog).name}_{eng.encoder.name}"
    df.to_csv(out / f"{tag}.csv", index=False)
    sdf = pd.DataFrame(summary)
    (out / f"{tag}.json").write_text(json.dumps(
        {"setup": dict(catalog=a.catalog, encoder=eng.encoder.name, arm=a.arm, users=len(users),
                       rounds=a.rounds, k=a.k, decay=a.decay, tau=a.tau, strength=a.strength),
         "rows": summary}, indent=1), encoding="utf-8")
    print("\n" + sdf.to_string(index=False))
    print("\nAdopt a weight only if novelty rises significantly AND utility does not fall "
          "significantly; the simulator shares features with the ranker, so utility is a guard "
          "rail, not a user study.")


if __name__ == "__main__":
    main()
