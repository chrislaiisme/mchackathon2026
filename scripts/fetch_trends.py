"""Fetch a LIVE public trend signal ONCE, into a local file. Side-car, never the serving path.

Why a side-car and not a call inside /rank — exactly the same reason as `scripts/fetch_context.py`
(§3.34): a cold call from Taipei is p50 1.57 s against a `/rank` that is 12.8 ms inside a 1.5 s
budget, and `ENGINE02_DEMO=1` has no network on the serving path at all. So the network happens
here, on a timer, and the request path only ever reads a small JSON file.

  python scripts/fetch_trends.py --source wikipedia
  python scripts/fetch_trends.py --source google_trends --gt-mode rss
  python scripts/fetch_trends.py --source bluesky --window 90
  python scripts/fetch_trends.py --source all --every 21600        # refresher, 6 h
  python scripts/fetch_trends.py --source google_trends --dry-run  # print the exact requests

Writes ``data/trends/<source>_<YYYY-MM-DD>.json`` in the shape `engine02/trends.py` already reads:
``{source, as_of, catalog, notes, terms:[{term, score, df}]}`` → `trends.load_trends(path)` →
`trends.trend_badges(...)`. Extra provenance keys are additive; `TrendKeywords.from_dict` ignores
what it does not know, so the file round-trips.

What this is NOT — and this is the whole point of the file:
  **not a ranking term.** `docs/engine02-design.md` §3.15 measured trend keywords inside the score
  in 28 configurations and all 28 were worse (NDCG@5 −0.16 … −0.38). This writes a DISPLAY signal.
  The JSON says so in `affects_score: false`, and nothing here touches `arm.w_trend`.

Login and terms (checked 2026-09-19, see docs/research/live-trend-sources.md):
  * every endpoint below is reachable **without an account, key, cookie or login**;
  * anything that needs a login (Instagram, TikTok, X, Reddit's OAuth Data API, Pinterest) is
    refused by `refuse_if_login_required()` — this script will not authenticate to anything;
  * Reddit's robots.txt is `User-agent: * / Disallow: /`, so its public JSON is NOT fetched here;
  * Pinterest's developer guidelines forbid *storing* API data, which is what this script does, so
    Pinterest stays out (`engine02/trends.py::from_live_fetch` is the request-time, ephemeral path).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# A descriptive User-Agent with contact info is REQUIRED by Wikimedia's User-Agent policy
# ("Scripts should use an informative User-Agent string with contact information, or they may be
# blocked without notice", revision 2026-03-27) and is simply good manners everywhere else.
UA = ("mchackathon2026-trend-sidecar/0.1 "
      "(academic hackathon, non-commercial; +https://github.com/Evan-Jiamg; ben940815@gmail.com)")

# --- endpoints, each verified reachable without a login on 2026-09-19 from Taipei --------------
WIKI_PAGEVIEWS = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
                  "{proj}/all-access/user/{article}/daily/{start}/{end}")
WIKI_SLEEP = 6.5      # anonymous Wikimedia limit is 10 requests/minute (Wikimedia APIs/Rate limits)

GT_RSS = "https://trends.google.com/trending/rss?geo={geo}"
GT_EXPLORE = "https://trends.google.com/trends/api/explore?hl=en-US&tz={tz}&req={req}"
GT_MULTILINE = "https://trends.google.com/trends/api/widgetdata/multiline?hl=en-US&tz={tz}&req={req}&token={tok}"
GT_SLEEP = 8.0        # no published quota; 8 s between keywords is our self-imposed politeness

BSKY_APPVIEW = "https://public.api.bsky.app/xrpc/{method}"
JETSTREAM = ("wss://jetstream2.us-east.bsky.network/subscribe"
             "?wantedCollections=app.bsky.feed.post")

# Sources that can only be reached by authenticating. We do not authenticate. Ever.
LOGIN_REQUIRED = {
    "reddit": "Reddit's robots.txt is `User-agent: * / Disallow: /`; the only sanctioned route is "
              "the OAuth Data API, which needs a Reddit account + registered app (login).",
    "instagram": "Instagram Graph API needs a Business/Creator account and App Review (login).",
    "tiktok": "TikTok Research API is restricted to approved academic institutions (login).",
    "x": "X/Twitter API is usage-priced with no academic tier (login).",
    "twitter": "X/Twitter API is usage-priced with no academic tier (login).",
    "pinterest": "Pinterest developer guidelines forbid STORING API data — this script stores. "
                 "Use engine02.trends.from_live_fetch() at request time instead (ephemeral).",
    "instaloader": "Scraping Instagram breaches Meta's platform terms (docs/research/"
                   "social4fashion-appraisal.md). Refused.",
}


# ---------------------------------------------------------------------------------------------
# THE MAPPING TABLE — see docs/research/live-trend-sources.md §3 for where each row can lie.
# An external source speaks free text; ENGINE 02 speaks a closed vocabulary. This table IS the
# mapping, written down so it can be argued with, instead of hidden inside a fuzzy matcher.
#   target kinds: "category" = taxonomy_v1 node id | "attr" = attribute_defs slot=value
#                 "element"  = kansei_v1 design element | "color" = free colour token (no slot)
# `risk` is the honest failure mode of that particular row.
# ---------------------------------------------------------------------------------------------
VOCAB: list[dict] = [
    # term (external)      wiki article                target kind/value          risk
    {"term": "trench coat", "wiki": "Trench_coat", "kind": "category", "target": "outerwear.coats",
     "risk": "電影／軍事新聞會拉高，與服飾需求無關"},
    {"term": "blazer", "wiki": "Blazer", "kind": "category", "target": "outerwear.blazers",
     "risk": "英式學校制服語意，非時尚語意"},
    {"term": "cardigan", "wiki": "Cardigan,_Ceredigion", "kind": "category", "target": "tops.cardigans",
     "risk": "同名地名（威爾斯），這一列註定被污染，留著當反例"},
    {"term": "hoodie", "wiki": "Hoodie", "kind": "category", "target": "tops.sweatshirts_hoodies",
     "risk": "社會新聞用語"},
    {"term": "jeans", "wiki": "Jeans", "kind": "category", "target": "bottoms.jeans", "risk": "—"},
    {"term": "sneakers", "wiki": "Sneakers_(footwear)", "kind": "category", "target": "shoes.sneakers",
     "risk": "球鞋轉售新聞 ≠ 服飾需求"},
    {"term": "loafers", "wiki": "Loafer", "kind": "category", "target": "shoes.loafers",
     "risk": "`Loafer_(shoe)` 是 404（2026-09-19 實測）；條目名要一個一個驗，猜不得"},
    {"term": "miniskirt", "wiki": "Miniskirt", "kind": "attr", "target": "length=mini", "risk": "—"},
    {"term": "crop top", "wiki": "Crop_top", "kind": "attr", "target": "length=cropped", "risk": "—"},
    {"term": "turtleneck", "wiki": "Polo_neck", "kind": "attr", "target": "neckline=turtle",
     "risk": "英式條目名 Polo neck，字面與 tops.polos 撞名"},
    {"term": "oversized", "wiki": None, "kind": "attr", "target": "fit=oversized",
     "risk": "純形容詞，wiki 無對應條目；只有 Google Trends 有"},
    {"term": "linen", "wiki": "Linen", "kind": "element", "target": "matte_fabric",
     "risk": "材質→感性軸是有損投影：亞麻≠所有霧面"},
    {"term": "corduroy", "wiki": "Corduroy", "kind": "element", "target": "matte_fabric", "risk": "同上"},
    {"term": "satin", "wiki": "Satin", "kind": "element", "target": "glossy_fabric", "risk": "同上"},
    {"term": "athleisure", "wiki": "Athleisure", "kind": "element", "target": "athletic_style", "risk": "—"},
    {"term": "quiet luxury", "wiki": "Quiet_luxury", "kind": "element", "target": "minimal_design",
     "risk": "媒體造詞，語意逐季漂移；投影到 minimal_design 是我們的判斷不是資料的"},
    {"term": "tailoring", "wiki": "Bespoke_tailoring", "kind": "element", "target": "tailored_fit",
     "risk": "條目談工藝史，不談當季"},
    {"term": "knitwear", "wiki": "Knitting", "kind": "attr", "target": "construction=knit",
     "risk": "Knitting 條目是手工藝，不是成衣需求"},
    {"term": "cargo pants", "wiki": "Cargo_pants", "kind": "category", "target": "bottoms.trousers",
     "risk": "只落到 trousers，cargo 這個設計細節在我們的封閉詞彙裡沒有位置"},
    {"term": "pleated skirt", "wiki": "Pleated_skirt", "kind": "category", "target": "bottoms.skirts",
     "risk": "同上，pleat 無槽位"},
]
WIKI_ARTICLES = [(v["wiki"], v) for v in VOCAB if v.get("wiki")]


# ---------------------------------------------------------------------------------------------
def refuse_if_login_required(source: str) -> None:
    key = source.lower().strip()
    if key in LOGIN_REQUIRED:
        raise SystemExit(
            f"refusing --source {source}: {LOGIN_REQUIRED[key]}\n"
            f"This side-car only fetches endpoints that are public without an account. "
            f"See docs/research/live-trend-sources.md.")


def _get(url: str, timeout: float = 20.0, accept: str = "application/json") -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:      # 429/403 are DATA, not crashes: we record them
        return e.code, e.read()[:400]


def _envelope(name: str, notes: list[str], terms: list[dict], **extra) -> dict:
    """The on-disk shape. Keys `source/as_of/catalog/notes/terms` are what TrendKeywords reads."""
    return {
        "source": f"live:{name}",
        "as_of": date.today().isoformat(),
        "catalog": None,
        "notes": notes,
        "terms": terms,
        "affects_score": False,
        "not_a_ranking_term": (
            "這不是分數項。docs/engine02-design.md §3.15 量過 28 組「趨勢關鍵字進排序」，"
            "全部變差（NDCG@5 −0.16～−0.38）。這份檔案只餵 trends.trend_badges() 的展示標籤，"
            "以及後台需求面板。要進排序必須先有另一套帶時間軸的標準答案（§3.26）。"),
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "user_agent": UA,
        "login_used": False,
        **extra,
    }


# --- Google Trends ----------------------------------------------------------------------------
def plan_google_trends(geo: str, mode: str, tz: int) -> list[str]:
    if mode == "rss":
        return [GT_RSS.format(geo=geo)]
    out = []
    for v in VOCAB:
        req = json.dumps({"comparisonItem": [{"keyword": v["term"], "geo": geo, "time": "today 12-m"}],
                          "category": 0, "property": ""}, separators=(",", ":"))
        out.append(GT_EXPLORE.format(tz=tz, req=urllib.parse.quote(req)))
    return out


def gt_rss(geo: str) -> tuple[list[dict], list[str], dict]:
    """Google's own published RSS of daily trending searches. Documented, no key, no login."""
    code, body = _get(GT_RSS.format(geo=geo), accept="application/rss+xml")
    meta = {"endpoint": GT_RSS.format(geo=geo), "http_status": code, "official": True}
    if code != 200:
        return [], [f"Google Trends RSS 回傳 HTTP {code}，本輪無資料"], meta
    root = ET.fromstring(body)
    ns = {"ht": "https://trends.google.com/trending/rss"}
    raw = []
    for i, item in enumerate(root.iter("item")):
        title = (item.findtext("title") or "").strip()
        traffic = (item.findtext("ht:approx_traffic", default="", namespaces=ns) or "").strip()
        if title:
            raw.append({"title": title, "approx_traffic": traffic, "rank": i})
    # intersect with OUR closed vocabulary — this is the mapping, and it is usually empty
    lowered = [r["title"].lower() for r in raw]
    terms, hits = [], []
    for v in VOCAB:
        for j, t in enumerate(lowered):
            if v["term"] in t:
                terms.append({"term": v["term"], "score": round(10.0 - raw[j]["rank"] * 0.2, 4), "df": 0})
                hits.append({**{k: v[k] for k in ("term", "kind", "target", "risk")},
                             "matched_trending_title": raw[j]["title"]})
                break
    notes = [f"來源：Google Trends 官方公開 RSS（{geo}），無金鑰、無登入，{code}",
             f"當日熱搜 {len(raw)} 則，落在本專案封閉詞彙內的有 {len(terms)} 則",
             "這個端點是**全域熱搜**不是時尚熱搜：多數日子交集為 0，這是誠實的 0，不是失敗"]
    meta["trending_titles"] = [r["title"] for r in raw[:20]]
    meta["mapped"] = hits
    return terms, notes, meta


