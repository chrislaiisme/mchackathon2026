"""Wikimedia Commons as an inspiration-image source (runway, cosplay, street fashion).

Uses the official MediaWiki Action API (https://commons.wikimedia.org/w/api.php), which permits
automated access from a client with a descriptive User-Agent that follows the API etiquette:
requests in series, `maxlag=5`, back off when the server says it is lagged, stop when it says no.

  * list=categorymembers (cmtype=file|subcat) walks the categories breadth-first up to `depth`
    levels of subcategories; files are de-duplicated across categories, category cycles are cut;
  * prop=imageinfo|categories (iiprop=url|extmetadata|mime|size, iiurlwidth) describes each file;
    only image/jpeg, image/png and image/webp are kept;
  * a file is skipped when one of its own categories, or a category on the path it was found
    through, contains an excluded word (case-insensitive substring); subcategories containing one
    are not entered at all.

Commons states no brand and no price, so both stay None. The licence and attribution that CC BY /
BY-SA require when an image is shown are carried in `field_origin` ("license", "license_url",
"author", "credit"), because `Record` has no licence field.

Stop signals (-> `Blocked`, raised by `CommonsSource.records()`, caught and logged by `run()`):
HTTP 401/403/407/451, HTTP 429 that persists after Retry-After (handled by `Fetcher`), the API
error codes `ratelimited` / `blocked` / `autoblocked` / `readapidenied`, and replication lag that
persists after two `maxlag` retries.
"""

from __future__ import annotations

import html
import json
import re
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterator
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from .http import Blocked, FetchError, Fetcher
from .records import Record

API_URL = "https://commons.wikimedia.org/w/api.php"
WIKI_URL = "https://commons.wikimedia.org/wiki/"

DEFAULT_EXCLUDE = ["Lingerie shows", "Topless", "Nude", "Nudity", "Erotic", "Furry"]
KEEP_MIME = {"image/jpeg", "image/png", "image/webp"}
EXTMETADATA_FIELDS = ["ObjectName", "ImageDescription", "DateTimeOriginal", "DateTime",
                      "LicenseShortName", "LicenseUrl", "Artist", "Credit"]

MAXLAG_S = 5                 # recommended value for Wikimedia wikis (Manual:Maxlag parameter)
MAXLAG_RETRIES = 2
MAXLAG_WAIT_CAP_S = 30.0
MAXLAG_WAIT_MIN_S = 5.0      # "pause your script for at least 5 seconds before trying again"
TITLES_PER_QUERY = 50        # the API's multi-value limit for `titles` without apihighlimits

STOP_CODES = {"ratelimited": "rate_limited", "blocked": "access_denied", "autoblocked": "access_denied",
              "readapidenied": "access_denied"}


# ------------------------------------------------------------------------------------------------
# text helpers
# ------------------------------------------------------------------------------------------------
class _TextOnly(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in ("br", "p", "div", "li"):
            self.parts.append(" ")


def strip_html(value) -> str | None:
    """Text content of an HTML fragment, entities decoded, whitespace collapsed; None when empty."""
    if value is None:
        return None
    p = _TextOnly()
    p.feed(str(value))
    p.close()
    text = re.sub(r"\s+", " ", html.unescape("".join(p.parts))).strip()
    return text or None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _excluded(title: str, words: list[str]) -> str | None:
    low = title.lower()
    for w in words:
        if w.lower() in low:
            return w
    return None


def _drop_utm(url: str) -> str:
    """imageinfo URLs now carry ?utm_source=...&utm_campaign=imageinfo; the file is the same without."""
    p = urlsplit(url)
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not k.lower().startswith("utm_")]
    return urlunsplit((p.scheme, p.netloc, p.path, urlencode(q), p.fragment))


def _cat(name: str) -> str:
    return name if name.startswith("Category:") else f"Category:{name}"


