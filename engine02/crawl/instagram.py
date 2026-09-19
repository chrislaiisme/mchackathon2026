"""Instagram, as its own source -- through the official Graph API or data the account owner exported.

Why there is no page scraper here (checked 2026-09-19, not assumed):
  * technically possible: an anonymous GET of https://www.instagram.com/hm/ returns HTTP 200;
  * explicitly prohibited: instagram.com/robots.txt ends with "User-agent: * / Disallow: /" and
    opens with "Collection of data on Instagram through automated means is prohibited unless you
    have express written permission from Instagram". The generic web crawler therefore refuses it
    on robots.txt grounds, and this module does not add a way around that.

What IS supported:

1. Graph API (needs IG_ACCESS_TOKEN and IG_USER_ID of an Instagram professional account, in the
   environment or .env; never written anywhere):
     mode = "own_media"           GET /{ig-user-id}/media
     mode = "business_discovery"  GET /{ig-user-id}?fields=business_discovery.username(X){...media{...}}
                                  -- public posts of OTHER business/creator accounts, e.g. brands
     mode = "hashtag"             GET /ig_hashtag_search -> /{hashtag-id}/top_media|recent_media
                                  (recent_media returns only the last 24 h, per the docs)
   Endpoints and field syntax checked against developers.facebook.com (Instagram Platform docs).

2. Your own export ("Download your information", JSON format), a directory or a single .json.
   The parser looks for media objects with a "uri" and groups them by post; Meta exports encode
   non-ASCII text as mis-decoded UTF-8 ("\\u00e5\\u00a5..."), which is repaired. If a file has a
   structure this parser does not recognise it is REPORTED, not guessed at.

3. A CSV you prepare: columns url|permalink, caption|text, image_url(s)|media_url, timestamp,
   account|username (case-insensitive; several image URLs separated by " | ").

Brand and price are never filled: an Instagram post does not state them in structured form, and
the posting account is recorded as `account`, which is not the same thing as a brand.
"""

from __future__ import annotations

import csv
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import USER_AGENT
from .records import Record

GRAPH = "https://graph.facebook.com"
DEFAULT_FIELDS = "id,caption,media_type,media_url,permalink,timestamp,children{media_url,media_type}"
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp", ".heic")


def scrub(url: str) -> str:
    """Never let a token reach a log line or a report."""
    return re.sub(r"(access_token=)[^&]+", r"\1***", url or "")


class GraphStop(Exception):
    def __init__(self, reason: str, detail: str):
        super().__init__(f"{reason}: {detail}")
        self.reason, self.detail = reason, detail


def classify_graph_error(err: dict) -> str:
    code = err.get("code")
    if code == 190:
        return "auth_invalid"
    if code in (4, 17, 32, 613, 80002, 80006):
        return "rate_limited"
    if code == 24 or err.get("error_subcode") == 2207049:
        return "hashtag_limit"
    if code == 10 or (isinstance(code, int) and 200 <= code <= 299):
        return "permission_denied"
    if code == 100:
        return "invalid_parameter"
    return "api_error"


@dataclass
class InstagramAPIConfig:
    name: str
    mode: str                                     # own_media | business_discovery | hashtag
    usernames: list[str] = field(default_factory=list)
    hashtags: list[str] = field(default_factory=list)
    hashtag_edge: str = "top_media"               # top_media | recent_media
    max_posts: int = 100
    fields: str = DEFAULT_FIELDS
    api_version: str = "v25.0"
    delay_s: float = 1.0


def _env(key: str) -> str | None:
    v = os.environ.get(key, "").strip()
    if v:
        return v
    env = Path(__file__).resolve().parents[2] / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'") or None
    return None


