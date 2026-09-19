"""engine02.crawl against a real local HTTP server: robots, stop signals, extraction, rate limit,
cache, de-duplication, export, and the Instagram module. No external network."""

from __future__ import annotations

import csv
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from engine02.crawl.extract import extract
from engine02.crawl.http import Blocked, Fetcher, challenge_in
from engine02.crawl.instagram import (GraphClient, GraphStop, InstagramAPIConfig, fix_meta_text,
                                      run_instagram_api, run_instagram_export, scrub)
from engine02.crawl.records import Record, export, normalize_url
from engine02.crawl.robots import Robots
from engine02.crawl.web import WebSourceConfig, run_web

PRODUCT_JSONLD = """<html><head><title>Wool coat | Shop</title>
<script type="application/ld+json">{"@context":"https://schema.org","@type":"Product","name":"Wool coat",
"brand":{"@type":"Brand","name":"Acme"},"description":"A long wool coat.","image":["/img/coat.jpg"],
"offers":{"@type":"Offer","price":"1290","priceCurrency":"TWD"}}</script>
<meta property="og:image" content="/img/coat-og.jpg"></head><body>
<footer><form><div class="g-recaptcha" data-sitekey="x"></div></form></footer></body></html>"""
PRODUCT_OG = """<html><head><meta property="og:type" content="product"><meta property="og:title" content="Linen shirt">
<meta property="product:price:amount" content="890"><meta property="product:price:currency" content="TWD">
<meta property="product:brand" content="Brandy"><meta property="og:image" content="/img/shirt.jpg"></head>
<body><img src="/img/pixel.png" width="1" height="1"><img src="/img/a.jpg" srcset="/img/a-2x.jpg 2x"></body></html>"""
PRODUCT_PROSE_PRICE = """<html><head><meta property="og:type" content="product"><meta property="og:title" content="Tee">
</head><body><p>Now only NT$990! Brand: Nobody</p></body></html>"""
ARTICLE = """<html><head><script type="application/ld+json">{"@type":"BlogPosting","headline":"Fall looks",
"articleBody":"Layer a trench over knitwear.","datePublished":"2026-09-01","image":"/img/look.jpg"}</script></head></html>"""
LISTING = """<html><head><title>New in</title></head><body>
<a href="/p/1">1</a><a href="/p/1?utm_source=x&fbclid=y">1 again</a><a href="/p/2">2</a><a href="/p/3">3</a>
<a href="/article/1">a</a><a href="/private/secret">no</a><a href="https://elsewhere.test/x">ext</a>
<a href="/p/1-copy">copy</a></body></html>"""
COPY = PRODUCT_JSONLD.replace("<head>", '<head><link rel="canonical" href="/p/1-copy">')
CF = "<html><head><title>Just a moment...</title></head><body>checking</body></html>"


class Site:
    """Routes: path -> (status, headers, body). Records every hit with its time."""

    def __init__(self, routes):
        self.routes, self.hits = routes, []
        site = self

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                site.hits.append((self.path, time.monotonic()))
                route = site.routes.get(self.path.split("?")[0])
                if callable(route):
                    route = route(self)
                status, headers, body = route or (404, {}, "not found")
                self.send_response(status)
                for k, v in {"Content-Type": "text/html; charset=utf-8", **headers}.items():
                    self.send_header(k, v)
                data = body.encode("utf-8") if isinstance(body, str) else body
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def count(self, path):
        return sum(1 for p, _ in self.hits if p.split("?")[0] == path)

    def close(self):
        self.server.shutdown()


@pytest.fixture
def shop():
    s = Site({
        "/robots.txt": (200, {"Content-Type": "text/plain"}, "User-agent: *\nDisallow: /private/\n"),
        "/list": (200, {}, LISTING), "/p/1": (200, {}, PRODUCT_JSONLD), "/p/2": (200, {}, PRODUCT_OG),
        "/p/3": (200, {}, PRODUCT_PROSE_PRICE), "/article/1": (200, {}, ARTICLE),
        "/p/1-copy": (200, {}, COPY), "/private/secret": (200, {}, PRODUCT_JSONLD),
    })
    yield s
    s.close()


def crawl(site, tmp_path, start="/list", **kw):
    f = Fetcher(tmp_path / "cache", min_delay_s=kw.pop("delay", 0.0), sleep=time.sleep)
    cfg = WebSourceConfig(name="shop", start_urls=[site.base + start], max_pages=kw.pop("max_pages", 30), **kw)
    return (*run_web(cfg, f, Robots()), f)


