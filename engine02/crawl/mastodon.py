"""Mastodon public hashtag timelines -- a social-network source that needs no key.

Endpoint (checked on docs.joinmastodon.org/methods/timelines, 2026-09-19):

    GET https://{instance}/api/v1/timelines/tag/{hashtag}?limit=40&only_media=true&max_id=...

  * `limit`       default 20, max 40;
  * `only_media`  return only statuses with media attachments;
  * `max_id`      "all results returned will be lesser than this ID" -- older pages are fetched by
                  passing the id of the last status of the previous page;
  * authentication is only required when the instance has disabled public preview (then 401/422,
    which is treated as a stop / an error, never worked around).

The documented rate limit is 300 requests per 5 minutes per IP (one per second); `delay_s`
(default 1.0) is installed as the per-host minimum gap on the Fetcher, and robots.txt is checked
for the API path first (its Crawl-delay, if any, also applies).

Safety: statuses marked `sensitive` or carrying a content warning (`spoiler_text`) are skipped and
counted, never collected. Brand and price stay None -- a toot does not state them in structured form.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from urllib.parse import quote, urlencode

from .commons import strip_html
from .http import Blocked, FetchError, Fetcher
from .records import Record
from .robots import Robots

PAGE_LIMIT = 40              # the API's maximum `limit`
MAX_EMPTY_PAGES = 5          # pages in a row that yield nothing usable before giving up on a tag


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def tag_url(instance: str, hashtag: str, only_media: bool = True, max_id: str | None = None,
            limit: int = PAGE_LIMIT) -> str:
    inst = instance.strip().rstrip("/")
    if not inst.startswith(("http://", "https://")):
        inst = "https://" + inst
    q = {"limit": str(limit)}
    if only_media:
        q["only_media"] = "true"
    if max_id:
        q["max_id"] = str(max_id)
    return f"{inst}/api/v1/timelines/tag/{quote(hashtag.lstrip('#').strip(), safe='')}?{urlencode(q)}"


def status_to_record(name: str, status: dict, query: str = "", fetched_at: str | None = None) -> Record | None:
    """Map one Mastodon Status to a Record; None when it has no URL at all."""
    url = status.get("url") or status.get("uri")
    if not url:
        return None
    images = []
    for m in status.get("media_attachments") or []:
        if (m or {}).get("type") == "image":
            u = m.get("url") or m.get("preview_url")
            if u and u not in images:
                images.append(u)
    origin = {"url": "mastodon:url" if status.get("url") else "mastodon:uri",
              "text": "mastodon:content", "image_urls": "mastodon:media_attachments",
              "published_at": "mastodon:created_at", "account": "mastodon:account.acct"}
    if query:
        origin["query"] = query
    return Record(source=name, url=url, title=None, text=strip_html(status.get("content")),
                  brand=None, price=None, currency=None, image_urls=images,
                  published_at=status.get("created_at"), account=(status.get("account") or {}).get("acct"),
                  page_type="post", fetched_at=fetched_at or _now(), field_origin=origin)


def run_mastodon(name: str, instances: list[str] | None, hashtags: list[str], max_posts: int = 200,
                 only_media: bool = True, delay_s: float = 1.0, fetcher: Fetcher | None = None,
                 robots: Robots | None = None) -> tuple[list[Record], list[dict], dict]:
    instances = list(instances or ["mastodon.social"])
    hashtags = [h.lstrip("#").strip() for h in (hashtags or []) if h and h.lstrip("#").strip()]
    fetcher = fetcher or Fetcher(None, min_delay_s=delay_s)
    robots = robots or Robots()
    records: list[Record] = []
    errors: list[dict] = []
    seen: set[str] = set()
    report = {"name": name, "type": "mastodon", "status": "completed", "stop_reason": None,
              "stop_detail": None, "stop_url": None, "instances": instances, "hashtags": hashtags,
              "api_calls": 0, "statuses_seen": 0, "skipped_sensitive": 0, "skipped_spoiler": 0,
              "duplicates": 0, "with_images": 0, "records": 0, "errors": 0, "per_query": {}}

    def log(url, kind, detail, status=None):
        errors.append({"time": _now(), "source": name, "url": url, "kind": kind, "detail": detail,
                       "status": status})
        report["errors"] = len(errors)

    if not hashtags:
        report.update(status="not_run", stop_reason="no_hashtags")
        return records, errors, report

    pairs = [(i, h) for i in instances for h in hashtags]
    blocked_instances: set[str] = set()
    try:
        for idx, (inst, tag) in enumerate(pairs):
            remaining = max_posts - len(records)
            if remaining <= 0:
                break
            # spread what is left over the queries not yet run, so one busy tag cannot eat the budget
            quota = math.ceil(remaining / (len(pairs) - idx))
            first = tag_url(inst, tag, only_media)
            qkey = f"{inst}#{tag}"
            got = 0
            report["per_query"][qkey] = 0
            if inst in blocked_instances:
                continue
            verdict = robots.check(first)
            if not verdict.allowed:
                blocked_instances.add(inst)
                log(first, f"robots:{verdict.reason}", "robots.txt does not allow the API path")
                report["per_query"][qkey] = f"robots_{verdict.reason}"
                continue
            fetcher.set_host_delay(first, max(delay_s, verdict.crawl_delay or 0.0))
            max_id, empty_pages = None, 0
            while got < quota:
                url = tag_url(inst, tag, only_media, max_id)
                report["api_calls"] += 1
                try:
                    resp = fetcher.get(url)          # Blocked on 401/403/407/451 and persistent 429
                    page = json.loads(resp.body.decode("utf-8"))
                except FetchError as e:
                    log(e.url, "fetch_error", e.detail, e.status)
                    break
                except (UnicodeDecodeError, json.JSONDecodeError) as e:
                    log(url, "fetch_error", f"not JSON: {e}")
                    break
                if not isinstance(page, list):
                    log(url, "fetch_error", f"expected a list of statuses, got {type(page).__name__}: "
                                            f"{str(page)[:200]}")
                    break
                if not page:
                    break
                before = got
                fetched_at = _now()
                for outer in page:
                    report["statuses_seen"] += 1
                    st = outer.get("reblog") or outer        # a boost: the post is the reblogged one
                    if outer.get("sensitive") or st.get("sensitive"):
                        report["skipped_sensitive"] += 1
                        continue
                    if (outer.get("spoiler_text") or "").strip() or (st.get("spoiler_text") or "").strip():
                        report["skipped_spoiler"] += 1
                        continue
                    rec = status_to_record(name, st, qkey, fetched_at)
                    if rec is None:
                        continue
                    if rec.url in seen:
                        report["duplicates"] += 1
                        continue
                    seen.add(rec.url)
                    records.append(rec)
                    report["with_images"] += bool(rec.image_urls)
                    got += 1
                    if got >= quota:
                        break
                report["per_query"][qkey] = got
                empty_pages = empty_pages + 1 if got == before else 0
                if empty_pages >= MAX_EMPTY_PAGES:
                    break
                new_max = page[-1].get("id")
                if not new_max or new_max == max_id:
                    break
                max_id = new_max
    except Blocked as b:
        report.update(status="stopped", stop_reason=b.reason, stop_url=b.url, stop_detail=b.detail)
        log(b.url, f"stopped:{b.reason}", b.detail, b.status)
    if blocked_instances and not records and report["status"] == "completed":
        report.update(status="stopped", stop_reason="robots_disallow",
                      stop_detail=f"robots.txt disallows {sorted(blocked_instances)}")
    report["records"] = len(records)
    return records, errors, report