def _to_record(m: dict, source: str, account: str | None) -> Record:
    kind = (m.get("media_type") or "").upper()
    imgs: list[str] = []
    if kind == "VIDEO":
        if m.get("thumbnail_url"):
            imgs.append(m["thumbnail_url"])        # media_url of a video is the video itself
    elif m.get("media_url"):
        imgs.append(m["media_url"])
    for ch in ((m.get("children") or {}).get("data") or []):
        u = ch.get("thumbnail_url") if (ch.get("media_type") or "").upper() == "VIDEO" else ch.get("media_url")
        if u and u not in imgs:
            imgs.append(u)
    origin = {k: v for k, v in (("text", "graph:caption" if m.get("caption") else None),
                                ("image_urls", "graph:media_url" if imgs else None),
                                ("published_at", "graph:timestamp" if m.get("timestamp") else None)) if v}
    return Record(source=source, url=m.get("permalink") or f"instagram:media:{m.get('id')}",
                  text=m.get("caption"), image_urls=imgs, published_at=m.get("timestamp"),
                  account=m.get("username") or account, page_type="post",
                  fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"), field_origin=origin)


class GraphClient:
    def __init__(self, cfg: InstagramAPIConfig, token: str, user_id: str, opener=None, sleep=time.sleep):
        self.cfg, self.token, self.user_id = cfg, token, user_id
        self._open = opener or urllib.request.urlopen
        self._sleep = sleep
        self.calls = 0

    def get(self, path_or_url: str, **params) -> dict:
        if path_or_url.startswith("http"):
            url = path_or_url                        # a paging.next link already carries everything
        else:
            q = dict(params, access_token=self.token)
            url = f"{GRAPH}/{self.cfg.api_version}/{path_or_url.lstrip('/')}?{urllib.parse.urlencode(q)}"
        if self.calls:
            self._sleep(self.cfg.delay_s)
        self.calls += 1
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with self._open(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                err = json.loads(e.read().decode("utf-8")).get("error", {})
            except (ValueError, AttributeError):
                err = {}
            raise GraphStop(classify_graph_error(err) if err else f"http_{e.code}",
                            f"HTTP {e.code} {err.get('type', '')} code={err.get('code')} "
                            f"subcode={err.get('error_subcode')}: {err.get('message', '')} [{scrub(url)}]")
        except (urllib.error.URLError, OSError) as e:
            raise GraphStop("network_error", f"{type(e).__name__}: {e} [{scrub(url)}]")


def run_instagram_api(cfg: InstagramAPIConfig, client: GraphClient | None = None) -> tuple[list[Record], list[dict], dict]:
    report = {"name": cfg.name, "type": "instagram_api", "mode": cfg.mode, "status": "completed",
              "stop_reason": None, "stop_detail": None, "records": 0, "api_calls": 0}
    errors: list[dict] = []
    if client is None:
        token, uid = _env("IG_ACCESS_TOKEN"), _env("IG_USER_ID")
        missing = [k for k, v in (("IG_ACCESS_TOKEN", token), ("IG_USER_ID", uid)) if not v]
        if missing:
            report.update(status="not_run", stop_reason="missing_credentials",
                          stop_detail=f"set {', '.join(missing)} in the environment or .env")
            return [], errors, report
        client = GraphClient(cfg, token, uid)
    recs: list[Record] = []
    seen: set[str] = set()

    def add(m, account=None):
        r = _to_record(m, cfg.name, account)
        if r.url not in seen and len(recs) < cfg.max_posts:
            seen.add(r.url)
            recs.append(r)

    try:
        if cfg.mode == "own_media":
            body = client.get(f"{client.user_id}/media", fields=cfg.fields, limit=50)
            while True:
                for m in body.get("data", []):
                    add(m)
                nxt = (body.get("paging") or {}).get("next")
                if not nxt or len(recs) >= cfg.max_posts:
                    break
                body = client.get(nxt)
        elif cfg.mode == "business_discovery":
            for user in cfg.usernames:
                after = None
                while len(recs) < cfg.max_posts:
                    media = f"media.after({after}).limit(50)" if after else "media.limit(50)"
                    body = client.get(client.user_id,
                                      fields=f"business_discovery.username({user}){{username,{media}{{{cfg.fields}}}}}")
                    bd = body.get("business_discovery") or {}
                    for m in (bd.get("media") or {}).get("data", []):
                        add(m, bd.get("username") or user)
                    after = (((bd.get("media") or {}).get("paging") or {}).get("cursors") or {}).get("after")
                    if not after or not (bd.get("media") or {}).get("data"):
                        break
        elif cfg.mode == "hashtag":
            for tag in cfg.hashtags:
                found = client.get("ig_hashtag_search", user_id=client.user_id, q=tag.lstrip("#"))
                ids = [d.get("id") for d in found.get("data", []) if d.get("id")]
                if not ids:
                    errors.append({"source": cfg.name, "url": f"hashtag:{tag}", "kind": "hashtag_not_found",
                                   "detail": "ig_hashtag_search returned no id"})
                    continue
                body = client.get(f"{ids[0]}/{cfg.hashtag_edge}", user_id=client.user_id, fields=cfg.fields, limit=50)
                while True:
                    for m in body.get("data", []):
                        add(m)
                    nxt = (body.get("paging") or {}).get("next")
                    if not nxt or len(recs) >= cfg.max_posts:
                        break
                    body = client.get(nxt)
        else:
            raise GraphStop("bad_config", f"unknown mode {cfg.mode!r}")
    except GraphStop as s:
        report.update(status="stopped", stop_reason=s.reason, stop_detail=s.detail)
        errors.append({"source": cfg.name, "url": "", "kind": f"stopped:{s.reason}", "detail": s.detail})
    report["records"], report["api_calls"] = len(recs), client.calls
    return recs, errors, report


# ------------------------------------------------------------------------------------------------
# the owner's own export
# ------------------------------------------------------------------------------------------------
def fix_meta_text(s):
    """Meta exports write UTF-8 bytes as \\u00XX escapes; re-decode when that is what happened."""
    if not isinstance(s, str):
        return s
    try:
        fixed = s.encode("latin-1").decode("utf-8")
        return fixed if fixed != s else s
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def _iso(ts) -> str | None:
    try:
        return datetime.fromtimestamp(int(ts), timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError, OSError):
        return None


def _posts_in(obj, base: Path, source: str) -> list[Record]:
    """Posts in a Meta JSON export: a dict whose "media" list holds objects with an image "uri"."""
    out: list[Record] = []

    def media_list(d):
        m = d.get("media")
        return [x for x in m if isinstance(x, dict) and str(x.get("uri", "")).lower().endswith(IMAGE_EXT)] \
            if isinstance(m, list) else []

    def walk(x):
        if isinstance(x, list):
            for y in x:
                walk(y)
        elif isinstance(x, dict):
            media = media_list(x)
            if media:
                caption = x.get("title") or next((m.get("title") for m in media if m.get("title")), None)
                ts = x.get("creation_timestamp") or media[0].get("creation_timestamp")
                imgs = [str((base / m["uri"]).resolve()) for m in media]
                out.append(Record(source=source, url=f"export:{media[0]['uri']}", text=fix_meta_text(caption),
                                  image_urls=imgs, published_at=_iso(ts), page_type="post",
                                  fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                  field_origin={k: v for k, v in (("text", "export:title" if caption else None),
                                                                  ("image_urls", "export:media.uri"),
                                                                  ("published_at", "export:creation_timestamp" if ts else None)) if v}))
                return
            for v in x.values():
                walk(v)
    walk(obj)
    return out


def run_instagram_export(name: str, path: str | Path) -> tuple[list[Record], list[dict], dict]:
    p = Path(path)
    report = {"name": name, "type": "instagram_export", "status": "completed", "stop_reason": None,
              "files": 0, "records": 0, "unrecognised_files": []}
    errors: list[dict] = []
    if not p.exists():
        report.update(status="not_run", stop_reason="path_not_found", stop_detail=str(p))
        return [], errors, report
    files = [p] if p.is_file() else sorted([*p.rglob("*.json"), *p.rglob("*.csv")])
    root = p if p.is_dir() else p.parent
    recs: list[Record] = []
    for f in files:
        report["files"] += 1
        got: list[Record] = []
        shape = "csv"
        try:
            if f.suffix.lower() == ".csv":
                got = _from_csv(f, name)
            else:
                doc = json.loads(f.read_text(encoding="utf-8"))
                shape = list(doc)[:8] if isinstance(doc, dict) else type(doc).__name__
                bd = doc.get("business_discovery") if isinstance(doc, dict) else None
                if isinstance(doc, dict) and ("data" in doc or bd):
                    media = doc.get("data") or ((bd or {}).get("media") or {}).get("data", [])
                    got = [_to_record(m, name, (bd or {}).get("username")) for m in media]
                else:
                    got = _posts_in(doc, root, name)
        except (ValueError, OSError) as e:
            errors.append({"source": name, "url": str(f), "kind": "unreadable_file", "detail": str(e)})
            continue
        if not got:                     # reported, never guessed at
            report["unrecognised_files"].append({"file": str(f), "top_level": shape})
        recs += got
    seen, uniq = set(), []
    for r in recs:
        if r.url not in seen:
            seen.add(r.url)
            uniq.append(r)
    report["records"] = len(uniq)
    return uniq, errors, report


def _from_csv(f: Path, name: str) -> list[Record]:
    out = []
    with f.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            r = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
            url = r.get("url") or r.get("permalink") or r.get("link")
            if not url:
                continue
            raw = r.get("image_urls") or r.get("image_url") or r.get("media_url") or ""
            imgs = [u.strip() for u in raw.split("|") if u.strip()]
            text = r.get("caption") or r.get("text") or None
            ts = r.get("timestamp") or r.get("published_at") or None
            out.append(Record(source=name, url=url, text=text, image_urls=imgs, published_at=ts,
                              account=r.get("account") or r.get("username") or None, page_type="post",
                              fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                              field_origin={k: "csv" for k, v in (("text", text), ("image_urls", imgs),
                                                                  ("published_at", ts)) if v}))
    return out