# ---- extraction: structured data only -------------------------------------------------------
def test_product_fields_come_only_from_structured_data():
    p = extract(PRODUCT_JSONLD, "http://x.test/p/1")
    assert (p["title"], p["brand"], p["price"], p["currency"]) == ("Wool coat", "Acme", "1290", "TWD")
    assert p["field_origin"]["price"] == "jsonld:Offer.price"
    assert p["field_origin"]["brand"] == "jsonld:Product.brand"
    assert p["image_urls"][:2] == ["http://x.test/img/coat-og.jpg", "http://x.test/img/coat.jpg"]
    o = extract(PRODUCT_OG, "http://x.test/p/2")
    assert (o["brand"], o["price"], o["page_type"]) == ("Brandy", "890", "product")
    assert "http://x.test/img/pixel.png" not in o["image_urls"]          # 1x1 tracking pixel
    assert "http://x.test/img/a-2x.jpg" in o["image_urls"]               # srcset candidate


def test_a_price_in_prose_is_never_read():
    p = extract(PRODUCT_PROSE_PRICE, "http://x.test/p/3")
    assert p["price"] is None and p["brand"] is None and p["currency"] is None
    assert "price" not in p["field_origin"]


def test_aggregate_offer_says_it_is_a_low_price():
    html = ('<script type="application/ld+json">{"@type":"Product","name":"x","offers":'
            '{"@type":"AggregateOffer","lowPrice":"490","priceCurrency":"TWD"}}</script>')
    p = extract(html, "http://x.test/")
    assert p["price"] == "490" and p["field_origin"]["price"] == "jsonld:AggregateOffer.lowPrice"
    assert p["field_origin"]["currency"] == "jsonld:AggregateOffer.priceCurrency"


def test_microdata_brand_text_survives_void_elements():
    html = ('<div itemscope itemtype="https://schema.org/Product"><img src="/a.jpg"><br>'
            '<span itemprop="brand">Mono<br>Label</span><meta itemprop="price" content="1500">'
            '<meta itemprop="priceCurrency" content="TWD"></div>')
    p = extract(html, "http://x.test/")
    assert p["brand"] == "MonoLabel" and p["price"] == "1500"


# ---- the crawl loop -------------------------------------------------------------------------
def test_crawl_records_dedup_and_robots(shop, tmp_path):
    recs, errs, rep, _ = crawl(shop, tmp_path)
    urls = {r.url for r in recs}
    assert normalize_url(shop.base + "/p/1") in urls
    assert normalize_url(shop.base + "/article/1") in urls
    assert shop.count("/private/secret") == 0                          # disallowed: never requested
    assert rep["robots_disallowed"] == 1 and rep["status"] == "completed"
    assert shop.count("/p/1") == 1                                      # utm/fbclid variant = same page
    assert rep["duplicates"] == 1                                       # /p/1-copy: same content
    assert all(r.page_type in ("product", "article") for r in recs)     # the listing is not a record
    tee = next(r for r in recs if r.title == "Tee")
    assert tee.price is None and tee.brand is None                      # missing stays missing


def test_rate_limit_spaces_requests(shop, tmp_path):
    crawl(shop, tmp_path, delay=0.3, max_pages=3)
    times = [t for p, t in shop.hits if p != "/robots.txt"]
    assert len(times) >= 3
    assert min(b - a for a, b in zip(times, times[1:])) >= 0.28


def test_second_run_is_served_from_cache(shop, tmp_path):
    crawl(shop, tmp_path)
    before = len([p for p, _ in shop.hits if p != "/robots.txt"])
    recs, _, rep, f = crawl(shop, tmp_path)
    after = len([p for p, _ in shop.hits if p != "/robots.txt"])
    assert after == before and f.network_requests == 0 and rep["from_cache"] == rep["pages_fetched"]
    assert len(recs) > 0


def test_conditional_get_revalidates_stale_cache(tmp_path):
    s = Site({"/robots.txt": (404, {}, ""),
              "/p": lambda h: (304, {}, "") if h.headers.get("If-None-Match") == '"v1"'
              else (200, {"ETag": '"v1"'}, PRODUCT_JSONLD)})
    try:
        f = Fetcher(tmp_path / "c", cache_ttl_s=0, min_delay_s=0)
        first = f.get(s.base + "/p")
        second = f.get(s.base + "/p")
        assert not first.from_cache and second.from_cache and second.body == first.body
        assert s.count("/p") == 2                                        # asked, got 304, reused
    finally:
        s.close()


