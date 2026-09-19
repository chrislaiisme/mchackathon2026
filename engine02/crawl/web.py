"""The crawl loop for public web pages: seeds, sitemaps, link following, de-duplication, stop reasons.

A robots.txt disallow SKIPS that URL and the crawl continues -- sites routinely allow some paths and
not others, and obeying that is the point of robots.txt. What STOPS the whole source is a refusal
of access: login wall, CAPTCHA/bot challenge, 401/403/407/451, persistent 429 (see http.py), or an
unreachable robots.txt, which RFC 9309 says to treat as "disallow everything".

Listing pages are used for discovery; only pages whose structured data says they are a product,
an article or a post become records (configurable with `record_page_types`).
"""

from __future__ import annotations

import gzip
import re
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlsplit

from .extract import extract
from .http import Blocked, Fetcher, FetchError
from .records import Record, normalize_url
from .robots import Robots

LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)
# URL shapes that are usually a single product / article / post. Breadth-first alone spent lativ's
# whole 30-page budget on category pages (Disney, Dragon Ball, Ultraman ...) and found 1 product.
DEFAULT_PREFER = [r"/products?/", r"/p/", r"/item", r"/goods", r"/market/n/\d+", r"/product-detail/",
                  r"/gdsale/", r"/prod/", r"/article", r"/news/", r"/story/", r"/\d{6,}(/|$|\.html)"]


@dataclass
class WebSourceConfig:
    name: str
    start_urls: list[str]
    allowed_domains: list[str] = field(default_factory=list)   # empty -> the start URLs' hosts
    follow: list[str] = field(default_factory=list)            # regex; empty -> every allowed link
    exclude: list[str] = field(default_factory=list)           # regex; never enqueued
    prefer: list[str] = field(default_factory=lambda: list(DEFAULT_PREFER))  # fetched before listings
    sitemaps: list[str] = field(default_factory=list)
    use_robots_sitemaps: bool = False
    max_pages: int = 50
    max_depth: int = 2
    delay_s: float = 2.0
    record_page_types: list[str] = field(default_factory=lambda: ["product", "article", "post"])
    max_consecutive_errors: int = 5


