"""Backtest the trend forecast: can anything beat "just repeat last year"?

This is the number that decides whether a trend panel is allowed to exist. Rolling-origin
evaluation on real Wikipedia pageview history (fetched by scripts/fetch_trend_history.py), scored
with MASE against a seasonal-naive baseline. A model that cannot get MASE below 1.0 is worse than
repeating last season, and the honest outcome is to say so and ship the baseline.

  python scripts/eval_forecast.py --history data/trends/history/wikipedia_daily_*.json --h 8

Reported per model: mean MASE across series, how many series it wins on, and a paired permutation
test against seasonal naive over the per-series scores (the same test the retrieval experiments
use, so the standard of evidence is the same one).
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402


def to_weekly(points: list[dict], granularity: str = "daily") -> np.ndarray:
    """Daily pageviews → weekly totals; a series that is already weekly is passed through.

    Fashion attention moves on weeks, and a daily series carries a day-of-week cycle that would
    flatter any model that learns it. But summing every 7 points of an ALREADY weekly series turns
    52 weeks into 7 points and silently makes every series too short to backtest — which is exactly
    what happened the first time Pinterest data was fed through here.
    """
    vals = np.array([p["views"] for p in points], dtype=np.float64)
    if str(granularity).lower().startswith("week"):
        return vals
    n = (len(vals) // 7) * 7
    return vals[:n].reshape(-1, 7).sum(axis=1)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--history", default="data/trends/history/wikipedia_daily_*.json")
    ap.add_argument("--h", type=int, default=8, help="forecast horizon in weeks")
    ap.add_argument("--windows", type=int, default=10)
    ap.add_argument("--m", type=int, default=52, help="seasonal period in weeks")
    ap.add_argument("--out", default="reports/forecast")
    a = ap.parse_args()

    from engine02.eval.metrics import bootstrap_ci, paired_permutation_test
    from engine02.forecast import MODELS, backtest

    files = sorted(glob.glob(str(ROOT / a.history)))
    if not files:
        raise SystemExit(f"no history at {a.history}; run scripts/fetch_trend_history.py first")
    doc = json.loads(Path(files[-1]).read_text(encoding="utf-8"))
    print(f"{Path(files[-1]).name}: {doc['n_terms']} 條序列，{doc['granularity']}，"
          f"{doc['start']}–{doc['end']}")
    print(f"回測：h={a.h} 週、m={a.m} 週、{a.windows} 個滾動視窗、MASE 對季節性天真基準\n")

    per_series: dict[str, dict[str, float]] = {}
    for term, s in doc["series"].items():
        y = to_weekly(s["points"], doc.get("granularity", "daily"))
        res = backtest(y, m=a.m, h=a.h, n_windows=a.windows)
        if res.note:
            print(f"  {term:<16} 跳過：{res.note}")
            continue
        per_series[term] = res.mase

    if not per_series:
        raise SystemExit("no series had enough history to backtest")

    models = list(MODELS)
    print(f"{'model':<18} {'mean MASE':>10} {'median':>8} {'贏過基準':>9} {'vs seasonal_naive':>20}")
    rows = {}
    base = np.array([per_series[t]["seasonal_naive"] for t in per_series])
    for mname in models:
        vals = np.array([per_series[t].get(mname, np.nan) for t in per_series], dtype=np.float64)
        ok = np.isfinite(vals) & np.isfinite(base)
        wins = int(np.sum(vals[ok] < base[ok]))
        if mname == "seasonal_naive":
            cmp_ = "—"
            p = float("nan")
        else:
            p = paired_permutation_test(vals[ok], base[ok], n_perm=20000)
            d = float(np.mean(vals[ok] - base[ok]))
            lo, hi = bootstrap_ci(vals[ok] - base[ok])
            cmp_ = f"{d:+.3f} [{lo:+.3f},{hi:+.3f}] p={p:.4f}"
        rows[mname] = {"mean_mase": float(np.nanmean(vals)), "median_mase": float(np.nanmedian(vals)),
                       "wins_vs_seasonal_naive": wins, "n_series": int(ok.sum()),
                       "p_vs_seasonal_naive": None if mname == "seasonal_naive" else p}
        print(f"{mname:<18} {np.nanmean(vals):10.3f} {np.nanmedian(vals):8.3f} "
              f"{wins:>4}/{int(ok.sum()):<4} {cmp_:>20}")

    # The baseline that matters is the one that actually wins, not the one that flatters us.
    # On attention series seasonal naive is usually the WEAKEST baseline (acf(52) is far below
    # acf(1)), so beating it says very little on its own.
    baselines = ("naive", "seasonal_naive", "drift")
    strongest = min(baselines, key=lambda m: rows[m]["mean_mase"])
    candidates = [m for m in models if m not in baselines]
    best = min(candidates, key=lambda m: rows[m]["mean_mase"])
    bvals = np.array([per_series[t][strongest] for t in per_series], dtype=np.float64)
    cvals = np.array([per_series[t][best] for t in per_series], dtype=np.float64)
    ok2 = np.isfinite(bvals) & np.isfinite(cvals)
    p_strong = paired_permutation_test(cvals[ok2], bvals[ok2], n_perm=20000)
    lo2, hi2 = bootstrap_ci(cvals[ok2] - bvals[ok2])
    wins2 = int(np.sum(cvals[ok2] < bvals[ok2]))

    print(f"\n最強的基準是 {strongest}（平均 MASE {rows[strongest]['mean_mase']:.3f}），"
          f"不是季節性天真（{rows['seasonal_naive']['mean_mase']:.3f}）")
    if rows[best]["mean_mase"] >= rows[strongest]["mean_mase"]:
        verdict = (f"沒有任何模型贏過最強基準 {strongest}——誠實的結論是直接用它，"
                   f"而故事是這個回測本身")
    else:
        verdict = (f"{best} 平均 MASE {rows[best]['mean_mase']:.3f} < 最強基準 {strongest} "
                   f"{rows[strongest]['mean_mase']:.3f}"
                   f"（差 {cvals[ok2].mean() - bvals[ok2].mean():+.3f}，"
                   f"CI [{lo2:+.3f},{hi2:+.3f}]，{wins2}/{int(ok2.sum())} 條，p={p_strong:.4f}）")
    print(f"判定：{verdict}")
    rows["_strongest_baseline"] = {"name": strongest,
                                   "mean_mase": rows[strongest]["mean_mase"],
                                   "best_model": best,
                                   "delta": float(cvals[ok2].mean() - bvals[ok2].mean()),
                                   "ci": [lo2, hi2], "wins": wins2,
                                   "n_series": int(ok2.sum()), "p": p_strong}

    # the per-series table matters: an average hides the series where the method fails
    print(f"\n{'term':<16} {'seasonal_naive':>14} {'best model':>18} {'best MASE':>10}")
    for t, sc in sorted(per_series.items(), key=lambda kv: kv[1]["seasonal_naive"]):
        bm = min(sc, key=lambda k: sc[k] if np.isfinite(sc[k]) else np.inf)
        print(f"{t:<16} {sc['seasonal_naive']:14.3f} {bm:>18} {sc[bm]:10.3f}")

    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    (out / f"backtest_h{a.h}.json").write_text(json.dumps(
        {"setup": {"source": doc["source"], "granularity": "weekly (summed from daily)",
                   "h_weeks": a.h, "m_weeks": a.m, "windows": a.windows,
                   "n_series": len(per_series), "start": doc["start"], "end": doc["end"]},
         "models": rows, "per_series": per_series, "verdict": verdict}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    print(f"\nwrote {out / f'backtest_h{a.h}.json'}")


if __name__ == "__main__":
    main()
