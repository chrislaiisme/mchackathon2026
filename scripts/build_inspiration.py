"""Build the inspiration library (runway / street / cosplay photos from Wikimedia Commons).

    python scripts/build_inspiration.py                                   # 60 per group, marqo-fashionSigLIP
    python scripts/build_inspiration.py --per-group 20 --encoder hash --out E:/_verify/inspiration_smoke

Writes, under --out (default data/inspiration, or ENGINE02_INSPIRATION):

    items.parquet            insp_id, group, title, image_path, image_url, page_url, license,
                             license_url, author  (attribution is required for CC BY / BY-SA)
    images/<insp_id>.jpg     384 px wide JPEG thumbnails
    index/img_<encoder>.npy  embeddings from the SAME encoder the service uses (+ meta_<encoder>.json)
    build_report.json        per-group crawl counters, downloads, licences seen, stop reasons

The library is deliberately NOT merged into the product catalog: catalog design scores are z-scored
over the catalog, and photos of people on a catwalk would shift them. See engine02/inspiration.py.

Crawling follows engine02.crawl.commons (official API, serial, maxlag, stop on 403/429/blocked).
Files without a licence are dropped: we cannot show them with the attribution their licence needs.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine02.inspiration import COLUMNS, GROUPS, encoder_key, save_index, screen, write_index  # noqa: E402

THUMB_W = 384


def insp_id(group: str, page_url: str) -> str:
    return f"{group}-{hashlib.sha1(page_url.encode('utf-8')).hexdigest()[:10]}"


def _clip(s, n: int) -> str:
    s = "" if s is None else str(s).strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def records_to_rows(group: str, records, seen: set[str] | None = None) -> tuple[list[dict], Counter]:
    """Commons `Record`s -> library rows (image not downloaded yet). Returns (rows, skip reasons)."""
    seen = set() if seen is None else seen
    rows, skipped = [], Counter()
    for r in records:
        fo = r.field_origin or {}
        lic = (fo.get("license") or "").strip()
        if not lic:
            skipped["no_license"] += 1
            continue
        if not r.image_urls:
            skipped["no_image_url"] += 1
            continue
        if r.url in seen:
            skipped["duplicate"] += 1
            continue
        seen.add(r.url)
        iid = insp_id(group, r.url)
        rows.append({"insp_id": iid, "group": group, "title": _clip(r.title, 160),
                     "image_path": f"images/{iid}.jpg", "image_url": r.image_urls[0], "page_url": r.url,
                     "license": lic, "license_url": (fo.get("license_url") or "").strip(),
                     "author": _clip(fo.get("author") or fo.get("credit") or "unknown", 200)})
    return rows, skipped


def to_jpeg(blob: bytes, dest: Path, width: int = THUMB_W) -> None:
    """Normalise like /visual-search does (EXIF rotation, alpha on white, RGB), then save a JPEG."""
    from PIL import Image, ImageOps

    Image.MAX_IMAGE_PIXELS = 80_000_000
    with Image.open(io.BytesIO(blob)) as im:
        im = ImageOps.exif_transpose(im)
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
            im = Image.alpha_composite(bg, im)
        im = im.convert("RGB")
        if im.width > width:
            im = im.resize((width, max(1, round(im.height * width / im.width))), Image.LANCZOS)
        dest.parent.mkdir(parents=True, exist_ok=True)
        im.save(dest, format="JPEG", quality=88)


def download(rows: list[dict], out: Path, fetcher) -> tuple[list[dict], Counter, dict | None]:
    """Fetch each row's thumbnail; returns (rows with a saved image, failure counts, stop info)."""
    from engine02.crawl.http import Blocked, FetchError

    kept, fails, stop = [], Counter(), None
    for row in rows:
        dest = out / row["image_path"]
        if dest.exists() and dest.stat().st_size > 0:
            kept.append(row)
            continue
        try:
            resp = fetcher.get(row["image_url"])
            to_jpeg(resp.body, dest)
            kept.append(row)
        except Blocked as b:           # the server said stop: respect it for the rest of the run
            stop = {"reason": b.reason, "url": b.url, "detail": b.detail}
            fails[f"stopped:{b.reason}"] += 1
            break
        except FetchError as e:
            fails[f"fetch:{e.status or 'error'}"] += 1
        except Exception as e:         # undecodable image etc.
            fails[f"decode:{type(e).__name__}"] += 1
    return kept, fails, stop


def make_encoder(name: str, device: str = "auto"):
    if name == "hash":
        from engine02.encoders import HashEncoder

        return HashEncoder(dim=256)    # same dim/name ("hash-256") as the service's hash encoder
    from engine02.models import TorchEncoder

    return TorchEncoder(name, device=device)