@pytest.mark.parametrize("route,reason", [
    ((302, {"Location": "/accounts/login?next=/p"}, ""), "login_required"),
    ((200, {}, CF), "captcha"),
    ((503, {}, CF), "captcha"),
    ((403, {}, "forbidden"), "access_denied"),
    ((451, {}, "legal"), "access_denied"),
])
def test_stop_signals_stop_the_source(tmp_path, route, reason):
    s = Site({"/robots.txt": (404, {}, ""), "/list": (200, {}, '<a href="/p">p</a><a href="/q">q</a>'),
              "/p": route, "/q": (200, {}, PRODUCT_JSONLD),
              "/accounts/login": (200, {}, "<title>Log in</title><input type=\"password\">")})
    try:
        recs, errs, rep, _ = crawl(s, tmp_path)
        assert rep["status"] == "stopped" and rep["stop_reason"] == reason
        assert s.count("/q") == 0                                        # nothing after the stop
        assert any(e["kind"] == f"stopped:{reason}" for e in errs)
    finally:
        s.close()


def test_footer_recaptcha_on_a_real_product_page_is_not_a_block():
    assert challenge_in(PRODUCT_JSONLD) is None
    assert challenge_in("<html><body><div class='g-recaptcha'></div></body></html>") == "recaptcha"


def test_429_honours_retry_after_then_gives_up(tmp_path):
    n = {"k": 0}

    def flaky(h):
        n["k"] += 1
        return (429, {"Retry-After": "0"}, "") if n["k"] < 2 else (200, {}, PRODUCT_JSONLD)
    s = Site({"/robots.txt": (404, {}, ""), "/ok": flaky, "/never": (429, {"Retry-After": "0"}, ""),
              "/long": (429, {"Retry-After": "3600"}, "")})
    try:
        f = Fetcher(None, min_delay_s=0, max_retries=2)
        assert f.get(s.base + "/ok").status == 200
        with pytest.raises(Blocked) as e:
            f.get(s.base + "/never")
        assert e.value.reason == "rate_limited"
        with pytest.raises(Blocked) as e:
            f.get(s.base + "/long")
        assert "exceeds" in e.value.detail and s.count("/long") == 1     # did not sit for an hour
    finally:
        s.close()


def test_every_seed_disallowed_is_a_stop_not_a_completion(tmp_path):
    s = Site({"/robots.txt": (200, {"Content-Type": "text/plain"}, "User-agent: *\nDisallow: /\n"),
              "/list": (200, {}, LISTING)})
    try:
        recs, errs, rep, f = crawl(s, tmp_path)
        assert rep["status"] == "stopped" and rep["stop_reason"] == "robots_disallowed_all_seeds"
        assert s.count("/list") == 0 and f.network_requests == 0 and recs == []
    finally:
        s.close()


def test_unreachable_robots_means_disallow_all(tmp_path):
    s = Site({"/robots.txt": (500, {}, ""), "/list": (200, {}, LISTING)})
    try:
        recs, errs, rep, _ = crawl(s, tmp_path)
        assert rep["stop_reason"] == "robots_unreachable" and s.count("/list") == 0
    finally:
        s.close()


def test_export_leaves_missing_fields_empty(tmp_path):
    recs = [Record(source="s", url="http://x.test/a", title="A", image_urls=["u1", "u2"]),
            Record(source="s", url="http://x.test/b", brand="B", price="10", currency="TWD")]
    paths = export(recs, tmp_path)
    rows = list(csv.DictReader(open(paths["csv"], encoding="utf-8-sig")))
    assert rows[0]["image_urls"] == "u1 | u2" and rows[0]["price"] == "" and rows[0]["brand"] == ""
    js = json.loads(open(paths["json"], encoding="utf-8").read())
    assert js[0]["price"] is None and js[1]["image_urls"] == []


