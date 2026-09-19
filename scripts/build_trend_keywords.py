"""Derive a trend keyword list from the catalog itself (no Pinterest, no external service).

  python scripts/build_trend_keywords.py --catalog data/catalog/kagl_polyvore \
      --source curated_lift --top-n 40 --out data/catalog/kagl_polyvore/trend_keywords.json

Sources (see engine02/trends.py for the statistics and the citations):
  curated_lift    terms over-represented in items that human stylists put into outfits
                  (`outfit_ids`), vs the whole catalog — needs a catalog that mixes curated and
                  non-curated items, e.g. the merged `kagl_polyvore`.
  outfit_partner  terms of the items that share an outfit with `--anchor-categories`
                  ("what is styled with a blazer") — contextual, per anchor category.

Why not Pinterest: their developer guidelines forbid storing information obtained from the API
(PRD [108]), so nothing fetched from Pinterest may be written to a file like this one. A live
call is still allowed at request time — `engine02.trends.from_live_fetch` wraps that and marks
the result ephemeral so it cannot be saved.

The output file is data, not code: keep it out of git like every other catalog artefact.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine02.catalog import Catalog  # noqa: E402
from engine02.trends import derive_trends  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default="data/catalog/kagl_polyvore")
    ap.add_argument("--source", default="curated_lift", choices=["curated_lift", "outfit_partner"])
    ap.add_argument("--top-n", type=int, default=40)
    ap.add_argument("--min-df", type=int, default=8)
    ap.add_argument("--anchor-categories", default="outerwear,top",
                    help="outfit_partner only, comma separated")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    cat = Catalog.load(ROOT / args.catalog)
    tk = derive_trends(cat.items, source=args.source, catalog=cat.name, top_n=args.top_n,
                       anchor_categories=[c.strip() for c in args.anchor_categories.split(",") if c.strip()],
                       min_df=args.min_df)
    out = Path(args.out or (ROOT / args.catalog / f"trend_keywords_{args.source}.json"))
    tk.save(out)
    print(json.dumps({"out": str(out), "source": tk.source, "catalog": tk.catalog,
                      "n_terms": len(tk.terms), "top": tk.keywords(15)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
