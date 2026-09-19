"""Polite fetching: per-host rate limit, disk cache with conditional requests, bounded retries, and
detection of every response that means "stop" -- which it raises as `Blocked`, never retries past.

Stop signals (-> Blocked, the source is stopped by the caller):
  access_denied      HTTP 401 / 403 / 407 / 451
  login_required     redirected to a login URL, or a password gate with no content behind it
  captcha            a CAPTCHA or bot-challenge interstitial (Cloudflare, PerimeterX, DataDome,
                     Incapsula, reCAPTCHA/hCaptcha gate pages)
  rate_limited       429 that persists after honouring Retry-After, or a Retry-After too long to wait

Transient failures (-> FetchError after retries, the caller logs it and moves on): network errors,
timeouts, 5xx that are not challenge pages. 404/410 are FetchError without retry.
"""

from __future__ import annotations

import email.utils
import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from . import USER_AGENT


class Blocked(Exception):
    def __init__(self, reason: str, url: str, detail: str = "", status: int | None = None):
        super().__init__(f"{reason}: {url} ({detail})")
        self.reason, self.url, self.detail, self.status = reason, url, detail, status


class FetchError(Exception):
    def __init__(self, url: str, detail: str, status: int | None = None):
        super().__init__(f"{url}: {detail}")
        self.url, self.detail, self.status = url, detail, status


@dataclass
class Response:
    url: str
    final_url: str
    status: int
    headers: dict[str, str]
    body: bytes
    from_cache: bool = False
    fetched_at: float = field(default_factory=time.time)

    @property
    def content_type(self) -> str:
        return self.headers.get("content-type", "").split(";")[0].strip().lower()

    def text(self) -> str:
        m = re.search(r"charset=([\w-]+)", self.headers.get("content-type", ""), re.I)
        try:
            return self.body.decode(m.group(1) if m else "utf-8", "replace")
        except LookupError:
            return self.body.decode("utf-8", "replace")


# An interstitial page IS the block: stop whatever else is on it.
STRONG_CHALLENGE = [
    ("<title>just a moment...</title>", "cloudflare_challenge"),
    ("challenges.cloudflare.com/cdn-cgi/challenge-platform", "cloudflare_challenge"),
    ("cf-browser-verification", "cloudflare_challenge"),
    ("attention required! | cloudflare", "cloudflare_block"),
    ("px-captcha", "perimeterx"), ("captcha-delivery.com", "datadome"),
    ("_incapsula_resource", "incapsula"), ("distil_r_captcha", "distil"),
    ("our systems have detected unusual traffic", "bot_check"),
    ("please verify you are a human", "bot_check"),
]
# A widget can sit in a footer newsletter form on a perfectly normal product page: only a stop
# signal when the page has no content of its own.
WEAK_CHALLENGE = [("g-recaptcha", "recaptcha"), ("www.google.com/recaptcha", "recaptcha"),
                  ("h-captcha", "hcaptcha"), ("hcaptcha.com/1/api.js", "hcaptcha"),
                  ("are you a robot", "bot_check")]
LOGIN_PATH = re.compile(r"/(log-?in|sign-?in|signin|accounts/login|auth/login|session/new|users/sign_in)(/|$|\?)", re.I)
LOGIN_TITLE = re.compile(r"<title>[^<]*(log ?in|sign ?in|登入|登錄|ログイン)[^<]*</title>", re.I)
HAS_CONTENT = re.compile(r'application/ld\+json|property=["\']og:title', re.I)


def challenge_in(html: str) -> str | None:
    low = html[:300_000].lower()
    for marker, name in STRONG_CHALLENGE:
        if marker in low:
            return name
    if not HAS_CONTENT.search(low):
        for marker, name in WEAK_CHALLENGE:
            if marker in low:
                return name
    return None


def login_gate(requested: str, final: str, html: str) -> str | None:
    if LOGIN_PATH.search(urlsplit(final).path + "?") and not LOGIN_PATH.search(urlsplit(requested).path + "?"):
        return f"redirected to {final}"
    if 'type="password"' in html.lower() and LOGIN_TITLE.search(html[:50_000]) and not HAS_CONTENT.search(html):
        return "password form with no content behind it"
    return None


