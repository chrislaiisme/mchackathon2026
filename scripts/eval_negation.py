"""§3.35: when the user says 「不要黑色」 in plain text, does the next slate still show black?

The failure this measures is specific and easy to hide: a CLIP-family encoder is near chance on
negation (NegBench, ICML 2025), so a negated phrase left inside `retrieval_text` does not remove
anything — and the system answers 200 with a confident explanation while showing exactly what the
user just rejected.

For each query we take the colour that dominates its own baseline top-5, append 「不要<那個顏色>」
in Chinese, and compare two arms on the identical text:

  full_zclip3        resolves the negation against the catalog vocabulary and enforces it
  full_zclip3_noneg  today's behaviour: warn, and rank as if the words were positive

Reported:
  violation@5   share of the top 5 that still shows the rejected colour  (lower is better)
  empty_rate    how often enforcing it leaves the user with nothing      (must stay 0)
  ndcg5         relevance against the original grades                    (the cost of obeying)

  python scripts/eval_negation.py --catalog data/catalog/kagl_polyvore_filled \
      --encoder marqo-fashionSigLIP --device cuda --n-queries 100
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

# the Chinese word we put in the query for each catalog colour family
ZH_FOR = {"black": "黑色", "white": "白色", "grey": "灰色", "blue": "藍色", "red": "紅色",
          "pink": "粉色", "purple": "紫色", "green": "綠色", "yellow": "黃色",
          "orange": "橘色", "brown": "咖啡色", "beige": "米色"}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--catalog", default="data/catalog/kagl")
    ap.add_argument("--encoder", default="hash")
    ap.add_argument("--device", default="auto")
    ap.add_argument("--n-queries", type=int, default=100)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--out", default="reports/ablation/negation")
    a = ap.parse_args()

    from engine02.attribute_fill import color_family
    from engine02.catalog import Catalog
    from engine02.contracts import Engine02Options, Engine02Request
    from engine02.eval.metrics import bootstrap_ci, ndcg_at_k, paired_permutation_test
    from engine02.eval.tasks import make_queries
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
    items = cat.items

    def run(text: str, arm: str, k: int):
        req = Engine02Request(session_id="neg", retrieval_text=text,
                              options=Engine02Options(top_k=k, explain_with_llm=False,
                                                      counterfactual_check=False))
        resp = eng.run(req, arm)
        return resp

    rows = []
    for q in make_queries(items, n=a.n_queries):
        grades = q.grades(items)
        base_text = q.text(False)
        base = run(base_text, "full_zclip3_noneg", a.k)
        asked = color_family(getattr(q, "color", None))
        fams = [color_family(it.color) for it in base.items]
        # never reject the colour the query itself asked for: that is a contradiction, not a
        # negation, and it would show up as a huge (meaningless) relevance drop
        common = [f for f, _ in Counter([f for f in fams if f and f != asked]).most_common(1)]
        if not common or common[0] not in ZH_FOR:
            continue                      # nothing dominant to reject; skip rather than invent one
        fam = common[0]
        text = f"{base_text}，不要{ZH_FOR[fam]}"
        for arm in ("full_zclip3_noneg", "full_zclip3"):
            resp = run(text, arm, a.k)
            ids = [it.item_id for it in resp.items]
            shown = [color_family(it.color) for it in resp.items]
            rows.append(dict(qid=q.qid, arm=arm, rejected=fam, n_items=len(ids),
                             violations=sum(1 for f in shown if f == fam),
                             violation_rate=(sum(1 for f in shown if f == fam) / len(ids)) if ids else 0.0,
                             empty=int(not ids),
                             relaxed=";".join(resp.constraint_report.relaxed),
                             honoured=len(resp.constraint_report.honoured_negations),
                             ndcg5=ndcg_at_k(ids, grades, a.k)))

    df = pd.DataFrame(rows)
    if df.empty:
        raise SystemExit("no query had a dominant colour to reject")
    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    tag = f"negation_{Path(a.catalog).name}_{enc.name}"
    df.to_csv(out / f"{tag}.csv", index=False)

    piv_v = df.pivot(index="qid", columns="arm", values="violation_rate")
    piv_n = df.pivot(index="qid", columns="arm", values="ndcg5")
    on, off = "full_zclip3", "full_zclip3_noneg"
    p_v = paired_permutation_test(piv_v[on].to_numpy(), piv_v[off].to_numpy(), n_perm=20000)
    p_n = paired_permutation_test(piv_n[on].to_numpy(), piv_n[off].to_numpy(), n_perm=20000)
    lo_v, hi_v = bootstrap_ci((piv_v[on] - piv_v[off]).to_numpy())
    lo_n, hi_n = bootstrap_ci((piv_n[on] - piv_n[off]).to_numpy())

    print(f"\n=== 「不要X」 written in plain text, {len(piv_v)} queries, top {a.k}")
    print(f"{'arm':<20} {'violation@' + str(a.k):>13} {'empty':>7} {'ndcg' + str(a.k):>8} {'fired':>7}")
    for arm in (off, on):
        g = df[df.arm.eq(arm)]
        print(f"{arm:<20} {g.violation_rate.mean():13.3f} {g["empty"].mean():7.3f} "
              f"{g.ndcg5.mean():8.4f} {g.honoured.gt(0).mean():7.2f}")
    print(f"\nviolation@{a.k}: {piv_v[on].mean() - piv_v[off].mean():+.3f} "
          f"CI[{lo_v:+.3f},{hi_v:+.3f}] p={p_v:.5f}   (negative = the exclusion is being honoured)")
    print(f"ndcg{a.k}:        {piv_n[on].mean() - piv_n[off].mean():+.4f} "
          f"CI[{lo_n:+.4f},{hi_n:+.4f}] p={p_n:.5f}   (the price of obeying)")

    (out / f"{tag}.json").write_text(json.dumps(
        {"setup": dict(catalog=a.catalog, encoder=enc.name, queries=int(len(piv_v)), k=a.k),
         "arms": {arm: dict(violation_rate=round(float(df[df.arm.eq(arm)].violation_rate.mean()), 4),
                            empty_rate=round(float(df[df.arm.eq(arm)]["empty"].mean()), 4),
                            ndcg5=round(float(df[df.arm.eq(arm)].ndcg5.mean()), 4),
                            fired=round(float(df[df.arm.eq(arm)].honoured.gt(0).mean()), 4))
                  for arm in (off, on)},
         "paired": {"violation_rate": dict(delta=round(float(piv_v[on].mean() - piv_v[off].mean()), 4),
                                           ci=[round(lo_v, 4), round(hi_v, 4)], p=round(p_v, 5)),
                    "ndcg5": dict(delta=round(float(piv_n[on].mean() - piv_n[off].mean()), 4),
                                  ci=[round(lo_n, 4), round(hi_n, 4)], p=round(p_n, 5))}}, indent=1),
        encoding="utf-8")
    print(f"\nwrote {out / (tag + '.json')}")


if __name__ == "__main__":
    main()
