"""T17: does normalising the *query photo* close the domain gap we measured in T16?

T16 found that a garment photographed on a model retrieves its own flat-lay product photo at
R@1 0.601 — and the published consumer-to-shop numbers say the real gap is far worse (FashionNet:
in-shop top-20 76.4% vs consumer-to-shop 18.8%). The literature is unanimous about the cheapest
fix: **crop the query to the garment** (Street2Shop, ICCV 2015: top-20 10.1→42.0 on eyewear,
14.4→27.4 on tops; every deployed visual search detects and crops). Background removal is the
second move, and it is the one that aligns an uploaded photo with what our index actually is:
white-background product shots.

Notably, "remove the background of the **query only**, leave the index untouched" appears to be
unpublished, so this experiment generates evidence rather than reproducing it.

  python scripts/eval_query_norm.py --catalog agents/bench/catalog/dfinshop \
      --encoder marqo-fashionSigLIP --device cuda --n 600 --modes none,centercrop,salient_bbox,salient_white

Modes (all applied to the QUERY only; the index keeps its original flat-lay embeddings):
  none          whole image, exactly what /visual-search does today
  centercrop    centre 70% — a heuristic crop that needs no model, as a floor for "cropping helps"
  salient_bbox  crop to the salient object's bounding box (u2net via rembg, Apache-2.0 weights)
  salient_white composite the salient object onto white, keeping the frame
  salient_both  crop to the box AND composite onto white

Licence note: rembg's *default* model is BRIA RMBG-1.4, which needs a paid commercial agreement.
This script pins `u2net` (Apache-2.0) and sets U2NET_HOME so weights never land in the home
directory. If rembg is unavailable the salient modes are skipped and the rest still run.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

SEED = 20260918
ID_RE = re.compile(r"^(?P<garment>.+_id_\d+_\d+)_(?P<idx>\d+)_(?P<view>[a-z]+)$")
ON_MODEL = ("front", "side", "back")


def _session(model: str):
    """rembg session pinned to an Apache-2.0 model, with weights kept out of the home directory."""
    os.environ.setdefault("U2NET_HOME", str(ROOT / "data" / "cache" / "u2net"))
    Path(os.environ["U2NET_HOME"]).mkdir(parents=True, exist_ok=True)
    from rembg import new_session

    return new_session(model)


def normalise(img, mode: str, session=None):
    """Return the query image after the given query-side normalisation."""
    from PIL import Image

    if mode == "none":
        return img
    if mode == "centercrop":
        w, h = img.size
        dx, dy = int(w * 0.15), int(h * 0.15)
        return img.crop((dx, dy, w - dx, h - dy))

    from rembg import remove

    cut = remove(img, session=session)  # RGBA with the background transparent
    alpha = np.asarray(cut.split()[-1])
    ys, xs = np.nonzero(alpha > 16)
    if len(xs) < 50:  # segmentation found nothing usable → leave the photo alone
        return img
    box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    white = Image.new("RGBA", cut.size, (255, 255, 255, 255))
    on_white = Image.alpha_composite(white, cut).convert("RGB")
    if mode == "salient_bbox":
        return img.crop(box)
    if mode == "salient_white":
        return on_white
    if mode == "salient_both":
        return on_white.crop(box)
    raise ValueError(f"unknown mode {mode!r}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--catalog", default="agents/bench/catalog/dfinshop")
    ap.add_argument("--encoder", default="marqo-fashionSigLIP")
    ap.add_argument("--device", default="auto")
    ap.add_argument("--n", type=int, default=600)
    ap.add_argument("--modes", default="none,centercrop,salient_bbox,salient_white,salient_both")
    ap.add_argument("--rembg-model", default="u2net", help="Apache-2.0; NOT rembg's BRIA default")
    ap.add_argument("--out", default="reports/ablation")
    a = ap.parse_args()

    from PIL import Image

    from engine02.catalog import Catalog
    from engine02.encoders import cached_image_embeddings, l2n

    cat = Catalog.load(ROOT / a.catalog)
    if a.encoder == "hash":
        from engine02.encoders import HashEncoder

        enc = HashEncoder(dim=256, captions={Path(p).name: t for p, t in zip(cat.items["image_path"], cat.texts())})
    else:
        from engine02.models import TorchEncoder

        enc = TorchEncoder(a.encoder, device=a.device)
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", enc.name)
    index_dir = ROOT / a.catalog / "index"
    emb = cached_image_embeddings(enc, cat.image_paths(), index_dir / f"img_{safe}.npy")

    # same pairing as T16: one flat photo per garment is the target, an on-model photo is the query
    rows = []
    for pos, iid in enumerate(cat.items["item_id"].astype(str)):
        m = ID_RE.match(iid)
        if m:
            rows.append((pos, m.group("garment"), m.group("view")))
    by: dict[str, dict[str, list[int]]] = {}
    for pos, g, view in rows:
        d = by.setdefault(g, {"flat": [], "model": []})
        if view == "flat":
            d["flat"].append(pos)
        elif view in ON_MODEL:
            d["model"].append(pos)
    usable = [(g, d["flat"][0], d["model"][0]) for g, d in by.items() if d["flat"] and d["model"]]
    rng = np.random.default_rng(SEED)
    rng.shuffle(usable)
    usable = usable[: a.n]
    print(f"{len(usable)} garments with both views", flush=True)

    flat_emb = l2n(emb[np.array([f for _, f, _ in usable])].astype(np.float64))
    paths = cat.image_paths()
    modes = [m.strip() for m in a.modes.split(",") if m.strip()]
    session = None
    results = []
    for mode in modes:
        if mode.startswith("salient") and session is None:
            try:
                session = _session(a.rembg_model)
            except Exception as exc:  # noqa: BLE001
                print(f"skipping {mode}: rembg unavailable ({type(exc).__name__}: {exc})", flush=True)
                continue
        imgs = []
        for _, _, m_pos in usable:
            with Image.open(paths[m_pos]) as im:
                imgs.append(normalise(im.convert("RGB"), mode, session))
        q = l2n(np.asarray(enc.encode_images_pil(imgs) if hasattr(enc, "encode_images_pil")
                           else _encode_via_tmp(enc, imgs), dtype=np.float64))
        sims = q @ flat_emb.T
        order = np.argsort(-sims, axis=1)
        truth = np.arange(len(usable))
        ranks = np.array([int(np.where(order[i] == truth[i])[0][0]) + 1 for i in range(len(truth))])
        res = dict(mode=mode, n=len(ranks), r_at_1=round(float((ranks == 1).mean()), 4),
                   r_at_10=round(float((ranks <= 10).mean()), 4),
                   mrr=round(float((1.0 / ranks).mean()), 4), median_rank=int(np.median(ranks)))
        results.append((res, ranks))
        print(res, flush=True)

    base = next((r for r, _ in results if r["mode"] == "none"), None)
    base_ranks = next((rk for r, rk in results if r["mode"] == "none"), None)
    summary = []
    for res, ranks in results:
        row = dict(res)
        if base is not None and res["mode"] != "none":
            row["delta_r_at_1"] = round(res["r_at_1"] - base["r_at_1"], 4)
            row["p_vs_none"] = _paired_permutation(1.0 / ranks, 1.0 / base_ranks)
        summary.append(row)

    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    tag = f"query_norm_{Path(a.catalog).name}_{enc.name}"
    (out / f"{tag}.json").write_text(json.dumps(
        {"setup": dict(catalog=a.catalog, encoder=enc.name, garments=len(usable),
                       rembg_model=a.rembg_model), "rows": summary}, indent=1), encoding="utf-8")
    print("\n" + json.dumps(summary, indent=1))
    print(f"\nwrote {out / (tag + '.json')}")
    print("\nThe index is untouched in every row: only the query photo is normalised, which is the\n"
          "situation /visual-search is actually in. Both sides are still retailer photography, so a\n"
          "gain here is a lower bound on what it would buy on a real phone upload.")


def _encode_via_tmp(enc, imgs):
    """Encoders take paths; write the normalised images to a scratch dir and encode those."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        paths = []
        for i, im in enumerate(imgs):
            p = Path(td) / f"{i:06d}.png"
            im.save(p)
            paths.append(p)
        return enc.encode_images(paths)


def _paired_permutation(a, b, n: int = 10000, seed: int = 0) -> float:
    d = np.asarray(a, dtype=float) - np.asarray(b, dtype=float)
    if not np.any(d):
        return 1.0
    obs = abs(d.mean())
    rng = np.random.default_rng(seed)
    flips = rng.choice([-1.0, 1.0], size=(n, len(d)))
    return round(float((np.abs((flips * d).mean(axis=1)) >= obs).mean()), 4)


if __name__ == "__main__":
    main()
