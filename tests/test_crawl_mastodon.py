"""Offline tests for the Mastodon hashtag-timeline source: urlopen inside engine02.crawl.http is
replaced by a router answering with canned Status JSON; robots.txt comes from a fake opener."""

from __future__ import annotations

import io
import json
import urllib.error
from urllib.parse import parse_qs, urlsplit

import pytest

from engine02.crawl import USER_AGENT
from engine02.crawl import http as http_mod
from engine02.crawl.http import Fetcher
from engine02.crawl.mastodon import run_mastodon, status_to_record, tag_url
from engine02.crawl.robots import Robots


class FakeResp:
    def __init__(self, url, body, status=200, ctype="application/json; charset=utf-8"):
        self._url, self.status = url, status
        self._body = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        self.headers = {"Content-Type": ctype}

    def read(self, n=-1):
        return self._body

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Router:
    def __init__(self, handler):
        self.handler, self.calls = handler, []

    def __call__(self, req, timeout=None):
        url = req.full_url
        assert req.get_header("User-agent") == USER_AGENT
        p = urlsplit(url)
        params = {k: v[0] for k, v in parse_qs(p.query).items()}
        self.calls.append((p.path, params))
        out = self.handler(p.path, params)
        if isinstance(out, Exception):
            raise out
        return FakeResp(url, out)


def robots_opener(body: bytes = b"User-agent: *\nDisallow: /admin/\n"):
    def opener(req, timeout=None):
        return FakeResp(req.full_url, body, ctype="text/plain")
    return opener


def status(i, sensitive=False, spoiler="", media=("image",), content=None, reblog=None, url=True):
    s = {"id": str(1000 - i), "created_at": f"2026-09-19T10:{i % 60:02d}:00.000Z",
         "sensitive": sensitive, "spoiler_text": spoiler,
         "uri": f"https://remote.example/users/u{i}/statuses/{1000 - i}",
         "url": f"https://mastodon.social/@u{i}/{1000 - i}" if url else None,
         "content": content if content is not None else f"<p>Look {i} <a href=\"x\">#ootd</a></p>",
         "account": {"acct": f"u{i}@remote.example"},
         "media_attachments": [{"type": t, "url": f"https://files.example/{i}_{k}.jpg",
                                "preview_url": f"https://files.example/{i}_{k}_small.jpg"}
                               for k, t in enumerate(media)],
         "reblog": reblog}
    return s


@pytest.fixture
def sleeps():
    return []


def make(monkeypatch, handler, sleeps, robots_body=None, **kw):
    router = Router(handler)
    monkeypatch.setattr(http_mod.urllib.request, "urlopen", router)
    fetcher = Fetcher(None, min_delay_s=0.0, sleep=sleeps.append, max_retries=1)
    robots = Robots(opener=robots_opener(robots_body) if robots_body is not None else robots_opener())
    kw.setdefault("instances", ["mastodon.social"])
    kw.setdefault("hashtags", ["ootd"])
    return (lambda: run_mastodon("masto_test", fetcher=fetcher, robots=robots, **kw)), router


def test_tag_url_params_and_unicode():
    u = tag_url("mastodon.social", "#穿搭", only_media=True, max_id="123")
    p = urlsplit(u)
    assert p.netloc == "mastodon.social" and p.path == "/api/v1/timelines/tag/%E7%A9%BF%E6%90%AD"
    assert parse_qs(p.query) == {"limit": ["40"], "only_media": ["true"], "max_id": ["123"]}
    assert "only_media" not in tag_url("https://x.example/", "ootd", only_media=False)


def test_pagination_follows_max_id(monkeypatch, sleeps):
    pages = {None: [status(i) for i in range(0, 3)], "998": [status(i) for i in range(3, 5)], "996": []}

    def handler(path, params):
        assert path == "/api/v1/timelines/tag/ootd"
        assert params["only_media"] == "true" and params["limit"] == "40"
        return pages[params.get("max_id")]

    run, router = make(monkeypatch, handler, sleeps, max_posts=100, delay_s=1.0)
    recs, errs, rep = run()
    assert [c[1].get("max_id") for c in router.calls] == [None, "998", "996"]
    assert len(recs) == 5 and rep["records"] == 5 and rep["status"] == "completed" and not errs
    assert rep["api_calls"] == 3
    assert sleeps and all(s <= 1.0 for s in sleeps)   # the per-host delay was applied between calls


