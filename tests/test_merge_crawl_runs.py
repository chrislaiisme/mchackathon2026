"""scripts/merge_crawl_runs.py: several run folders -> one de-duplicated dataset."""

import importlib.util
import json
from pathlib import Path

from engine02.crawl.records import Record, export

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("merge_crawl_runs", ROOT / "scripts" / "merge_crawl_runs.py")
merge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(merge)


def _run(d: Path, records: list[Record], sources: list[dict], errors: list[dict]) -> None:
    export(records, d)
    (d / "report.json").write_text(json.dumps({"sources": sources}), encoding="utf-8")
    (d / "errors.jsonl").write_text("".join(json.dumps(e) + "\n" for e in errors), encoding="utf-8")


def test_merge_dedups_by_url_and_fingerprint_newest_wins(tmp_path):
    a, b = tmp_path / "g1" / "run1", tmp_path / "g2" / "run2"
    _run(a, [Record(source="shop", url="https://s/p/1", title="old", fetched_at="2026-09-18"),
             Record(source="shop", url="https://s/p/2", title="same", image_urls=["https://s/i.jpg"])],
         [{"name": "shop", "status": "completed", "records": 2}], [{"kind": "http", "url": "https://s/x"}])
    _run(b, [Record(source="shop", url="https://s/p/1", title="new", fetched_at="2026-09-19"),
             Record(source="shop", url="https://s/p/2?v=1", title="same", image_urls=["https://s/i.jpg"]),
             Record(source="commons_runway", url="https://c/f/1", title="look")],
         [{"name": "commons_runway", "status": "completed", "records": 1}], [])
    out = tmp_path / "out"
    assert merge.main(["--runs", str(tmp_path / "g1"), "--runs", str(b), "--out", str(out)]) == 0

    rows = json.loads((out / "records.json").read_text(encoding="utf-8"))
    by_url = {r["url"]: r for r in rows}
    assert len(rows) == 3                                     # p/2?v=1 is the same content as p/2
    assert by_url["https://s/p/1"]["title"] == "new"          # the newer fetch wins
    assert {s["name"] for s in json.loads((out / "sources.json").read_text(encoding="utf-8"))} == \
        {"shop", "commons_runway"}
    assert (out / "errors.jsonl").read_text(encoding="utf-8").count("\n") == 1
    assert (out / "records.csv").exists()


def test_merge_without_runs_fails(tmp_path):
    assert merge.main(["--runs", str(tmp_path), "--out", str(tmp_path / "o")]) == 1