# ---- Instagram ----------------------------------------------------------------------------------
class FakeGraph:
    def __init__(self, pages):
        self.pages, self.urls = pages, []

    def __call__(self, req, timeout=30):
        self.urls.append(req.full_url)
        body = self.pages.pop(0)
        if isinstance(body, Exception):
            raise body
        import io

        class R(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        return R(json.dumps(body).encode())


def test_graph_own_media_pagination_and_mapping():
    pages = [{"data": [{"id": "1", "media_type": "IMAGE", "media_url": "https://cdn/1.jpg",
                        "permalink": "https://www.instagram.com/p/A/", "caption": "fall fit", "timestamp": "2026-09-01"},
                       {"id": "2", "media_type": "VIDEO", "media_url": "https://cdn/2.mp4",
                        "thumbnail_url": "https://cdn/2.jpg", "permalink": "https://www.instagram.com/p/B/"}],
              "paging": {"next": "https://graph.facebook.com/v25.0/me/media?after=x&access_token=SECRET"}},
             {"data": [{"id": "3", "media_type": "CAROUSEL_ALBUM", "media_url": "https://cdn/3.jpg",
                        "permalink": "https://www.instagram.com/p/C/",
                        "children": {"data": [{"media_type": "IMAGE", "media_url": "https://cdn/3b.jpg"}]}}]}]
    fake = FakeGraph(pages)
    cfg = InstagramAPIConfig(name="ig", mode="own_media", delay_s=0)
    recs, errs, rep = run_instagram_api(cfg, GraphClient(cfg, "SECRET", "123", opener=fake, sleep=lambda s: None))
    assert rep["status"] == "completed" and rep["records"] == 3 and rep["api_calls"] == 2
    by = {r.url: r for r in recs}
    assert by["https://www.instagram.com/p/B/"].image_urls == ["https://cdn/2.jpg"]   # thumbnail, not the mp4
    assert by["https://www.instagram.com/p/C/"].image_urls == ["https://cdn/3.jpg", "https://cdn/3b.jpg"]
    assert all(r.brand is None and r.price is None for r in recs)


def test_graph_error_stops_and_never_leaks_the_token():
    import io
    import urllib.error
    err = urllib.error.HTTPError("https://graph.facebook.com/x?access_token=SECRET", 400, "Bad", {},
                                 io.BytesIO(json.dumps({"error": {"code": 190, "type": "OAuthException",
                                                                  "message": "expired"}}).encode()))
    cfg = InstagramAPIConfig(name="ig", mode="own_media", delay_s=0)
    recs, errs, rep = run_instagram_api(cfg, GraphClient(cfg, "SECRET", "1", opener=FakeGraph([err]),
                                                         sleep=lambda s: None))
    assert rep["status"] == "stopped" and rep["stop_reason"] == "auth_invalid"
    assert "SECRET" not in json.dumps(rep) and "SECRET" not in json.dumps(errs)
    assert scrub("https://g/x?a=1&access_token=abc&b=2") == "https://g/x?a=1&access_token=***&b=2"


def test_graph_business_discovery_request_shape():
    fake = FakeGraph([{"business_discovery": {"username": "brand", "media": {"data": [
        {"id": "9", "media_type": "IMAGE", "media_url": "u", "permalink": "https://www.instagram.com/p/Z/"}]}}}])
    cfg = InstagramAPIConfig(name="ig", mode="business_discovery", usernames=["brand"], delay_s=0)
    recs, _, rep = run_instagram_api(cfg, GraphClient(cfg, "T", "42", opener=fake, sleep=lambda s: None))
    from urllib.parse import unquote
    assert "business_discovery.username(brand){username,media.limit(50){" in unquote(fake.urls[0])
    assert recs[0].account == "brand" and rep["records"] == 1


def test_missing_credentials_is_reported_not_raised(monkeypatch):
    monkeypatch.delenv("IG_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("IG_USER_ID", raising=False)
    monkeypatch.setattr("engine02.crawl.instagram._env", lambda k: None)
    recs, _, rep = run_instagram_api(InstagramAPIConfig(name="ig", mode="own_media"))
    assert rep["status"] == "not_run" and rep["stop_reason"] == "missing_credentials" and recs == []


def test_owner_export_parsing_and_mojibake(tmp_path):
    mangled = "秋冬穿搭".encode("utf-8").decode("latin-1")
    (tmp_path / "media" / "posts").mkdir(parents=True)
    (tmp_path / "media" / "posts" / "1.jpg").write_bytes(b"x")
    (tmp_path / "posts_1.json").write_text(json.dumps([
        {"media": [{"uri": "media/posts/1.jpg", "creation_timestamp": 1757000000, "title": mangled}]},
        {"media": [{"uri": "media/posts/1.jpg", "creation_timestamp": 1757000000}]}]), encoding="utf-8")
    (tmp_path / "unknown.json").write_text(json.dumps({"something_else": [1, 2]}), encoding="utf-8")
    (tmp_path / "mine.csv").write_text("url,caption,image_url\nhttps://www.instagram.com/p/Q/,hi,https://c/q.jpg\n",
                                       encoding="utf-8")
    recs, errs, rep = run_instagram_export("ig_export", tmp_path)
    texts = {r.text for r in recs}
    assert "秋冬穿搭" in texts and rep["records"] == 2                   # duplicate media collapsed
    assert any(u["file"].endswith("unknown.json") for u in rep["unrecognised_files"])
    assert fix_meta_text("plain") == "plain"