# ------------------------------------------------------------------------------------------------
# the source
# ------------------------------------------------------------------------------------------------
@dataclass
class CommonsSource:
    name: str
    categories: list[str]
    max_files: int
    depth: int = 2
    thumb_width: int = 800
    exclude_categories: list[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDE))
    delay_s: float = 1.0
    cache_dir: str | Path | None = None
    page_size: int = 100                     # cmlimit per categorymembers request
    fetcher: Fetcher | None = None           # injected in tests; built from delay_s/cache_dir otherwise
    sleep: object = time.sleep               # used for maxlag waits (the Fetcher sleeps for spacing)

    def __post_init__(self):
        if self.fetcher is None:
            self.fetcher = Fetcher(self.cache_dir, min_delay_s=self.delay_s, sleep=self.sleep)
        self.errors: list[dict] = []
        self.report = {"name": self.name, "type": "commons", "status": "completed", "stop_reason": None,
                       "stop_detail": None, "stop_url": None, "api_calls": 0, "categories_walked": 0,
                       "subcats_excluded": 0, "files_seen": 0, "duplicates": 0, "excluded": 0,
                       "wrong_mime": 0, "no_imageinfo": 0, "records": 0, "errors": 0}

    # ---- API ----------------------------------------------------------------------------------
    def _log(self, url, kind, detail, status=None):
        self.errors.append({"time": _now(), "source": self.name, "url": url, "kind": kind,
                            "detail": detail, "status": status})
        self.report["errors"] = len(self.errors)

    def _forget(self, url: str) -> None:
        """An error body must not be served from the disk cache on retry."""
        paths = self.fetcher._paths(url) if self.fetcher.cache_dir else None
        for p in paths or ():
            p.unlink(missing_ok=True)

    def api(self, params: dict) -> dict:
        """One Action API GET, serial and spaced by the Fetcher; maxlag honoured, stop codes raised."""
        q = {"action": "query", "format": "json", "formatversion": "2", "maxlag": str(MAXLAG_S), **params}
        url = f"{API_URL}?{urlencode(q)}"
        for attempt in range(MAXLAG_RETRIES + 1):
            self.report["api_calls"] += 1
            resp = self.fetcher.get(url)              # raises Blocked on 401/403/407/451 and persistent 429
            try:
                body = json.loads(resp.body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                self._forget(url)
                raise FetchError(url, f"not JSON: {e}", resp.status)
            err = body.get("error") if isinstance(body, dict) else None
            if not err:
                return body
            self._forget(url)
            code, info = err.get("code", ""), err.get("info", "")
            if code == "maxlag":
                if attempt >= MAXLAG_RETRIES:
                    raise Blocked("server_lagged", url, f"maxlag persisted after {MAXLAG_RETRIES} retries: {info}")
                lag = err.get("lag")
                try:
                    lag = float(lag)
                except (TypeError, ValueError):
                    lag = 0.0
                ra = resp.headers.get("retry-after", "")
                ra = float(ra) if ra.strip().isdigit() else 0.0
                self.sleep(min(MAXLAG_WAIT_CAP_S, max(MAXLAG_WAIT_MIN_S, lag, ra)))
                continue
            if code in STOP_CODES:
                raise Blocked(STOP_CODES[code], url, f"API error {code}: {info}")
            raise FetchError(url, f"API error {code}: {info}")
        raise AssertionError("unreachable")

    def _query_all(self, params: dict) -> Iterator[dict]:
        """Follow `continue` tokens; yields each response body."""
        cont: dict = {}
        while True:
            body = self.api({**params, **cont})
            yield body
            if "continue" not in body:
                return
            cont = body["continue"]

    # ---- category walk ------------------------------------------------------------------------
    def walk(self) -> Iterator[tuple[str, tuple[str, ...]]]:
        """Yield (file title, category path) once per file, breadth-first; lazy, so it stops
        requesting as soon as the consumer has enough."""
        seen_cats: set[str] = set()
        seen_files: set[str] = set()
        queue: deque[tuple[str, tuple[str, ...], int]] = deque()
        for c in self.categories:
            c = _cat(c)
            if _excluded(c, self.exclude_categories):
                self.report["subcats_excluded"] += 1
                continue
            queue.append((c, (c,), 0))
        while queue:
            cat, path, level = queue.popleft()
            if cat in seen_cats:
                continue
            seen_cats.add(cat)
            self.report["categories_walked"] += 1
            params = {"list": "categorymembers", "cmtitle": cat, "cmtype": "file|subcat",
                      "cmprop": "ids|title|type", "cmlimit": str(self.page_size)}
            try:
                for body in self._query_all(params):
                    for m in (body.get("query") or {}).get("categorymembers", []):
                        title, kind = m.get("title", ""), m.get("type")
                        if kind == "subcat" or m.get("ns") == 14:
                            if level >= self.depth:
                                continue
                            if _excluded(title, self.exclude_categories):
                                self.report["subcats_excluded"] += 1
                                continue
                            if title not in seen_cats:
                                queue.append((title, path + (title,), level + 1))
                        elif kind == "file" or m.get("ns") == 6:
                            if title in seen_files:
                                self.report["duplicates"] += 1
                                continue
                            seen_files.add(title)
                            self.report["files_seen"] += 1
                            yield title, path
            except FetchError as e:
                self._log(e.url, "fetch_error", e.detail, e.status)

    # ---- file description ---------------------------------------------------------------------
    def describe(self, titles: list[str]) -> dict[str, dict]:
        """title -> {"imageinfo": {...}, "categories": [...]} for a batch of <= 50 files."""
        out: dict[str, dict] = {t: {"imageinfo": None, "categories": []} for t in titles}
        params = {"titles": "|".join(titles), "prop": "imageinfo|categories",
                  "iiprop": "url|extmetadata|mime|size", "iiurlwidth": str(self.thumb_width),
                  "iiextmetadatafilter": "|".join(EXTMETADATA_FIELDS), "cllimit": "max"}
        norm: dict[str, str] = {}
        for body in self._query_all(params):
            q = body.get("query") or {}
            for n in q.get("normalized", []):
                norm[n.get("to")] = n.get("from")
            for page in q.get("pages", []):
                t = page.get("title", "")
                t = t if t in out else norm.get(t, t)
                slot = out.setdefault(t, {"imageinfo": None, "categories": []})
                if page.get("imageinfo"):
                    slot["imageinfo"] = page["imageinfo"][0]
                for c in page.get("categories", []):
                    if c.get("title") and c["title"] not in slot["categories"]:
                        slot["categories"].append(c["title"])
        return out

    def to_record(self, title: str, info: dict, fetched_at: str | None = None) -> Record:
        em = info.get("extmetadata") or {}

        def meta(key):
            return strip_html((em.get(key) or {}).get("value"))

        origin: dict[str, str] = {"url": "commons:imageinfo.descriptionurl", "image_urls": "commons:imageinfo"}
        rec_title = meta("ObjectName")
        origin["title"] = "commons:extmetadata.ObjectName"
        if not rec_title:
            rec_title = title.split(":", 1)[1] if title.startswith("File:") else title
            origin["title"] = "commons:page_title"
        text = meta("ImageDescription")
        if text:
            origin["text"] = "commons:extmetadata.ImageDescription"
        published = None
        for key in ("DateTimeOriginal", "DateTime"):
            published = meta(key)
            if published:
                origin["published_at"] = f"commons:extmetadata.{key}"
                break
        images = [_drop_utm(u) for u in (info.get("thumburl"), info.get("url")) if u]
        images = list(dict.fromkeys(images))
        origin.update({"license": meta("LicenseShortName") or "", "license_url": meta("LicenseUrl") or "",
                       "author": meta("Artist") or "", "credit": meta("Credit") or ""})
        url = info.get("descriptionurl") or WIKI_URL + quote(title.replace(" ", "_"), safe=":/()")
        return Record(source=self.name, url=url, title=rec_title, text=text, brand=None, price=None,
                      currency=None, image_urls=images, published_at=published, page_type="image",
                      fetched_at=fetched_at or _now(), field_origin=origin)

    # ---- driver -------------------------------------------------------------------------------
    def records(self) -> Iterator[Record]:
        """Yield up to max_files records. Raises Blocked when the server says stop."""
        produced = 0
        walker = self.walk()
        exhausted = False
        while produced < self.max_files and not exhausted:
            batch: list[tuple[str, tuple[str, ...]]] = []
            want = min(TITLES_PER_QUERY, self.max_files - produced)
            for item in walker:
                batch.append(item)
                if len(batch) >= want:
                    break
            else:
                exhausted = True
            if not batch:
                break
            try:
                described = self.describe([t for t, _ in batch])
            except FetchError as e:
                self._log(e.url, "fetch_error", e.detail, e.status)
                continue
            for title, path in batch:
                d = described.get(title) or {}
                info = d.get("imageinfo")
                if not info:
                    self.report["no_imageinfo"] += 1
                    self._log(WIKI_URL + title.replace(" ", "_"), "no_imageinfo", "file has no imageinfo")
                    continue
                if (info.get("mime") or "").lower() not in KEEP_MIME:
                    self.report["wrong_mime"] += 1
                    continue
                hit = next((w for w in (_excluded(c, self.exclude_categories)
                                        for c in list(d.get("categories", [])) + list(path)) if w), None)
                if hit:
                    self.report["excluded"] += 1
                    continue
                produced += 1
                self.report["records"] = produced
                yield self.to_record(title, info)
                if produced >= self.max_files:
                    return


def run(source: CommonsSource) -> tuple[list[Record], list[dict]]:
    """Collect a source's records; a stop signal ends the source and is logged, not raised.
    The per-source counters are left in `source.report`."""
    recs: list[Record] = []
    try:
        for r in source.records():
            recs.append(r)
    except Blocked as b:
        source.report.update(status="stopped", stop_reason=b.reason, stop_url=b.url, stop_detail=b.detail)
        source._log(b.url, f"stopped:{b.reason}", b.detail, b.status)
    except FetchError as e:
        source._log(e.url, "fetch_error", e.detail, e.status)
    source.report["records"] = len(recs)
    return recs, source.errors
