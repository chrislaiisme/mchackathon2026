"""Command line for engine02.crawl.

    # everything in a config file (see scripts/crawl_sources.example.toml)
    python -m engine02.crawl --config scripts/crawl_sources.example.toml
    python -m engine02.crawl --config my_sources.toml --source vogue_tw --source uniqlo_tw

    # one-off: some URLs, stay on their host
    python -m engine02.crawl --url https://shop.example/collections/new --max-pages 20

    # Instagram from your own export, no network
    python -m engine02.crawl --instagram-export path/to/instagram-export/

Every run writes data/crawl/<run id>/: records.json, records.csv, errors.jsonl and report.json.
report.json says, per source, whether it completed or was stopped, and why (robots_*,
access_denied, login_required, captcha, rate_limited, missing_credentials, ...).
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path

from .http import Fetcher
from .instagram import InstagramAPIConfig, run_instagram_api, run_instagram_export
from .records import export
from .robots import Robots
from .web import WebSourceConfig, run_web

ROOT = Path(__file__).resolve().parents[2]
WEB_KEYS = set(WebSourceConfig.__dataclass_fields__) - {"name"}
IG_KEYS = set(InstagramAPIConfig.__dataclass_fields__) - {"name"}


def load_sources(path: Path) -> tuple[dict, list[dict]]:
    doc = tomllib.loads(path.read_text(encoding="utf-8"))
    return doc.get("defaults", {}), doc.get("sources", [])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m engine02.crawl", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", type=Path)
    ap.add_argument("--source", action="append", default=[], help="only run these source names")
    ap.add_argument("--url", action="append", default=[], help="ad-hoc start URL (repeatable)")
    ap.add_argument("--allow-domain", action="append", default=[])
    ap.add_argument("--follow", action="append", default=[], help="regex of links to follow")
    ap.add_argument("--instagram-export", type=Path)
    ap.add_argument("--max-pages", type=int)
    ap.add_argument("--delay", type=float, help="seconds between requests to one host (min)")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "crawl")
    ap.add_argument("--cache-dir", type=Path, default=ROOT / "data" / "crawl" / ".cache")
    ap.add_argument("--cache-ttl-hours", type=float, default=24.0)
    ap.add_argument("--no-cache", action="store_true")
    a = ap.parse_args(argv)

    defaults, sources = ({}, [])
    if a.config:
        defaults, sources = load_sources(a.config)
    if a.url:
        sources.append({"name": "adhoc", "type": "web", "start_urls": a.url,
                        "allowed_domains": a.allow_domain, "follow": a.follow})
    if a.instagram_export:
        sources.append({"name": "instagram_export", "type": "instagram_export", "path": str(a.instagram_export)})
    if a.source:
        sources = [s for s in sources if s.get("name") in set(a.source)]
    if not sources:
        ap.error("nothing to do: give --config, --url or --instagram-export")

    delay = a.delay if a.delay is not None else float(defaults.get("delay_s", 2.0))
    fetcher = Fetcher(None if a.no_cache else a.cache_dir,
                      cache_ttl_s=float(defaults.get("cache_ttl_hours", a.cache_ttl_hours)) * 3600,
                      min_delay_s=delay)
    robots = Robots()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = a.out / run_id
    all_records, all_errors, reports = [], [], []

    for s in sources:
        kind = s.get("type", "web")
        name = s.get("name", kind)
        if kind == "web":
            # a misspelt key (e.g. "include" for "follow") used to vanish silently and change what
            # got crawled; say so loudly and put it in the report instead
            unknown = sorted(set(s) - WEB_KEYS - {"name", "type"})
            if unknown:
                print(f"WARNING [{name}] unknown config keys ignored: {unknown} "
                      f"(valid: {sorted(WEB_KEYS)})", file=sys.stderr, flush=True)
            cfg = WebSourceConfig(name=name, **{k: v for k, v in {**defaults, **s}.items() if k in WEB_KEYS})
            if a.max_pages:
                cfg.max_pages = a.max_pages
            fetcher.min_delay_s = max(delay, float(s.get("delay_s", delay)))
            recs, errs, rep = run_web(cfg, fetcher, robots)
            if unknown:
                rep["ignored_config_keys"] = unknown
        elif kind == "instagram_api":
            cfg = InstagramAPIConfig(name=name, **{k: v for k, v in s.items() if k in IG_KEYS})
            recs, errs, rep = run_instagram_api(cfg)
        elif kind == "instagram_export":
            recs, errs, rep = run_instagram_export(name, s["path"])
        elif kind == "commons":
            from .commons import CommonsSource, run as run_commons
            keys = {"categories", "max_files", "depth", "thumb_width", "exclude_categories", "delay_s", "page_size"}
            src = CommonsSource(name=name, cache_dir=None if a.no_cache else a.cache_dir,
                                **{k: v for k, v in s.items() if k in keys})
            recs, errs = run_commons(src)
            rep = src.report
        else:
            recs, errs, rep = [], [], {"name": name, "type": kind, "status": "not_run",
                                       "stop_reason": "unknown_source_type"}
        all_records += recs
        all_errors += errs
        reports.append(rep)
        print(f"[{rep['status']:>9}] {name:<28} records={rep.get('records', 0):<5} "
              f"{('stop=' + str(rep.get('stop_reason'))) if rep.get('stop_reason') else ''}", flush=True)

    # the same URL from two sources is one record
    seen, uniq = set(), []
    for r in all_records:
        if r.url not in seen:
            seen.add(r.url)
            uniq.append(r)
    paths = export(uniq, out)
    with (out / "errors.jsonl").open("w", encoding="utf-8") as fh:
        for e in all_errors:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    summary = {"run_id": run_id, "records": len(uniq), "cross_source_duplicates": len(all_records) - len(uniq),
               "network_requests": fetcher.network_requests, "cache_hits": fetcher.cache_hits,
               "sources": reports, "files": {**paths, "errors": str(out / "errors.jsonl")}}
    (out / "report.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{len(uniq)} records -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
