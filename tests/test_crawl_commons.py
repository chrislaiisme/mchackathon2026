"""Offline tests for the Wikimedia Commons source: the HTTP layer (urlopen inside engine02.crawl.http)
is replaced by a router that answers with canned MediaWiki Action API JSON."""

from __future__ import annotations

import io
import json
import urllib.error
from urllib.parse import parse_qs, urlsplit

import pytest

from engine02.crawl import USER_AGENT
from engine02.crawl import http as http_mod
from engine02.crawl.commons import CommonsSource, run, strip_html
from engine02.crawl.http import Blocked, Fetcher


class FakeResp:
    def __init__(self, url, body: dict, headers=None, status=200):
        self._url, self.status = url, status
        self._body = json.dumps(body).encode("utf-8")
        self.headers = {"Content-Type": "application/json; charset=utf-8", **(headers or {})}

    def read(self, n=-1):
        return self._body

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Router:
    """Records every request; `handler(params) -> dict | (dict, headers) | Exception`."""

    def __init__(self, handler):
        self.handler, self.calls = handler, []

    def __call__(self, req, timeout=None):
        url = req.full_url
        assert req.get_header("User-agent") == USER_AGENT
        params = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
        self.calls.append(params)
        out = self.handler(params)
        if isinstance(out, Exception):
            raise out
        body, headers = out if isinstance(out, tuple) else (out, None)
        return FakeResp(url, body, headers)


@pytest.fixture
def sleeps():
    return []


def make(monkeypatch, handler, sleeps, **kw):
    router = Router(handler)
    monkeypatch.setattr(http_mod.urllib.request, "urlopen", router)
    fetcher = Fetcher(None, min_delay_s=kw.pop("delay_s", 1.0), sleep=sleeps.append)
    kw.setdefault("categories", ["Catwalks (fashion)"])
    kw.setdefault("max_files", 10)
    src = CommonsSource(name="commons_test", fetcher=fetcher, sleep=sleeps.append, **kw)
    return src, router


def ext(**fields):
    return {k: {"value": v, "source": "commons-desc-page"} for k, v in fields.items()}


def image(title, mime="image/jpeg", cats=(), **meta):
    slug = title.split(":", 1)[1].replace(" ", "_")
    return {"ns": 6, "title": title, "categories": [{"ns": 14, "title": c} for c in cats],
            "imageinfo": [{"size": 1000, "width": 2000, "height": 3000, "mime": mime,
                           "url": f"https://upload.wikimedia.org/wikipedia/commons/a/ab/{slug}",
                           "thumburl": f"https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/{slug}/800px-{slug}"
                                       "?utm_source=commons.wikimedia.org&utm_campaign=imageinfo",
                           "descriptionurl": f"https://commons.wikimedia.org/wiki/{title.replace(' ', '_')}",
                           "extmetadata": ext(**meta)}]}


def members(*items, cont=None):
    body = {"batchcomplete": True, "query": {"categorymembers": [
        {"pageid": i, "ns": 14 if t.startswith("Category:") else 6, "title": t,
         "type": "subcat" if t.startswith("Category:") else "file"} for i, t in enumerate(items)]}}
    if cont:
        body["continue"] = {"cmcontinue": cont, "continue": "-||"}
        body.pop("batchcomplete")
    return body


def info_for(params, images: dict):
    return {"batchcomplete": True,
            "query": {"pages": [images[t] for t in params["titles"].split("|") if t in images]}}


# ------------------------------------------------------------------------------------------------
def test_strip_html():
    assert strip_html('<a href="//x">Jane&nbsp;Doe</a> <span>(photo)</span>') == "Jane Doe (photo)"
    assert strip_html("<div>  </div>") is None
    assert strip_html(None) is None