def test_max_posts_stops_paging(monkeypatch, sleeps):
    def handler(path, params):
        start = 0 if "max_id" not in params else 1000 - int(params["max_id"]) + 1
        return [status(i) for i in range(start, start + 40)]

    run, router = make(monkeypatch, handler, sleeps, max_posts=50)
    recs, _, rep = run()
    assert len(recs) == 50 and len(router.calls) == 2


def test_sensitive_and_spoiler_are_skipped_and_counted(monkeypatch, sleeps):
    page = [status(0), status(1, sensitive=True), status(2, spoiler="nsfw"), status(3)]
    run, _ = make(monkeypatch, lambda p, q: page if "max_id" not in q else [], sleeps)
    recs, _, rep = run()
    assert [r.account for r in recs] == ["u0@remote.example", "u3@remote.example"]
    assert rep["skipped_sensitive"] == 1 and rep["skipped_spoiler"] == 1 and rep["statuses_seen"] == 4


def test_html_strip_and_media_mapping():
    s = status(7, content='<p>Fit check &amp; <br>layers</p><p><a href="/tags/ootd">#<span>ootd</span></a></p>',
               media=("image", "video", "gifv", "image"))
    s["media_attachments"][3]["url"] = None                     # fall back to preview_url
    r = status_to_record("m", s, "mastodon.social#ootd")
    assert r.text == "Fit check & layers #ootd"
    assert r.image_urls == ["https://files.example/7_0.jpg", "https://files.example/7_3_small.jpg"]
    assert r.url == "https://mastodon.social/@u7/993" and r.page_type == "post"
    assert r.published_at == s["created_at"] and r.account == "u7@remote.example"
    assert r.brand is None and r.price is None
    assert r.field_origin["text"] == "mastodon:content"
    assert r.field_origin["image_urls"] == "mastodon:media_attachments"
    r2 = status_to_record("m", status(8, url=False))
    assert r2.url == "https://remote.example/users/u8/statuses/992" and r2.field_origin["url"] == "mastodon:uri"


def test_reblog_duplicates_by_url(monkeypatch, sleeps):
    orig = status(0)
    boost = status(1, reblog=orig)
    run, _ = make(monkeypatch, lambda p, q: [orig, boost] if "max_id" not in q else [], sleeps)
    recs, _, rep = run()
    assert len(recs) == 1 and rep["duplicates"] == 1


def test_duplicates_across_hashtags(monkeypatch, sleeps):
    run, _ = make(monkeypatch, lambda p, q: [status(0)] if "max_id" not in q else [], sleeps,
                  hashtags=["ootd", "fashion"])
    recs, _, rep = run()
    assert len(recs) == 1 and rep["duplicates"] == 1


def test_429_stops_the_source(monkeypatch, sleeps):
    def handler(path, params):
        return urllib.error.HTTPError("https://mastodon.social" + path, 429, "Too Many Requests",
                                      {"Retry-After": "1"}, io.BytesIO(b'{"error":"Too many requests"}'))

    run, router = make(monkeypatch, handler, sleeps, hashtags=["ootd", "fashion"])
    recs, errs, rep = run()
    assert rep["status"] == "stopped" and rep["stop_reason"] == "rate_limited"
    assert recs == [] and errs[-1]["kind"] == "stopped:rate_limited"
    assert len(router.calls) == 2              # one retry after Retry-After, then stop; "fashion" never tried


def test_401_stops_the_source(monkeypatch, sleeps):
    def handler(path, params):
        return urllib.error.HTTPError("https://mastodon.social" + path, 401, "Unauthorized", {},
                                      io.BytesIO(b'{"error":"This API requires an authenticated user"}'))

    run, _ = make(monkeypatch, handler, sleeps)
    _, _, rep = run()
    assert rep["status"] == "stopped" and rep["stop_reason"] == "access_denied"


def test_robots_disallow_means_no_api_call(monkeypatch, sleeps):
    run, router = make(monkeypatch, lambda p, q: [status(0)], sleeps,
                       robots_body=b"User-agent: *\nDisallow: /api/\n")
    recs, errs, rep = run()
    assert router.calls == [] and recs == []
    assert rep["status"] == "stopped" and rep["stop_reason"] == "robots_disallow"
    assert errs[0]["kind"] == "robots:parsed"


def test_error_body_is_logged_not_raised(monkeypatch, sleeps):
    run, _ = make(monkeypatch, lambda p, q: {"error": "Record not found"}, sleeps)
    recs, errs, rep = run()
    assert recs == [] and rep["status"] == "completed" and errs[0]["kind"] == "fetch_error"