def gt_widgets(geo: str, tz: int, sleep_s: float, limit: int) -> tuple[list[dict], list[str], dict]:
    """UNOFFICIAL two-step widget endpoint (what the archived `pytrends` wrapped). Opt-in only.

    pytrends was archived read-only on 2025-04-17 and its README always said "not an official or
    supported API". We keep this behind `--gt-mode widgets` and treat 429 as the expected answer.
    """
    terms, notes, per = [], [], []
    status_seen = Counter()
    for v in VOCAB[:limit]:
        req = json.dumps({"comparisonItem": [{"keyword": v["term"], "geo": geo, "time": "today 12-m"}],
                          "category": 0, "property": ""}, separators=(",", ":"))
        code, body = _get(GT_EXPLORE.format(tz=tz, req=urllib.parse.quote(req)))
        status_seen[code] += 1
        if code != 200:
            per.append({"term": v["term"], "http_status": code})
            time.sleep(sleep_s)
            continue
        try:
            widgets = json.loads(body[5:].decode("utf-8"))["widgets"]
            ml = next(w for w in widgets if w.get("id") == "TIMESERIES")
            time.sleep(sleep_s)
            code2, body2 = _get(GT_MULTILINE.format(
                tz=tz, req=urllib.parse.quote(json.dumps(ml["request"], separators=(",", ":"))),
                tok=ml["token"]))
            status_seen[code2] += 1
            if code2 != 200:
                per.append({"term": v["term"], "http_status": code2})
                time.sleep(sleep_s)
                continue
            series = [p["value"][0] for p in json.loads(body2[5:].decode("utf-8"))["default"]["timelineData"]]
            if len(series) < 12:
                continue
            recent, base = series[-4:], series[:-4]
            mu = sum(base) / len(base)
            sd = (sum((x - mu) ** 2 for x in base) / len(base)) ** 0.5 or 1.0
            z = (sum(recent) / len(recent) - mu) / sd
            terms.append({"term": v["term"], "score": round(z, 4), "df": 0})
            per.append({"term": v["term"], "http_status": 200, "z_recent_vs_12m": round(z, 4),
                        "kind": v["kind"], "target": v["target"], "risk": v["risk"]})
        except Exception as e:                      # malformed payload is data too
            per.append({"term": v["term"], "error": f"{type(e).__name__}: {e}"})
        time.sleep(sleep_s)
    notes = [f"來源：Google Trends **非官方** widget 端點（pytrends 包的那個），geo={geo}",
             f"HTTP 統計：{dict(status_seen)}；429 是這個端點的常態，不是本腳本的錯誤",
             "pytrends 已於 2025-04-17 由作者封存唯讀；官方 Trends API 仍在 alpha（需候補名單）",
             "score = 最近 4 週相對前 48 週的 z；Google 的值是 0–100 相對尺度，跨關鍵字不可比"]
    return terms, notes, {"endpoint": "trends.google.com/trends/api/{explore,widgetdata/multiline}",
                          "official": False, "per_term": per}