class Fetcher:
    def __init__(self, cache_dir: Path | None, cache_ttl_s: float = 86_400, min_delay_s: float = 2.0,
                 max_retries: int = 2, timeout: float = 30.0, max_bytes: int = 5_000_000,
                 max_retry_after_s: float = 60.0, sleep=time.sleep, clock=time.monotonic):
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.cache_ttl_s, self.min_delay_s = cache_ttl_s, min_delay_s
        self.max_retries, self.timeout, self.max_bytes = max_retries, timeout, max_bytes
        self.max_retry_after_s = max_retry_after_s
        self._sleep, self._clock = sleep, clock
        self._last: dict[str, float] = {}
        self._host_delay: dict[str, float] = {}
        self.network_requests = 0
        self.cache_hits = 0

    # ---- rate limit ---------------------------------------------------------------------------
    def set_host_delay(self, url: str, seconds: float | None) -> None:
        if seconds:
            host = urlsplit(url).netloc
            self._host_delay[host] = max(self._host_delay.get(host, 0.0), float(seconds))

    def _wait(self, url: str) -> None:
        host = urlsplit(url).netloc
        gap = max(self.min_delay_s, self._host_delay.get(host, 0.0))
        last = self._last.get(host)
        if last is not None:
            remaining = gap - (self._clock() - last)
            if remaining > 0:
                self._sleep(remaining)
        self._last[host] = self._clock()

    # ---- cache --------------------------------------------------------------------------------
    def _paths(self, url: str) -> tuple[Path, Path] | None:
        if not self.cache_dir:
            return None
        h = hashlib.sha1(url.encode("utf-8")).hexdigest()
        d = self.cache_dir / h[:2]
        return d / f"{h}.json", d / f"{h}.body"

    def _cached(self, url: str) -> tuple[Response, bool] | None:
        p = self._paths(url)
        if not p or not p[0].exists() or not p[1].exists():
            return None
        meta = json.loads(p[0].read_text(encoding="utf-8"))
        r = Response(url=url, final_url=meta["final_url"], status=meta["status"], headers=meta["headers"],
                     body=p[1].read_bytes(), from_cache=True, fetched_at=meta["fetched_at"])
        return r, (time.time() - meta["fetched_at"]) < self.cache_ttl_s

    def _store(self, r: Response) -> None:
        p = self._paths(r.url)
        if not p:
            return
        p[0].parent.mkdir(parents=True, exist_ok=True)
        p[1].write_bytes(r.body)
        p[0].write_text(json.dumps({"final_url": r.final_url, "status": r.status, "headers": r.headers,
                                    "fetched_at": r.fetched_at}), encoding="utf-8")

    # ---- fetch --------------------------------------------------------------------------------
    def _retry_after(self, headers) -> float | None:
        v = (headers.get("Retry-After") or "").strip()
        if not v:
            return None
        if v.isdigit():
            return float(v)
        try:
            return max(0.0, email.utils.parsedate_to_datetime(v).timestamp() - time.time())
        except (TypeError, ValueError):
            return None

    def get(self, url: str) -> Response:
        cached = self._cached(url)
        if cached and cached[1]:
            self.cache_hits += 1
            return cached[0]
        headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
                   "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8"}
        if cached:                                           # stale: ask the server if it changed
            etag, lm = cached[0].headers.get("etag"), cached[0].headers.get("last-modified")
            if etag:
                headers["If-None-Match"] = etag
            if lm:
                headers["If-Modified-Since"] = lm
        attempt = 0
        while True:
            self._wait(url)
            self.network_requests += 1
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    body = r.read(self.max_bytes + 1)
                    hdrs = {k.lower(): v for k, v in r.headers.items()}
                    resp = Response(url=url, final_url=r.geturl(), status=r.status, headers=hdrs,
                                    body=body[: self.max_bytes])
                break
            except urllib.error.HTTPError as e:
                status = e.code
                body = e.read(300_000) if e.fp else b""
                html = body.decode("utf-8", "replace")
                if status == 304 and cached:
                    fresh = cached[0]
                    fresh.fetched_at, fresh.from_cache = time.time(), True
                    self._store(fresh)
                    self.cache_hits += 1
                    return fresh
                ch = challenge_in(html)
                if ch:
                    raise Blocked("captcha", url, ch, status)
                if status in (401, 403, 407, 451):
                    raise Blocked("access_denied", url, f"HTTP {status}", status)
                if status == 429:
                    wait = self._retry_after(e.headers)
                    if attempt >= self.max_retries:
                        raise Blocked("rate_limited", url, f"HTTP 429 after {attempt} retries", status)
                    if wait is not None and wait > self.max_retry_after_s:
                        raise Blocked("rate_limited", url, f"Retry-After {wait:.0f}s exceeds the "
                                                           f"{self.max_retry_after_s:.0f}s we will wait", status)
                    self._sleep(wait if wait is not None else 5.0 * (attempt + 1))
                    attempt += 1
                    continue
                if status in (404, 410):
                    raise FetchError(url, f"HTTP {status}", status)
                if status >= 500 and attempt < self.max_retries:
                    self._sleep(2.0 * (attempt + 1))
                    attempt += 1
                    continue
                raise FetchError(url, f"HTTP {status}", status)
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                if attempt < self.max_retries:
                    self._sleep(2.0 * (attempt + 1))
                    attempt += 1
                    continue
                raise FetchError(url, f"{type(e).__name__}: {e}")

        if resp.content_type in ("text/html", "application/xhtml+xml", ""):
            html = resp.text()
            ch = challenge_in(html)
            if ch:
                raise Blocked("captcha", url, ch, resp.status)
            gate = login_gate(url, resp.final_url, html)
            if gate:
                raise Blocked("login_required", url, gate, resp.status)
        self._store(resp)
        return resp
