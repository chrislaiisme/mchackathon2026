"""Write engine02.price_estimate's labelled estimates into a catalog's items.parquet.

    python scripts/estimate_prices.py --catalog data/catalog/hm_filled

The service already estimates missing prices when it loads a catalog (Catalog.load), so this is
only for people who read items.parquet directly (frontend, other engines): after it, every row has
`price`, `currency`, `price_twd`, `price_estimated` and `price_basis`. Listed prices are never
changed; estimates are recomputed from the current rules, so running it twice gives the same file.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine02.price_estimate import ESTIMATOR_VERSION, fill_missing_prices  # noqa: E402


def main(argv: list[str] | None = None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--catalog", required=True, type=Path)
    a = ap.parse_args(argv)
    f = a.catalog / "items.parquet"
    df, n = fill_missing_prices(pd.read_parquet(f))
    df.to_parquet(f, index=False)
    est = df["price_estimated"].astype(bool)
    out = {"catalog": str(a.catalog), "estimator": ESTIMATOR_VERSION, "n_items": len(df),
           "estimated_this_run": n, "estimated_total": int(est.sum()), "listed": int((~est).sum()),
           "median_twd_by_category": {k: float(v) for k, v in
                                      df.groupby("category")["price_twd"].median().round().items()}}
    stats = a.catalog / "stats.json"
    if stats.exists():
        s = json.loads(stats.read_text(encoding="utf-8"))
        s["price"] = {k: out[k] for k in ("estimator", "estimated_total", "listed", "median_twd_by_category")}
        s.setdefault("attr_coverage", {})["price"] = 1.0
        stats.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False))
    return out


if __name__ == "__main__":
    main()
