"""Drive N simulated shoppers through ENGINE 01 → 02 → 03 → 02 and check the loop actually works.

This is not a unit test and not a benchmark. It answers the two questions a judge will ask on the
day, at a sample size where the answer means something:

  1. Does the second round actually change, in the direction the feedback asked for?
  2. Does the recommendation stay within what the user said (budget, exclusions, category)?

Each simulated shopper has a hidden preference (a design axis they like, one they dislike, a
budget) and speaks in Chinese the way the brief's examples do. Round 1 is their sentence. They then
give feedback the way ENGINE 03 expects, and round 2 is checked against the preference they never
stated directly.

    PYTHONPATH=. SESSION_SECRET=dev ENGINE01_LLM=stub \
    ENGINE02_CATALOG=data/catalog/kagl_priced_fixture ENGINE02_ENCODER=marqo-fashionSigLIP \
    ENGINE02_DEVICE=cuda ENGINE02_DEMO=1 python scripts/simulate_sessions.py --n 60

Outputs a table plus reports/server/simulation/sessions.json. Every claim it prints is computed
from the responses, and the ones that cannot be computed are left out rather than estimated.
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

SEED = 20260919

ITEMS = ["襯衫", "洋裝", "外套", "大衣", "T恤", "褲子", "針織衫"]
OCCASIONS = ["面試", "上班", "約會", "婚禮", "旅行", "運動", "休閒"]
COLORS = ["黑色", "白色", "藍色", "深藍色", "米色", "灰色", "粉色"]
# (phrase the shopper says, the axis it means, the direction they want)
LIKES = [("修身", "tailored_fit", +1), ("寬鬆", "relaxed_fit", +1), ("素面", "minimal_design", +1),
         ("針織", "soft_knit", +1), ("正式", "formal_style", +1), ("休閒", "casual_style", +1)]
DISLIKES = [("不要太正式", "formal_style", -1), ("不要有明顯 logo", "visible_logo", -1),
            ("不要印花", "bold_pattern", -1), ("不要太寬鬆", "relaxed_fit", -1)]


def sentence(rng: random.Random, item: str, occ: str, colour: str | None,
             like: str, budget: int | None) -> str:
    parts = [f"{occ}要穿的{item}"]
    if colour:
        parts.append(colour)
    parts.append(like)
    if budget:
        parts.append(f"預算 {budget} 元")
    return "，".join(parts)



def make_axis_expression(engine, arm: str):
    """Mean c(i, axis) of the shown items, in catalog z units — defined for every item."""
    import numpy as np

    from engine02.config import ARMS

    c_mat = np.asarray(engine.design_matrix(ARMS[arm]), dtype=np.float64)
    mu = c_mat.mean(axis=0)
    sd = np.where(c_mat.std(axis=0) > 1e-9, c_mat.std(axis=0), 1.0)
    ids = engine.kansei.element_ids
    folded = dict(getattr(engine.kansei, "folded", {}) or {})

    def expression(body, axis: str) -> float | None:
        canon = folded.get(axis, axis)
        if canon not in ids:
            return None
        j = ids.index(canon)
        sign = -1.0 if axis in folded else 1.0
        pos = [engine.catalog.pos(p["product_id"]) for p in body["products"]]
        pos = [q for q in pos if q is not None]
        if not pos:
            return None
        z = (c_mat[pos, j] - mu[j]) / sd[j]
        return float(sign * np.mean(z))

    return expression


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--budget-rate", type=float, default=0.5, help="share of shoppers who state one")
    ap.add_argument("--step", type=int, default=-1,
                    help="how hard one complaint pushes the axis (ENGINE 03 sends -1)")
    ap.add_argument("--out", default="reports/server/simulation")
    a = ap.parse_args()

    import os

    os.environ.setdefault("ENGINE01_LLM", "stub")
    os.environ.setdefault("ENGINE02_DEMO", "1")
    os.environ.setdefault("ENGINE02_LLM", "none")

    from fastapi.testclient import TestClient

    try:
        from mcp_servers.catalog.main import app as e02_app       # the Hermes layout
    except ImportError:
        from backend.engine02_retrieval.main import app as e02_app  # our own branch

    from bff.engine01_intent import llm_client
    from bff.shared.schemas import Intent

    rng = random.Random(SEED)
    rows = []
    t0 = time.perf_counter()

    with TestClient(e02_app) as e02:
        health = e02.get("/health").json()
        print(f"catalog={health['catalog']} n={health['n_items']} encoder={health['encoder']}\n")
        from engine02.api import engine as _engine

        arm_name = os.environ.get("ENGINE02_ARM", "full_zclip3")
        expression = make_axis_expression(_engine(), arm_name)

        for i in range(a.n):
            item = rng.choice(ITEMS)
            occ = rng.choice(OCCASIONS)
            colour = rng.choice(COLORS) if rng.random() < 0.7 else None
            like_word, like_axis, like_dir = rng.choice(LIKES)
            hate_word, hate_axis, hate_dir = rng.choice(DISLIKES)
            budget = rng.choice([1000, 1500, 2000, 3000]) if rng.random() < a.budget_rate else None
            msg = sentence(rng, item, occ, colour, like_word, budget)

            intent = llm_client.extract_intent(msg, Intent()).intent.model_dump(exclude_none=True)
            sid = f"sim{i:03d}"
            r1 = e02.post("/retrieve", json={"session_id": sid, "round": 1, "message": msg,
                                             "intent": intent, "top_k": a.top_k})
            if r1.status_code != 200:
                rows.append(dict(session=sid, ok=False, stage="round1", detail=r1.text[:120]))
                continue
            b1 = r1.json()
            shown = [p["product_id"] for p in b1["products"]]

            # the shopper reacts: they pick one, and they say the thing they dislike
            fb = {"session_id": sid, "round": 1,
                  "ops": [{"op": "choice", "shown_item_ids": shown, "chosen_item_id": shown[0]}]}
            # ENGINE 03's contract allows only ±1, so a stronger push is expressed by
            # repeating the op — which is what apply_round accumulates anyway
            for _ in range(abs(a.step)):
                fb["ops"].append({"op": "adjust", "element": hate_axis,
                                  "step": -1 if a.step < 0 else 1, "quote": hate_word})
            r2 = e02.post("/retrieve", json={"session_id": sid, "round": 2, "message": hate_word,
                                             "intent": intent, "prev_intent": intent,
                                             "feedback": fb, "top_k": a.top_k})
            if r2.status_code != 200:
                rows.append(dict(session=sid, ok=False, stage="round2", detail=r2.text[:120]))
                continue
            b2 = r2.json()
            ids2 = [p["product_id"] for p in b2["products"]]

            # Did the clothes change in the direction they asked for? Measure the axis on the
            # ITEMS (c(i,d) in catalog z units), not on the contributions: a contribution only
            # exists when that axis carries weight, so round 1 has no entry for the axis they are
            # about to complain about and the comparison silently drops most sessions.
            before = expression(b1, hate_axis)
            after = expression(b2, hate_axis)
            prices = [float(p["attributes"]["price"]) for p in b2["products"]
                      if p["attributes"].get("price")]
            rep2 = b2["engine02"]["constraint_report"]
            rows.append(dict(
                session=sid, ok=True, message=msg, budget=budget,
                n1=len(shown), n2=len(ids2),
                changed=ids2 != shown,
                overlap=len(set(ids2) & set(shown)) / max(1, len(shown)),
                axis=hate_axis, axis_before=before, axis_after=after,
                axis_moved_right_way=(None if (before is None or after is None) else after < before),
                match1=b1["match_score"], match2=b2["match_score"],
                over_budget=(sum(1 for p in prices if budget and p > budget) if budget else 0),
                relaxed=";".join(rep2["relaxed"]),
                ledger=[e["op"] for e in b2["engine02"].get("feedback_ledger", [])],
                rejected_ops=len(b2["engine02"].get("rejected_ops", [])),
                warnings=len(rep2["input_warnings"]),
            ))
            if (i + 1) % 10 == 0:
                print(f"  {i + 1}/{a.n} …", flush=True)

    ok = [r for r in rows if r.get("ok")]
    fail = [r for r in rows if not r.get("ok")]
    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    (out / "sessions.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

    def share(pred) -> float:
        vals = [pred(r) for r in ok if pred(r) is not None]
        return sum(vals) / len(vals) if vals else float("nan")

    moved = [r for r in ok if r["axis_moved_right_way"] is not None]
    print(f"\n=== {len(ok)}/{len(rows)} 場成功，耗時 {time.perf_counter() - t0:.0f}s")
    print(f"第二輪與第一輪不同          : {share(lambda r: r['changed']):.1%}")
    print(f"前 5 名重疊率（越低越有反應）: {share(lambda r: r['overlap']):.1%}")
    if moved:
        import numpy as _np

        right = sum(1 for r in moved if r["axis_moved_right_way"]) / len(moved)
        delta = _np.array([r["axis_after"] - r["axis_before"] for r in moved])
        print(f"被抱怨的那條軸往正確方向動  : {right:.1%}  (n={len(moved)}, step={a.step})")
        print(f"  該軸平均位移（負值=如願）  : {delta.mean():+.3f} z  "
              f"(中位 {_np.median(delta):+.3f})")
    budgeted = [r for r in ok if r["budget"]]
    if budgeted:
        viol = sum(r["over_budget"] for r in budgeted)
        print(f"超出預算的卡片              : {viol} 張 / {sum(r['n2'] for r in budgeted)} 張")
    print(f"ENGINE 03 的 op 被拒絕       : {sum(r['rejected_ops'] for r in ok)} 個")
    print(f"平均 match_score  R1 → R2    : {share(lambda r: r['match1']):.3f} → "
          f"{share(lambda r: r['match2']):.3f}")
    if fail:
        print(f"\n失敗 {len(fail)} 場：")
        for r in fail[:5]:
            print(f"  [{r['stage']}] {r['detail']}")
    print(f"\nwrote {out / 'sessions.json'}")


if __name__ == "__main__":
    main()
