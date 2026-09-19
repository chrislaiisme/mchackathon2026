"""Every outfit-idea Pin the team's Pinterest account can reach, plus the related vocabulary.

What a standard v5 token can and cannot read, probed against the live API on 2026-09-19:

  reachable   /user_account, /boards, /boards/{id}/pins, /pins        -- the account's OWN Pins
              /terms/related, /terms/suggested                       -- keyword vocabulary
              /trends/keywords/{region}/top/{type}                   -- see fetch_pinterest_trends.py
  401         /search/partner/pins   "does not have access to this restricted feature: pin_search"
  401         /search/pins, /search/boards   "token does not have sufficient permissions"

So **public Pinterest cannot be searched with this token**: the millions of outfit ideas on the
site are behind `pin_search`, a partner-only feature. What this script collects is everything the
API does allow -- the Pins the team saved to its own boards, which is exactly the curated
reference set the product is meant to learn from -- and the related-term vocabulary for a list of
outfit seeds. Scraping the website instead would break Pinterest's terms and is not done here.

    python scripts/fetch_pinterest_boards.py                    # metadata only
    python scripts/fetch_pinterest_boards.py --download-images  # also the 600px images, local only

The token comes from PINTEREST_ACCESS_TOKEN (env or .env, which is gitignored) and is never
written into any output. Metadata goes to data/pinterest/pins_<date>.json; images, if asked for,
to data/pinterest/images/ -- those stay local (third-party images, internal use only).

Every image URL in the metadata is a public i.pinimg.com CDN link, so a teammate WITHOUT the
token can rebuild the images from the committed metadata with --images-from.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.pinterest.com/v5"

# Outfit vocabulary seeds for /terms/related. Deliberately the catalog's own axes (occasion,
# season, category) plus the brief's example requests, so the related terms map back to things
# the ranking already understands.
SEEDS = [
    "outfit ideas", "work outfit", "interview outfit", "date night outfit", "wedding guest outfit",
    "casual outfit", "smart casual", "business casual", "formal outfit", "streetwear",
    "minimalist outfit", "capsule wardrobe", "fall outfit", "winter outfit", "spring outfit",
    "summer outfit", "layering outfit", "athleisure", "old money outfit", "office outfit women",
    "office outfit men", "blazer outfit", "trench coat outfit", "knit sweater outfit",
]


def token() -> str:
    tok = os.environ.get("PINTEREST_ACCESS_TOKEN", "").strip()
    env = ROOT / ".env"
    if not tok and env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("PINTEREST_ACCESS_TOKEN="):
                tok = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
    if not tok:
        raise SystemExit("PINTEREST_ACCESS_TOKEN is not set (env or .env). Nothing was requested.")
    return tok


class Client:
    def __init__(self, tok: str, pause: float):
        self.tok, self.pause, self.calls = tok, pause, 0

    def get(self, path: str, **q) -> dict | list:
        url = API + path + ("?" + urllib.parse.urlencode(q, doseq=True) if q else "")
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.tok}",
                                                   "Accept": "application/json"})
        for attempt in range(3):
            time.sleep(self.pause)
            self.calls += 1
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    return json.loads(r.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < 2:      # rate limited: back off, then retry
                    time.sleep(10 * (attempt + 1))
                    continue
                raise

    def pages(self, path: str, **q):
        """Follow Pinterest's bookmark cursor to the end."""
        bookmark = None
        while True:
            params = dict(q, page_size=100)
            if bookmark:
                params["bookmark"] = bookmark
            body = self.get(path, **params)
            yield from body.get("items", [])
            bookmark = body.get("bookmark")
            if not bookmark:
                return


def slim(pin: dict, board_name: str | None) -> dict:
    """Keep what the product can use; drop account analytics and promotion flags."""
    images = ((pin.get("media") or {}).get("images") or {})
    return {
        "pin_id": pin.get("id"),
        "board_id": pin.get("board_id"),
        "board": board_name,
        "title": pin.get("title") or None,
        "description": (pin.get("description") or "").strip() or None,
        "alt_text": pin.get("alt_text") or None,
        "dominant_color": pin.get("dominant_color"),
        "link": pin.get("link") or None,
        "created_at": pin.get("created_at"),
        "is_product": pin.get("is_product"),
        "creative_type": pin.get("creative_type"),
        "media_type": (pin.get("media") or {}).get("media_type"),
        "images": {size: v.get("url") for size, v in images.items() if isinstance(v, dict)},
    }