def test_walk_subcat_continuation_and_mapping(monkeypatch, sleeps):
    imgs = {
        "File:A.jpg": image("File:A.jpg", ObjectName="Runway look A",
                            ImageDescription='<p>Model at <a href="/wiki/X">Paris&nbsp;Fashion Week</a> &amp; more</p>',
                            DateTimeOriginal='<time datetime="2019-03-01">1 March 2019</time>',
                            DateTime="2020-01-01 10:00:00", LicenseShortName="CC BY-SA 4.0",
                            LicenseUrl="https://creativecommons.org/licenses/by-sa/4.0",
                            Artist='<a href="//commons.wikimedia.org/wiki/User:Jane">Jane Doe</a>',
                            Credit='<span class="int-own-work">Own work</span>'),
        "File:B.png": image("File:B.png", mime="image/png", DateTime="2021-05-05 00:00:00",
                            LicenseShortName="CC BY 2.0"),
        "File:C.jpg": image("File:C.jpg", LicenseShortName="CC0"),
    }

    def handler(p):
        assert p["format"] == "json" and p["maxlag"] == "5" and p["action"] == "query"
        if p.get("list") == "categorymembers":
            assert p["cmtype"] == "file|subcat"
            if p["cmtitle"] == "Category:Catwalks (fashion)":
                if "cmcontinue" not in p:
                    return members("Category:Runway 2019", "File:A.jpg", cont="file|B|2")
                assert p["cmcontinue"] == "file|B|2"
                return members("File:B.png")
            if p["cmtitle"] == "Category:Runway 2019":
                return members("File:C.jpg")
            raise AssertionError(p)
        assert p["prop"] == "imageinfo|categories"
        assert p["iiprop"] == "url|extmetadata|mime|size" and p["iiurlwidth"] == "800"
        return info_for(p, imgs)

    src, router = make(monkeypatch, handler, sleeps, depth=1)
    recs, errors = run(src)
    assert errors == []
    assert [r.url.rsplit("/", 1)[1] for r in recs] == ["File:A.jpg", "File:B.png", "File:C.jpg"]
    a = recs[0]
    assert a.source == "commons_test" and a.page_type == "image"
    assert a.title == "Runway look A"
    assert a.text == "Model at Paris Fashion Week & more"
    assert a.published_at == "1 March 2019"
    assert a.brand is None and a.price is None
    assert a.image_urls[0].endswith("800px-A.jpg") and a.image_urls[1].endswith("/A.jpg")
    fo = a.field_origin
    assert fo["license"] == "CC BY-SA 4.0"
    assert fo["license_url"] == "https://creativecommons.org/licenses/by-sa/4.0"
    assert fo["author"] == "Jane Doe" and fo["credit"] == "Own work"
    assert fo["published_at"] == "commons:extmetadata.DateTimeOriginal"
    b = recs[1]
    assert b.title == "B.png" and b.field_origin["title"] == "commons:page_title"   # no ObjectName
    assert b.published_at == "2021-05-05 00:00:00" and b.field_origin["published_at"].endswith("DateTime")
    assert b.text is None and b.field_origin["author"] == ""
    # spacing: the fetcher is asked to wait between consecutive API calls (serial)
    assert len(router.calls) >= 4 and sleeps


def test_depth_zero_does_not_enter_subcats(monkeypatch, sleeps):
    def handler(p):
        if p.get("list") == "categorymembers":
            assert p["cmtitle"] == "Category:Catwalks (fashion)"
            return members("Category:Runway 2019", "File:A.jpg")
        return info_for(p, {"File:A.jpg": image("File:A.jpg")})

    src, _ = make(monkeypatch, handler, sleeps, depth=0)
    recs, _ = run(src)
    assert len(recs) == 1


def test_exclusion_of_files_and_subcats(monkeypatch, sleeps):
    imgs = {"File:Ok.jpg": image("File:Ok.jpg", cats=["Category:Fashion shows"]),
            "File:Bad.jpg": image("File:Bad.jpg", cats=["Category:Victoria's Secret LINGERIE SHOWS 2015"]),
            "File:Fur.jpg": image("File:Fur.jpg", cats=["Category:Furry fandom"]),
            "File:Vid.webm": image("File:Vid.webm", mime="video/webm")}

    def handler(p):
        if p.get("list") == "categorymembers":
            assert p["cmtitle"] != "Category:Nude fashion", "excluded subcategory was walked"
            return members("Category:Nude fashion", "File:Ok.jpg", "File:Bad.jpg", "File:Fur.jpg", "File:Vid.webm")
        return info_for(p, imgs)

    src, _ = make(monkeypatch, handler, sleeps)
    recs, _ = run(src)
    assert [r.title for r in recs] == ["Ok.jpg"]
    assert src.report["excluded"] == 2 and src.report["subcats_excluded"] == 1 and src.report["wrong_mime"] == 1


def test_exclusion_list_is_a_parameter(monkeypatch, sleeps):
    imgs = {"File:Fur.jpg": image("File:Fur.jpg", cats=["Category:Furry fandom"])}

    def handler(p):
        if p.get("list") == "categorymembers":
            return members("File:Fur.jpg")
        return info_for(p, imgs)

    src, _ = make(monkeypatch, handler, sleeps, exclude_categories=["Topless"])
    assert len(run(src)[0]) == 1


