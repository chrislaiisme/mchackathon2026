"""Pinterest Trends → the same history shape as the Wikipedia series, so the backtest just works.

Pinterest is the one public source here whose users are *planning a purchase* rather than reading
an encyclopedia, and its Trends API returns a **weekly time series per keyword**, not a snapshot —
which is what makes it usable for the rolling-origin backtest in `engine02/forecast.py`.

    python scripts/fetch_pinterest_trends.py --dry-run
    python scripts/fetch_pinterest_trends.py --region US --interests womens_fashion,mens_fashion

The token comes from `PINTEREST_ACCESS_TOKEN` (env or .env, which is gitignored) and is never
written into the output. Output goes to `data/trends/history/pinterest_<region>_<date>.json` in the
same schema as `fetch_trend_history.py`, so `scripts/eval_forecast.py` and `GET /trends/forecast`
read it without a single change.

Limits found by probing the live API (2026-09-19):
  * region must be one of AR, AU+NZ, BR, CA, CO, DE, DE+AT+CH, ES, FR, GB+IE, IT, IT+ES+PT+GR+MT,
    MX, MX+AR+CO+CL, NL+BE+LU, PL+RO+HU+SK+CZ, SE+DK+FI+NO, US — **there is no Taiwan or Asia
    region**, so this describes Western attention and the slide must say so;
  * `interests` accepts womens_fashion / mens_fashion / childrens_fashion / beauty / design (not
    the bare word "fashion");
  * `/v5/search/partner/pins` returns 401 on a standard token — partner access only.

Like every other trend source here, this is **attention, not demand**, and it never enters the
ranking (§3.15).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

API = "https://api.pinterest.com/v5/trends/keywords/{region}/top/{trend_type}"
REGIONS = ("AR", "AU+NZ", "BR", "CA", "CO", "DE", "DE+AT+CH", "ES", "FR", "GB+IE", "IT",
           "IT+ES+PT+GR+MT", "MX", "MX+AR+CO+CL", "NL+BE+LU", "PL+RO+HU+SK+CZ",
           "SE+DK+FI+NO", "US")
INTERESTS = ("womens_fashion", "mens_fashion", "childrens_fashion", "beauty", "design")
TREND_TYPES = ("growing", "monthly", "yearly", "seasonal")


def token() -> str:
    tok = os.environ.get("PINTEREST_ACCESS_TOKEN", "").strip()
    if not tok:
        env = ROOT / ".env"
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                if line.startswith("PINTEREST_ACCESS_TOKEN="):
                    tok = line.split("=", 1)[1].strip()
                    break
    if not tok:
        raise SystemExit("PINTEREST_ACCESS_TOKEN is not set (env or .env). Nothing was requested.")
    return tok


def fetch(region: str, trend_type: str, interests: list[str], limit: int, tok: str) -> list[dict]:
    q = {"trend_type": trend_type, "limit": str(limit)}
    if interests:
        q["interests"] = ",".join(interests)
    url = f"{API.format(region=urllib.parse.quote(region), trend_type=trend_type)}?{urllib.parse.urlencode(q)}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}",
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8")).get("trends", [])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--region", default="US", choices=REGIONS)
    ap.add_argument("--trend-types", default="growing,monthly,yearly",
                    help=f"comma-separated, from {TREND_TYPES}")
    ap.add_argument("--interests", default="womens_fashion,mens_fashion")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--out", default="data/trends/history")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    types = [t.strip() for t in a.trend_types.split(",") if t.strip() in TREND_TYPES]
    interests = [i.strip() for i in a.interests.split(",") if i.strip() in INTERESTS]
    bad = [i.strip() for i in a.interests.split(",") if i.strip() and i.strip() not in INTERESTS]
    if bad:
        raise SystemExit(f"unknown interests {bad}; valid: {INTERESTS}")

    print(f"region={a.region}  trend_types={types}  interests={interests}  limit={a.limit}")
    for t in types:
        print(f"  GET /v5/trends/keywords/{a.region}/top/{t}?interests={','.join(interests)}"
              f"&limit={a.limit}")
    if a.dry_run:
        print("\n--dry-run: nothing was requested")
        return

    tok = token()
    series: dict[str, dict] = {}
    failed = []
    for i, t in enumerate(types):
        try:
            trends = fetch(a.region, t, interests, a.limit, tok)
        except urllib.error.HTTPError as e:
            failed.append({"trend_type": t, "status": e.code, "body": e.read().decode()[:200]})
            print(f"  {t:<10} HTTP {e.code}")
            continue
        for tr in trends:
            kw = tr.get("keyword")
            ts = tr.get("time_series") or {}
            if not kw or not ts:
                continue
            # same shape as fetch_trend_history.py: a date-sorted list of {date, views}
            points = [{"date": d.replace("-", ""), "views": int(v)}
                      for d, v in sorted(ts.items())]
            prev = series.get(kw)
            if prev is None or len(points) > len(prev["points"]):
                series[kw] = {
                    "term": kw, "wiki": None, "kind": "pinterest_keyword",
                    "target": None, "trend_type": t,
                    "risk": "Pinterest 關鍵字是自由文字，未對映到我們的封閉詞彙；"
                            "且地區選項沒有台灣，這是西方市場的注意力",
                    "pct_growth_wow": tr.get("pct_growth_wow"),
                    "pct_growth_mom": tr.get("pct_growth_mom"),
                    "pct_growth_yoy": tr.get("pct_growth_yoy"),
                    "points": points,
                }
        print(f"  {t:<10} {len(trends)} 個關鍵字", flush=True)
        if i < len(types) - 1:
            time.sleep(1.0)

    if not series:
        raise SystemExit("no series returned; nothing written")

    weeks = {len(s["points"]) for s in series.values()}
    doc = {
        "source": "pinterest_trends",
        "license": "Pinterest API terms — 取得需 access token，輸出不得再散布",
        "region": a.region, "interests": interests, "trend_types": types,
        "granularity": "weekly",
        "start": min(s["points"][0]["date"] for s in series.values()),
        "end": max(s["points"][-1]["date"] for s in series.values()),
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "measures": "attention on Pinterest (search/save interest), NOT demand; "
                    "no Taiwan/Asia region is offered by the API",
        "affects_score": False,
        "n_terms": len(series), "failed": failed,
        "series": series,
    }
    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    dst = out / f"pinterest_{a.region.replace('+', '')}_{datetime.now().strftime('%Y%m%d')}.json"
    dst.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    print(f"\n{len(series)} 條序列、每條 {sorted(weeks)} 週 → {dst}")
    top = sorted(series.values(), key=lambda s: -(s.get("pct_growth_yoy") or 0))[:5]
    for s in top:
        print(f"  {s['term'][:34]:<36} YoY {s.get('pct_growth_yoy')}%  ({len(s['points'])} 週)")


if __name__ == "__main__":
    main()