def download_images(doc: dict, out_dir: Path, size: str = "600x") -> tuple[int, int]:
    """Fetch images from the public CDN URLs in the metadata. Needs no token."""
    out_dir.mkdir(parents=True, exist_ok=True)
    ok = failed = 0
    for p in doc["pins"]:
        url = (p.get("images") or {}).get(size)
        if not url:
            continue
        dst = out_dir / f"{p['pin_id']}.jpg"
        if dst.exists():
            ok += 1
            continue
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                dst.write_bytes(r.read())
            ok += 1
        except (urllib.error.URLError, OSError):
            failed += 1
        time.sleep(0.3)
    return ok, failed


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="data/pinterest")
    ap.add_argument("--pause", type=float, default=1.0, help="seconds between API calls")
    ap.add_argument("--download-images", action="store_true", help="also save 600px images locally")
    ap.add_argument("--images-from", metavar="PINS_JSON",
                    help="no API calls: rebuild images from an existing pins_*.json (no token needed)")
    a = ap.parse_args()
    out = ROOT / a.out

    if a.images_from:
        doc = json.loads(Path(a.images_from).read_text(encoding="utf-8"))
        ok, failed = download_images(doc, out / "images")
        print(f"images: {ok} saved, {failed} failed -> {out / 'images'}")
        return

    c = Client(token(), a.pause)
    acct = c.get("/user_account")
    boards = list(c.pages("/boards"))
    print(f"account type {acct.get('account_type')}, {len(boards)} boards")

    pins: dict[str, dict] = {}
    per_board = {}
    for b in boards:
        n = 0
        for p in c.pages(f"/boards/{b['id']}/pins"):
            pins.setdefault(p["id"], slim(p, b.get("name")))
            n += 1
        per_board[b.get("name")] = n
        print(f"  board {b.get('name')!r}: {n} pins")
    # Pins the account owns but that are not on any board (e.g. unsorted saves)
    loose = 0
    for p in c.pages("/pins"):
        if p["id"] not in pins:
            pins[p["id"]] = slim(p, None)
            loose += 1
    print(f"  not on a listed board: {loose}")

    # /terms/related is an ads-targeting endpoint and is sparse: "work outfit" returns zero related
    # terms. An empty list is recorded as empty -- never back-filled with the seed itself.
    related: dict[str, list | dict] = {}
    for seed in SEEDS:
        try:
            body = c.get("/terms/related", terms=seed)
            terms = []
            for group in body.get("related_terms_list") or []:
                for t in group.get("related_terms") or []:
                    terms.append(t.get("term") if isinstance(t, dict) else t)
            related[seed] = [t for t in terms if t and t != seed][:50]
        except urllib.error.HTTPError as e:
            related[seed] = {"error": e.code}
    print(f"related terms for {len(related)} seeds")

    now = datetime.now(timezone.utc)
    doc = {
        "source": "pinterest_api_v5",
        "fetched_at": now.isoformat(timespec="seconds"),
        "account_type": acct.get("account_type"),
        "scope": "the account's OWN boards and Pins; public search (pin_search) is partner-only "
                 "and returned 401, so this is not a sample of Pinterest at large",
        "license": "Pinterest API terms; images belong to their creators -- internal use only, "
                   "do not redistribute the images",
        "boards": [{"board_id": b.get("id"), "name": b.get("name"),
                    "description": b.get("description") or None,
                    "pin_count": b.get("pin_count"), "fetched": per_board.get(b.get("name"))}
                   for b in boards],
        "n_pins": len(pins),
        "pins": list(pins.values()),
        "related_terms": related,
        "api_calls": c.calls,
    }
    out.mkdir(parents=True, exist_ok=True)
    dst = out / f"pins_{now.strftime('%Y%m%d')}.json"
    dst.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{len(pins)} pins, {c.calls} API calls -> {dst}")

    if a.download_images:
        ok, failed = download_images(doc, out / "images")
        print(f"images: {ok} saved, {failed} failed -> {out / 'images'} (local only)")


if __name__ == "__main__":
    main()
