"""Multi-year history for the trend terms, so a forecast can be BACKTESTED rather than asserted.

`scripts/fetch_trends.py` takes a snapshot of today. A snapshot cannot be evaluated: with one point
there is no way to tell a forecast from a guess. This pulls the full daily history of the same
Wikipedia articles (Wikimedia Pageviews REST, keyless, data CC0, anonymous limit 10 req/min) and
writes one tidy series per term.

    python scripts/fetch_trend_history.py --start 20190101 --granularity daily
    python scripts/fetch_trend_history.py --terms satin,linen --dry-run

Why Wikipedia and not Google Trends: `pytrends` was archived read-only on 2025-04-17 and the
endpoint it wrapped returns 429 to every user agent we tried (see docs/research/live-trend-sources.md).
Wikimedia answers, is licensed for redistribution, and gives years of daily data in one call.

**What this measures is attention, not demand.** A spike can be a film release, a news story, or a
Welsh town called Cardigan — that row is kept deliberately as a counter-example. Everything
downstream must carry that caveat.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

API = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
       "{project}/all-access/user/{article}/{granularity}/{start}/{end}")

# Wikimedia asks for a contactable agent and rate-limits anonymous callers to 10 req/min
UA = ("mchackathon2026-engine02/0.1 (academic hackathon project; "
      "https://github.com/chrislaiisme/mchackathon2026)")
SLEEP_S = 6.5


def load_vocab() -> list[dict]:
    """The same article list fetch_trends.py verified one by one (a guessed title is a 404)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("fetch_trends", ROOT / "scripts" / "fetch_trends.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return [v for v in mod.VOCAB if v.get("wiki")]


def fetch_article(article: str, start: str, end: str, granularity: str, project: str,
                  timeout: float = 20.0) -> list[dict]:
    url = API.format(project=project, article=urllib.parse.quote(article, safe=""),
                     granularity=granularity, start=start, end=end)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        payload = json.loads(r.read().decode("utf-8"))
    return [{"date": it["timestamp"][:8], "views": int(it["views"])} for it in payload.get("items", [])]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default="20190101")
    ap.add_argument("--end", default=datetime.now(timezone.utc).strftime("%Y%m%d"))
    ap.add_argument("--granularity", default="daily", choices=("daily", "monthly"))
    ap.add_argument("--project", default="en.wikipedia")
    ap.add_argument("--terms", default="", help="comma-separated subset of terms")
    ap.add_argument("--out", default="data/trends/history")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    vocab = load_vocab()
    if a.terms:
        want = {t.strip().lower() for t in a.terms.split(",") if t.strip()}
        vocab = [v for v in vocab if v["term"].lower() in want]
    if not vocab:
        raise SystemExit("no terms selected")

    print(f"{len(vocab)} 個條目，{a.start}–{a.end}，{a.granularity}，每次間隔 {SLEEP_S}s "
          f"（Wikimedia 匿名限制 10 req/min）")
    for v in vocab:
        print(f"  {v['term']:<16} → {v['wiki']}")
    if a.dry_run:
        print("\n--dry-run：不發出任何請求")
        return

    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    series, failed = {}, []
    for i, v in enumerate(vocab):
        try:
            points = fetch_article(v["wiki"], a.start, a.end, a.granularity, a.project)
            series[v["term"]] = {"term": v["term"], "wiki": v["wiki"], "kind": v["kind"],
                                 "target": v["target"], "risk": v.get("risk", ""),
                                 "points": points}
            print(f"  [{i + 1}/{len(vocab)}] {v['term']:<16} {len(points)} 點 "
                  f"({points[0]['date']}–{points[-1]['date']})" if points else
                  f"  [{i + 1}/{len(vocab)}] {v['term']:<16} 0 點", flush=True)
        except urllib.error.HTTPError as e:
            failed.append({"term": v["term"], "wiki": v["wiki"], "status": e.code})
            print(f"  [{i + 1}/{len(vocab)}] {v['term']:<16} HTTP {e.code}", flush=True)
        except Exception as e:  # noqa: BLE001 — one bad article must not lose the rest
            failed.append({"term": v["term"], "wiki": v["wiki"], "error": f"{type(e).__name__}: {e}"})
            print(f"  [{i + 1}/{len(vocab)}] {v['term']:<16} {type(e).__name__}", flush=True)
        if i < len(vocab) - 1:
            time.sleep(SLEEP_S)

    doc = {
        "source": "wikimedia_pageviews",
        "license": "CC0 (Wikimedia pageviews)",
        "project": a.project,
        "granularity": a.granularity,
        "start": a.start, "end": a.end,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "measures": "attention (pageviews), NOT demand — a spike may be a film, a news story, "
                    "or a Welsh town called Cardigan",
        "affects_score": False,
        "n_terms": len(series), "failed": failed,
        "series": series,
    }
    dst = out / f"wikipedia_{a.granularity}_{a.start}_{a.end}.json"
    dst.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    total = sum(len(s["points"]) for s in series.values())
    print(f"\n{len(series)} 條序列、{total} 個資料點 → {dst}")
    if failed:
        print(f"失敗 {len(failed)}：{[f['term'] for f in failed]}")


if __name__ == "__main__":
    main()