def apply_screen(out: Path, items: pd.DataFrame, emb, enc, key: str):
    """Drop the photos engine02.inspiration.screen rejects: rows, embeddings and image files."""
    keep, info = screen(emb, enc)
    items = items.reset_index(drop=True)
    dropped = [{"insp_id": r.insp_id, "group": r.group, "title": r.title, **info[i]}
               for i, r in enumerate(items.itertuples()) if not keep[i]]
    for d in dropped:
        f = out / "images" / f"{d['insp_id']}.jpg"
        if f.exists():
            f.unlink()
    items, emb = items[keep].reset_index(drop=True), emb[keep]
    save_index(out, items, emb, enc.name, key)
    rep = {"n_dropped": len(dropped), "by_label": dict(Counter(d["label"] for d in dropped)),
           "by_group": dict(Counter(d["group"] for d in dropped)), "dropped": dropped}
    print(f"[screen] dropped {len(dropped)}: {rep['by_label']}", flush=True)
    return items, emb, rep


def screen_existing(out: Path, key: str, device: str) -> dict:
    import numpy as np

    items = pd.read_parquet(out / "items.parquet")
    emb = np.load(out / "index" / f"img_{encoder_key(key)}.npy")
    enc = make_encoder(key, device)
    items, emb, rep = apply_screen(out, items, emb, enc, key)
    f = out / "build_report.json"
    report = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    report.update(screen=rep, n_items=len(items), by_group=dict(Counter(items["group"])),
                  licenses=dict(Counter(items["license"]).most_common()))
    f.write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=os.environ.get("ENGINE02_INSPIRATION", "data/inspiration"))
    ap.add_argument("--per-group", type=int, default=60)
    ap.add_argument("--groups", default=",".join(GROUPS), help="comma list of " + ",".join(GROUPS))
    ap.add_argument("--encoder", default="marqo-fashionSigLIP", help="marqo-fashionSigLIP | fashion-clip | hash")
    ap.add_argument("--device", default="auto")
    ap.add_argument("--depth", type=int, default=2)
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between requests to one host")
    ap.add_argument("--cache-dir", default=None, help="API response cache (default <out>/.cache)")
    ap.add_argument("--no-screen", action="store_true",
                    help="keep every photo (default: drop posters, crowds, talks, close-ups, swimwear -- "
                         "engine02.inspiration.screen)")
    ap.add_argument("--screen-only", action="store_true",
                    help="no crawl: screen an existing library at --out in place, using its saved index")
    args = ap.parse_args(argv)
    if args.screen_only:
        return screen_existing(Path(args.out) if Path(args.out).is_absolute() else ROOT / args.out,
                               args.encoder, args.device)

    from engine02.crawl.commons import CommonsSource, run
    from engine02.crawl.http import Fetcher

    out = Path(args.out)
    out = out if out.is_absolute() else ROOT / out
    out.mkdir(parents=True, exist_ok=True)
    cache = Path(args.cache_dir) if args.cache_dir else out / ".cache"
    img_fetcher = Fetcher(None, min_delay_s=args.delay)
    report: dict = {"out": str(out), "encoder": args.encoder, "per_group": args.per_group, "groups": {}}
    all_rows: list[dict] = []
    seen: set[str] = set()
    stopped = None
    for group in [g.strip() for g in args.groups.split(",") if g.strip()]:
        if group not in GROUPS:
            raise SystemExit(f"unknown group {group!r}; one of {sorted(GROUPS)}")
        src = CommonsSource(name=f"commons-{group}", categories=GROUPS[group]["categories"],
                            max_files=args.per_group, depth=args.depth, thumb_width=THUMB_W,
                            delay_s=args.delay, cache_dir=cache)
        recs, errors = run(src)
        rows, skipped = records_to_rows(group, recs, seen)
        if stopped is None:
            rows, fails, stopped = download(rows, out, img_fetcher)
        else:
            rows, fails = [], Counter({"skipped_after_stop": len(rows)})
        all_rows.extend(rows)
        report["groups"][group] = {"crawl": src.report, "crawl_errors": len(errors), "records": len(recs),
                                   "skipped": dict(skipped), "download_failures": dict(fails),
                                   "kept": len(rows)}
        print(f"[{group}] records={len(recs)} kept={len(rows)} skipped={dict(skipped)} "
              f"fail={dict(fails)} crawl_status={src.report['status']}", flush=True)
    report["image_stop"] = stopped
    items = pd.DataFrame(all_rows, columns=COLUMNS)
    enc = make_encoder(args.encoder, args.device)
    emb = write_index(out, items, enc, args.encoder)
    if not args.no_screen:
        items, emb, report["screen"] = apply_screen(out, items, emb, enc, args.encoder)
    report.update(n_items=len(items), dim=int(emb.shape[1]) if emb.ndim == 2 else None,
                  encoder_name=enc.name, licenses=dict(Counter(items["license"]).most_common()),
                  by_group=dict(Counter(items["group"])))
    (out / "build_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str),
                                           encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("n_items", "by_group", "licenses", "encoder_name", "dim")},
                     ensure_ascii=False), flush=True)
    return report


if __name__ == "__main__":
    main()