def test_max_files_cap_and_lazy_walk(monkeypatch, sleeps):
    names = [f"File:F{i}.jpg" for i in range(20)]
    imgs = {n: image(n) for n in names}

    def handler(p):
        if p.get("list") == "categorymembers":
            if "cmcontinue" in p:
                raise AssertionError("walked past what max_files needed")
            return members(*names[:10], cont="file|X|1")
        assert len(p["titles"].split("|")) <= 3
        return info_for(p, imgs)

    src, _ = make(monkeypatch, handler, sleeps, max_files=3)
    recs, _ = run(src)
    assert len(recs) == 3


def test_dedup_file_in_two_categories(monkeypatch, sleeps):
    imgs = {"File:A.jpg": image("File:A.jpg"), "File:B.jpg": image("File:B.jpg")}

    def handler(p):
        if p.get("list") == "categorymembers":
            if p["cmtitle"] == "Category:Catwalks (fashion)":
                return members("File:A.jpg", "Category:Cosplayers")
            return members("File:A.jpg", "File:B.jpg", "Category:Catwalks (fashion)")   # a cycle too
        return info_for(p, imgs)

    src, router = make(monkeypatch, handler, sleeps, categories=["Catwalks (fashion)", "Cosplayers"])
    recs, _ = run(src)
    assert sorted(r.title for r in recs) == ["A.jpg", "B.jpg"]
    assert src.report["duplicates"] == 1
    assert sum(1 for c in router.calls if c.get("list") == "categorymembers") == 2


def test_maxlag_retry(monkeypatch, sleeps):
    state = {"lagged": 0}

    def handler(p):
        if p.get("list") == "categorymembers":
            if state["lagged"] < 2:
                state["lagged"] += 1
                return ({"error": {"code": "maxlag", "info": "Waiting for db1: 7 seconds lagged",
                                   "host": "db1", "lag": 7}}, {"Retry-After": "5", "X-Database-Lag": "7"})
            return members("File:A.jpg")
        return info_for(p, {"File:A.jpg": image("File:A.jpg")})

    src, _ = make(monkeypatch, handler, sleeps, delay_s=0)
    recs, errors = run(src)
    assert len(recs) == 1 and errors == []
    assert sleeps.count(7.0) == 2


def test_maxlag_wait_capped_and_gives_up(monkeypatch, sleeps):
    def handler(p):
        return {"error": {"code": "maxlag", "info": "Waiting for db1: 120 seconds lagged", "lag": 120}}

    src, router = make(monkeypatch, handler, sleeps, delay_s=0)
    recs, errors = run(src)
    assert recs == [] and len(router.calls) == 3          # first try + two retries
    assert sleeps == [30.0, 30.0]
    assert errors[0]["kind"] == "stopped:server_lagged"


def test_429_is_blocked(monkeypatch, sleeps):
    def handler(p):
        return urllib.error.HTTPError("https://commons.wikimedia.org/w/api.php", 429, "Too Many Requests",
                                      {"Retry-After": "1"}, io.BytesIO(b"slow down"))

    src, _ = make(monkeypatch, handler, sleeps)
    with pytest.raises(Blocked) as ei:
        list(src.records())
    assert ei.value.reason == "rate_limited" and ei.value.status == 429

    src2, _ = make(monkeypatch, handler, sleeps)
    recs, errors = run(src2)
    assert recs == [] and errors[-1]["kind"] == "stopped:rate_limited"
    assert src2.report["status"] == "stopped"


def test_403_and_ratelimited_api_code_are_blocked(monkeypatch, sleeps):
    def forbidden(p):
        return urllib.error.HTTPError("https://commons.wikimedia.org/w/api.php", 403, "Forbidden", {},
                                      io.BytesIO(b"Please set a user-agent"))

    src, _ = make(monkeypatch, forbidden, sleeps)
    with pytest.raises(Blocked) as ei:
        list(src.records())
    assert ei.value.reason == "access_denied"

    src2, _ = make(monkeypatch, lambda p: {"error": {"code": "ratelimited", "info": "You've exceeded your rate limit"}},
                   sleeps)
    with pytest.raises(Blocked) as ei:
        list(src2.records())
    assert ei.value.reason == "rate_limited"


def test_other_api_error_is_logged_not_fatal(monkeypatch, sleeps):
    def handler(p):
        if p.get("list") == "categorymembers":
            if p["cmtitle"] == "Category:Nope":
                return {"error": {"code": "cminvalidcategory", "info": "The category name you entered is not valid."}}
            return members("File:A.jpg")
        return info_for(p, {"File:A.jpg": image("File:A.jpg")})

    src, _ = make(monkeypatch, handler, sleeps, categories=["Nope", "Catwalks (fashion)"])
    recs, errors = run(src)
    assert len(recs) == 1
    assert errors[0]["kind"] == "fetch_error" and "cminvalidcategory" in errors[0]["detail"]