# --- Wikipedia pageviews ----------------------------------------------------------------------
def plan_wikipedia(proj: str, days: int) -> list[str]:
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=days)
    return [WIKI_PAGEVIEWS.format(proj=proj, article=urllib.parse.quote(a, safe=""),
                                  start=start.strftime("%Y%m%d"), end=end.strftime("%Y%m%d"))
            for a, _ in WIKI_ARTICLES]


def wikipedia(proj: str, days: int, sleep_s: float) -> tuple[list[dict], list[str], dict]:
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=days)
    terms, per = [], []
    status = Counter()
    for article, v in WIKI_ARTICLES:
        url = WIKI_PAGEVIEWS.format(proj=proj, article=urllib.parse.quote(article, safe=""),
                                    start=start.strftime("%Y%m%d"), end=end.strftime("%Y%m%d"))
        code, body = _get(url)
        status[code] += 1
        if code == 200:
            try:
                views = [it["views"] for it in json.loads(body)["items"]]
            except Exception:
                views = []
            if len(views) >= 21:
                recent, base = views[-7:], views[:-7]
                mu = sum(base) / len(base)
                sd = (sum((x - mu) ** 2 for x in base) / len(base)) ** 0.5 or 1.0
                z = (sum(recent) / len(recent) - mu) / sd
                terms.append({"term": v["term"], "score": round(z, 4), "df": int(sum(recent))})
                per.append({"term": v["term"], "article": article, "kind": v["kind"],
                            "target": v["target"], "risk": v["risk"],
                            "views_7d": int(sum(recent)), "baseline_mean_daily": round(mu, 1),
                            "z_7d_vs_prior": round(z, 4)})
            else:
                per.append({"term": v["term"], "article": article, "note": "資料點不足，跳過"})
        else:
            per.append({"term": v["term"], "article": article, "http_status": code})
        time.sleep(sleep_s)                        # 10 req/min anonymous → 6.5 s between calls
    notes = [f"來源：Wikimedia Pageviews REST API（{proj}，agent=user，過濾爬蟲），無金鑰、無登入",
             f"HTTP 統計：{dict(status)}；匿名速率上限 10 requests/minute，本腳本每次呼叫間隔 {sleep_s}s",
             "資料本身為 CC0（Wikimedia 分析資料），可存檔、可重現",
             "score = 最近 7 日日均相對前段日均的 z 分數；df = 最近 7 日總瀏覽數",
             "**注意力 ≠ 購買意圖**：條目瀏覽混入新聞、學術、同名事物（見每列 risk）"]
    return terms, notes, {"endpoint": WIKI_PAGEVIEWS, "official": True, "rate_limit": "10/min anon",
                          "window": f"{start} .. {end}", "per_term": per}


