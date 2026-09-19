"""Precompute the OutfitTransformer item embeddings so /complete-look is demo-fast.

`FastOutfitTransformer.complementary()` needs a CLIP embedding per candidate. Computed on demand
that means loading ~100 images and running the image encoder inside the request: measured p50 554 ms
(p95 704 ms) on cfda4 for one /complete-look. The embeddings depend only on the catalog, so compute
them once and the request is left with a single transformer forward pass.

  python scripts/precompute_ot_cache.py --catalog data/catalog/kagl_polyvore_filled --device cuda

Writes `<catalog>/index/ot_items.npz` (the path `engine02/api.py` loads by default). Resumable:
re-running only fills in the positions that are missing.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--catalog", default="data/catalog/kagl_polyvore_filled")
    ap.add_argument("--device", default="auto")
    ap.add_argument("--heads", default="complementary,compatibility")
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--chunk", type=int, default=1024, help="save after this many items")
    ap.add_argument("--limit", type=int, default=0, help="only the first N items (smoke test)")
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    from engine02.catalog import Catalog
    from engine02.complete_look import FastOutfitTransformer

    cat = Catalog.load(ROOT / a.catalog)
    out = Path(a.out) if a.out else ROOT / a.catalog / "index" / "ot_items.npz"
    have = FastOutfitTransformer.checkpoints()
    heads = tuple(h for h in a.heads.split(",") if h.strip() in have)
    if not heads:
        raise SystemExit(f"no checkpoints for {a.heads!r}; found {sorted(have)}")

    t0 = time.perf_counter()
    ot = FastOutfitTransformer(cat, device=a.device, heads=heads, batch_size=a.batch_size, cache_file=out)
    print(f"loaded heads={heads} shared_item_encoder={ot.shared_item_encoder} "
          f"in {time.perf_counter() - t0:.1f}s; cache={out}", flush=True)

    n = len(cat) if not a.limit else min(a.limit, len(cat))
    done = {h: len(store) for h, store in ot._emb.items()}
    print(f"catalog {n} items; already cached {done}", flush=True)

    t0 = time.perf_counter()
    for start in range(0, n, a.chunk):
        positions = range(start, min(start + a.chunk, n))
        ot.ensure_embeddings(positions)
        ot.save_cache()
        done_n = min(start + a.chunk, n)
        el = time.perf_counter() - t0
        rate = done_n / el if el else 0
        print(f"[{el:7.1f}s] {done_n}/{n} items  {rate:6.1f} items/s  "
              f"eta {(n - done_n) / rate / 60:5.1f} min", flush=True)
    print(f"done in {(time.perf_counter() - t0) / 60:.1f} min -> {out} "
          f"({out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