def _host_allowed(url: str, domains: list[str]) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in domains)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_web(cfg: WebSourceConfig, fetcher: Fetcher, robots: Robots | None = None) -> tuple[list[Record], list[dict], dict]:
    robots = robots or Robots()
    domains = [d.lower().lstrip(".") for d in cfg.allowed_domains] or \
              sorted({(urlsplit(u).hostname or "").lower() for u in cfg.start_urls})
    follow = [re.compile(p) for p in cfg.follow]
    exclude = [re.compile(p) for p in cfg.exclude]
    errors: list[dict] = []
    report = {"name": cfg.name, "type": "web", "status": "completed", "stop_reason": None, "stop_detail": None,
              "stop_url": None, "pages_fetched": 0, "from_cache": 0, "records": 0, "duplicates": 0,
              "robots_disallowed": 0, "non_html": 0, "errors": 0, "started_at": _now()}

    def log(url, kind, detail, status=None):
        errors.append({"time": _now(), "source": cfg.name, "url": url, "kind": kind,
                       "detail": detail, "status": status})

    def stop(reason, url, detail):
        report.update(status="stopped", stop_reason=reason, stop_url=url, stop_detail=detail)
        log(url, f"stopped:{reason}", detail)

    def wanted(url: str) -> bool:
        if not _host_allowed(url, domains) or any(p.search(url) for p in exclude):
            return False
        return not follow or any(p.search(url) for p in follow)

    # two queues: pages that look like a single product/article first, listings after. The page
    # budget is then spent on records, and listings are still crawled for discovery.
    prefer = [re.compile(p) for p in cfg.prefer]
    hi: deque[tuple[str, int]] = deque()
    lo: deque[tuple[str, int]] = deque()
    queued: set[str] = set()

    class _Frontier:
        def __bool__(self):
            return bool(hi or lo)

        def popleft(self):
            return hi.popleft() if hi else lo.popleft()

    frontier = _Frontier()

    def enqueue(url: str, depth: int, seed: bool = False):
        n = normalize_url(url)
        if urlsplit(n).scheme not in ("http", "https") or n in queued:
            return
        if seed or wanted(n):
            queued.add(n)
            (hi if (seed or any(p.search(n) for p in prefer)) else lo).append((n, depth))

    for u in cfg.start_urls:
        enqueue(u, 0, seed=True)

    # sitemaps: listed explicitly, or announced in robots.txt when asked to use them
    maps = list(cfg.sitemaps)
    if cfg.use_robots_sitemaps:
        for u in cfg.start_urls:
            maps += robots.sitemaps(u)
    seen_maps: set[str] = set()
    while maps and report["status"] == "completed":
        sm = maps.pop(0)
        if sm in seen_maps or len(seen_maps) >= 20:
            continue
        seen_maps.add(sm)
        v = robots.check(sm)
        if not v.allowed:
            report["robots_disallowed"] += 1
            log(sm, "robots_disallowed", v.reason)
            continue
        try:
            r = fetcher.get(sm)
        except Blocked as b:
            stop(b.reason, b.url, b.detail)
            break
        except FetchError as e:
            log(sm, "fetch_error", e.detail, e.status)
            continue
        body = r.body
        if sm.endswith(".gz") or body[:2] == b"\x1f\x8b":
            try:
                body = gzip.decompress(body)
            except OSError:
                log(sm, "bad_sitemap", "not valid gzip")
                continue
        text = body.decode("utf-8", "replace")
        locs = LOC.findall(text)
        if "<sitemapindex" in text[:2000].lower():
            maps += locs[:50]
        else:
            for loc in locs[: cfg.max_pages * 5]:
                enqueue(loc, 0)

    records: list[Record] = []
    seen_urls: set[str] = set()
    seen_prints: set[str] = set()
    consecutive_errors = 0

    while frontier and report["status"] == "completed" and report["pages_fetched"] < cfg.max_pages:
        url, depth = frontier.popleft()
        v = robots.check(url)
        if v.reason == "unreachable" or v.reason == "refused_401_403":
            stop("robots_" + v.reason, url, "robots.txt could not be read; RFC 9309: treat as disallow all")
            break
        if not v.allowed:
            report["robots_disallowed"] += 1
            log(url, "robots_disallowed", "robots.txt disallows this URL")
            continue
        fetcher.set_host_delay(url, v.crawl_delay)
        try:
            r = fetcher.get(url)
        except Blocked as b:
            stop(b.reason, b.url, b.detail)
            break
        except FetchError as e:
            report["errors"] += 1
            log(url, "fetch_error", e.detail, e.status)
            consecutive_errors = 0 if e.status in (404, 410) else consecutive_errors + 1
            if consecutive_errors >= cfg.max_consecutive_errors:
                stop("too_many_errors", url, f"{consecutive_errors} consecutive failures")
            continue
        consecutive_errors = 0
        report["pages_fetched"] += 1
        report["from_cache"] += int(r.from_cache)
        if r.content_type not in ("text/html", "application/xhtml+xml", ""):
            report["non_html"] += 1
            continue
        page = extract(r.text(), r.final_url)
        canonical = page.get("canonical")
        key = normalize_url(canonical if canonical and _host_allowed(canonical, domains) else r.final_url)

        if depth < cfg.max_depth:
            for link in page["links"]:
                enqueue(link, depth + 1)

        if page["page_type"] not in cfg.record_page_types:
            continue
        rec = Record(source=cfg.name, url=key, title=page["title"], text=page["text"], brand=page["brand"],
                     price=page["price"], currency=page["currency"], image_urls=page["image_urls"],
                     published_at=page["published_at"], page_type=page["page_type"],
                     fetched_at=datetime.fromtimestamp(r.fetched_at, timezone.utc).isoformat(timespec="seconds"),
                     field_origin=page["field_origin"], category=page.get("category"), sku=page.get("sku"),
                     availability=page.get("availability"), color=page.get("color"), gender=page.get("gender"))
        fp = rec.fingerprint()
        if key in seen_urls or fp in seen_prints:
            report["duplicates"] += 1
            continue
        seen_urls.add(key)
        seen_prints.add(fp)
        records.append(rec)

    if report["status"] == "completed" and report["pages_fetched"] == 0 and report["robots_disallowed"]:
        # nothing was fetchable at all: that is a refusal, not a completed crawl
        report.update(status="stopped", stop_reason="robots_disallowed_all_seeds", stop_url=cfg.start_urls[0],
                      stop_detail="robots.txt disallows every start URL for this user agent")
    report["records"] = len(records)
    report["finished_at"] = _now()
    return records, errors, report