# --- Bluesky (the social source) ---------------------------------------------------------------
def plan_bluesky(window: int) -> list[str]:
    return [BSKY_APPVIEW.format(method="app.bsky.unspecced.getTrends") + "?limit=25",
            f"{JETSTREAM}   (websocket, read-only, {window}s sampling window)"]


def bluesky(window: int) -> tuple[list[dict], list[str], dict]:
    """Bluesky's public AppView + the public Jetstream firehose. No account, no key, no login.

    `app.bsky.feed.searchPosts` would be the natural call but it answers HTTP 403 at Bluesky's
    BunnyCDN edge from Taiwan (verified 2026-09-19), so we count terms in the firehose sample
    instead — which is a *better* denominator anyway, because we see the total post count.
    """
    meta: dict = {"official": True, "login_used": False}
    topics = []
    code, body = _get(BSKY_APPVIEW.format(method="app.bsky.unspecced.getTrends") + "?limit=25")
    meta["get_trends_http"] = code
    if code == 200:
        try:
            topics = [{"topic": t.get("displayName"), "posts": t.get("postCount"),
                       "category": t.get("category")} for t in json.loads(body).get("trends", [])]
        except Exception:
            topics = []
    meta["platform_trending_topics"] = topics[:10]

    counts: Counter[str] = Counter()
    total = 0
    err = None
    try:
        import asyncio
        import websockets

        pats = {v["term"]: re.compile(r"(?<![a-z])" + re.escape(v["term"]) + r"(?![a-z])")
                for v in VOCAB}

        async def sample() -> None:
            nonlocal total
            async with websockets.connect(JETSTREAM, additional_headers={"User-Agent": UA},
                                          max_size=2 ** 20) as ws:
                deadline = time.monotonic() + window
                while time.monotonic() < deadline:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=max(1.0, deadline - time.monotonic()))
                    except asyncio.TimeoutError:
                        break
                    rec = ((json.loads(msg).get("commit") or {}).get("record") or {})
                    text = (rec.get("text") or "").lower()
                    if not text:
                        continue
                    total += 1
                    for term, pat in pats.items():
                        if pat.search(text):
                            counts[term] += 1

        asyncio.run(sample())
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        meta["jetstream_error"] = err

    per, terms = [], []
    for v in VOCAB:
        c = counts.get(v["term"], 0)
        if c == 0:
            continue
        rate_ppm = c / max(total, 1) * 1e6
        terms.append({"term": v["term"], "score": round(__import__("math").log10(rate_ppm + 1.0), 4), "df": c})
        per.append({"term": v["term"], "kind": v["kind"], "target": v["target"], "risk": v["risk"],
                    "hits": c, "rate_per_million_posts": round(rate_ppm, 1)})
    meta["posts_sampled"] = total
    meta["per_term"] = per
    notes = [f"來源：Bluesky 公開 AppView + 公開 Jetstream firehose，無帳號、無金鑰、無登入",
             f"取樣視窗 {window}s，共讀到 {total} 則公開貼文；只統計詞頻，**不存任何貼文內容或作者**",
             "app.bsky.feed.searchPosts 從台灣呼叫在 BunnyCDN 邊緣回 403（2026-09-19 實測），故改用 firehose 取樣",
             "score = log10(每百萬則貼文出現次數 + 1)；**單輪沒有基準線**，要比較必須連續跑幾天",
             "Bluesky 是英語為主、科技人口為主的樣本，對台灣成衣需求的外部效度未知"]
    if err:
        notes.append(f"firehose 連線失敗：{err}（本輪只有平台熱門主題，沒有詞頻）")
    return terms, notes, meta


