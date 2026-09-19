"""Fetch external context (weather) ONCE, into a local file the serving path can read.

Why a side-car and not a call inside /rank: measured from Taipei, Open-Meteo's cold connection is
p50 **1.57 s** (TLS handshake alone ~0.95 s) and a warm one is 0.295 s, against a /rank that is
12.8 ms (§3.21) inside a 1.5 s per-request budget — and the demo runs with ENGINE02_DEMO=1, which
has no network on the serving path at all. So the network call happens here, before the demo or on
a timer, and the request path only ever reads a small JSON file.

  python scripts/fetch_context.py --city Hsinchu --lat 24.8 --lon 120.97
  python scripts/fetch_context.py --city Hsinchu --lat 24.8 --lon 120.97 --every 900   # refresher

Writes data/context/weather.json. GET /context serves it, says how old it is, and returns the
`constraints.season` value a caller MAY attach — ENGINE 02 never attaches it itself, because
season is the caller's statement about the user, not ours.

What this is NOT: a ranking term. docs/research/context-weather-recsys.md measures why — on this
catalog `season` is not a wearing-season label (756 Winter items include 294 watches and 144
sunglasses; sweaters are 0% Winter), so a weather score term cannot be validated and would be
decoration. This ships the plumbing, honestly labelled, so a catalog with material and thickness
can turn it on with evidence later.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Open-Meteo: no API key, 10k/day, data CC-BY-4.0. Verified 2026-09-18.
URL = ("https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
       "&current=temperature_2m,precipitation,weather_code"
       "&daily=temperature_2m_max,temperature_2m_min,precipitation_sum&forecast_days=2"
       "&timezone=auto")

# Northern-hemisphere apparel seasons by daily mean temperature. Deliberately coarse: this only
# decides which word the CALLER may put in a soft slot, and the doc explains why nothing finer
# can be justified on a catalog without material or thickness.
def season_for(temp_c: float) -> str:
    if temp_c >= 26:
        return "Summer"
    if temp_c >= 20:
        return "Spring"
    if temp_c >= 14:
        return "Fall"
    return "Winter"


def fetch(lat: float, lon: float, timeout: float = 8.0) -> dict:
    with urllib.request.urlopen(URL.format(lat=lat, lon=lon), timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def build(city: str, lat: float, lon: float, timeout: float) -> dict:
    t0 = time.perf_counter()
    raw = fetch(lat, lon, timeout)
    ms = (time.perf_counter() - t0) * 1000
    cur = raw.get("current", {})
    daily = raw.get("daily", {})
    hi = (daily.get("temperature_2m_max") or [None])[0]
    lo = (daily.get("temperature_2m_min") or [None])[0]
    mean = (hi + lo) / 2 if (hi is not None and lo is not None) else cur.get("temperature_2m")
    return {
        "source": "open-meteo.com (CC-BY-4.0, no key)",
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fetch_ms": round(ms, 1),
        "city": city, "lat": lat, "lon": lon,
        "temperature_c": cur.get("temperature_2m"),
        "precipitation_mm": cur.get("precipitation"),
        "today_high_c": hi, "today_low_c": lo,
        "suggested_season": season_for(float(mean)) if mean is not None else None,
        "how_to_use": ("呼叫端可把 suggested_season 放進 constraints.season 且 state=\"inferred\"："
                       "那是軟訊號（不會砍候選池），ENGINE 02 不會自己加，因為季節是呼叫端對使用者的判斷。"),
        "not_a_ranking_term": ("這不是分數項。docs/research/context-weather-recsys.md 量過：本商品庫的 "
                               "season 標籤不是體感季節（756 件 Winter 裡有 294 支手錶），因此無法驗證。"),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--city", default="Hsinchu")
    ap.add_argument("--lat", type=float, default=24.8038)
    ap.add_argument("--lon", type=float, default=120.9686)
    ap.add_argument("--out", default="data/context/weather.json")
    ap.add_argument("--timeout", type=float, default=8.0)
    ap.add_argument("--every", type=float, default=0.0, help="seconds between refreshes; 0 = once")
    a = ap.parse_args()

    dst = ROOT / a.out
    dst.parent.mkdir(parents=True, exist_ok=True)
    while True:
        try:
            ctx = build(a.city, a.lat, a.lon, a.timeout)
            dst.write_text(json.dumps(ctx, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"{ctx['fetched_at']}  {ctx['city']} {ctx['temperature_c']}°C "
                  f"→ season={ctx['suggested_season']}  ({ctx['fetch_ms']:.0f} ms)  -> {dst}", flush=True)
        except Exception as e:  # the demo must survive a dead network without any special case
            print(f"could not fetch context ({type(e).__name__}: {e}); leaving the previous file "
                  f"alone — /context will report its age and the caller can ignore it", flush=True)
            if not dst.exists():
                sys.exit(1)
        if a.every <= 0:
            return
        time.sleep(a.every)


if __name__ == "__main__":
    main()
