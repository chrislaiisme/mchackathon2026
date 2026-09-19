"""Merge several crawl runs (data/crawl/<run id>/ folders) into one dataset folder.

    python scripts/merge_crawl_runs.py --runs E:/crawl/g1 --runs E:/crawl/g2 --out data/crawl_dataset

Each --runs path may be a run folder (has records.json) or a parent of run folders. Records are
de-duplicated by URL (the newest fetch wins), then by content fingerprint. Writes records.json,
records.csv (engine02.crawl.records.export), sources.json (every source's report: status,
stop reason, pages, records) and errors.jsonl (all runs' errors concatenated).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import fields
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine02.crawl.records import Record, export  # noqa: E402

RECORD_FIELDS = {f.name for f in fields(Record)}


def run_dirs(paths: list[Path]) -> list[Path]:
    out: list[Path] = []
    for p in paths:
        if (p / "records.json").exists():
            out.append(p)
        else:
            out.extend(sorted(d.parent for d in p.glob("*/records.json")))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", action="append", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "crawl_dataset")
    a = ap.parse_args(argv)

    dirs = run_dirs(a.runs)
    if not dirs:
        print("no run folders with records.json found", file=sys.stderr)
        return 1
    by_url: dict[str, Record] = {}
    sources: dict[str, dict] = {}
    errors: list[str] = []
    for d in dirs:
        for row in json.loads((d / "records.json").read_text(encoding="utf-8")):
            r = Record(**{k: v for k, v in row.items() if k in RECORD_FIELDS})
            old = by_url.get(r.url)
            if old is None or (r.fetched_at or "") > (old.fetched_at or ""):
                by_url[r.url] = r
        rep = d / "report.json"
        if rep.exists():
            for s in json.loads(rep.read_text(encoding="utf-8")).get("sources", []):
                s = {**s, "run": d.name}
                prev = sources.get(s.get("name") or s.get("source") or d.name)
                if prev is None or s.get("records", 0) >= prev.get("records", 0):
                    sources[s.get("name") or s.get("source") or d.name] = s
        err = d / "errors.jsonl"
        if err.exists():
            errors.extend(line for line in err.read_text(encoding="utf-8").splitlines() if line.strip())

    seen: set[str] = set()
    records: list[Record] = []
    for r in sorted(by_url.values(), key=lambda r: (r.source, r.url)):
        fp = r.fingerprint()
        if fp in seen:
            continue
        seen.add(fp)
        records.append(r)

    export(records, a.out)
    (a.out / "sources.json").write_text(json.dumps(sorted(sources.values(), key=lambda s: str(s.get("name"))),
                                                   ensure_ascii=False, indent=1), encoding="utf-8")
    (a.out / "errors.jsonl").write_text("\n".join(errors) + ("\n" if errors else ""), encoding="utf-8")
    per_source: dict[str, int] = {}
    for r in records:
        per_source[r.source] = per_source.get(r.source, 0) + 1
    print(json.dumps({"runs": len(dirs), "records": len(records), "sources": len(per_source),
                      "per_source": dict(sorted(per_source.items()))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