# ---------------------------------------------------------------------------------------------
SOURCES = ("google_trends", "wikipedia", "bluesky")


def run_one(src: str, a: argparse.Namespace) -> dict:
    if src == "google_trends":
        if a.gt_mode == "rss":
            terms, notes, meta = gt_rss(a.geo)
        else:
            terms, notes, meta = gt_widgets(a.geo, a.tz, a.gt_sleep, a.limit)
        name = f"google_trends_{a.gt_mode}"
    elif src == "wikipedia":
        terms, notes, meta = wikipedia(a.wiki_project, a.days, a.wiki_sleep)
        name = "wikipedia_pageviews"
    elif src == "bluesky":
        terms, notes, meta = bluesky(a.window)
        name = "bluesky_public"
    else:
        raise SystemExit(f"unknown --source {src!r}; expected one of {SOURCES} or 'all'")
    terms.sort(key=lambda t: -t["score"])
    return _envelope(name, notes, terms, **meta)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default="wikipedia",
                    help=f"{' | '.join(SOURCES)} | all  (login-only sources are refused)")
    ap.add_argument("--out-dir", default="data/trends")
    ap.add_argument("--geo", default="TW", help="Google Trends region")
    ap.add_argument("--tz", type=int, default=-480, help="minutes offset Google expects (TW = -480)")
    ap.add_argument("--gt-mode", default="rss", choices=["rss", "widgets"],
                    help="rss = official public feed (default); widgets = unofficial, often 429")
    ap.add_argument("--gt-sleep", type=float, default=GT_SLEEP)
    ap.add_argument("--wiki-project", default="en.wikipedia")
    ap.add_argument("--wiki-sleep", type=float, default=WIKI_SLEEP)
    ap.add_argument("--days", type=int, default=90, help="Wikipedia pageview window")
    ap.add_argument("--window", type=int, default=60, help="Bluesky firehose sampling seconds")
    ap.add_argument("--limit", type=int, default=len(VOCAB), help="max keywords per run")
    ap.add_argument("--every", type=float, default=0.0, help="seconds between refreshes; 0 = once")
    ap.add_argument("--dry-run", action="store_true", help="print the exact requests, fetch nothing")
    a = ap.parse_args()

    refuse_if_login_required(a.source)
    todo = list(SOURCES) if a.source == "all" else [a.source]
    for s in todo:
        if s not in SOURCES:
            raise SystemExit(f"unknown --source {s!r}; expected one of {SOURCES} or 'all'")

    if a.dry_run:
        print(f"DRY RUN — nothing is fetched. User-Agent: {UA}\nlogin/credentials used: NONE")
        for s in todo:
            plan = (plan_google_trends(a.geo, a.gt_mode, a.tz) if s == "google_trends"
                    else plan_wikipedia(a.wiki_project, a.days) if s == "wikipedia"
                    else plan_bluesky(a.window))
            sleep_s = {"google_trends": a.gt_sleep, "wikipedia": a.wiki_sleep, "bluesky": 0.0}[s]
            print(f"\n[{s}]  {len(plan)} request(s), {sleep_s}s apart "
                  f"→ {a.out_dir}/{s}*_{date.today().isoformat()}.json")
            for u in plan[:a.limit]:
                print("   GET " + u)
            if len(plan) > a.limit:
                print(f"   ... {len(plan) - a.limit} more (raise --limit)")
        print("\nrefused without asking (login required):")
        for k, why in LOGIN_REQUIRED.items():
            print(f"   {k:12s} {why}")
        return

    dst_dir = ROOT / a.out_dir
    dst_dir.mkdir(parents=True, exist_ok=True)
    while True:
        for s in todo:
            try:
                env = run_one(s, a)
                dst = dst_dir / f"{env['source'].split(':', 1)[1]}_{env['as_of']}.json"
                dst.write_text(json.dumps(env, ensure_ascii=False, indent=1), encoding="utf-8")
                top = "、".join(t["term"] for t in env["terms"][:5]) or "(本輪無交集)"
                print(f"{env['fetched_at']}  {s:14s} {len(env['terms']):2d} terms  top: {top}  -> {dst}",
                      flush=True)
            except Exception as e:      # the demo must survive a dead network without a special case
                print(f"{s}: could not fetch ({type(e).__name__}: {e}); leaving any previous file "
                      f"alone — the badge layer treats a missing/stale file as a documented no-op",
                      flush=True)
        if a.every <= 0:
            return
        time.sleep(a.every)


if __name__ == "__main__":
    main()
