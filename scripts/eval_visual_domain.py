"""T16: does a photo of a garment *being worn* behave like the catalog's product photo?

`/visual-search` and the concept-image fusion both assume an uploaded photo lands in the same part
of the embedding space as the white-background catalog images. §3.16 flagged this as the reason its
positive result is an upper bound. DeepFashion-InShop lets us test it properly: the same garment,
photographed by the same retailer, as `_1_front` / `_2_side` / `_3_back` (on a model) and `_6_flat`
(flat lay, i.e. what a product catalog looks like).

  python scripts/eval_visual_domain.py --catalog agents/bench/catalog/dfinshop \
      --encoder marqo-fashionSigLIP --device cuda --n 800

Two measurements, each with its own control:

  retrieval   index only the flat photos, query with the on-model photo of the same garment.
              Control = query with *another flat* photo of the same garment (same domain, same
              difficulty). The gap between them is the domain cost, not the task difficulty.

  profile     `concepts.element_profile` on the on-model photo vs the flat photo of the identical
              garment: per-element |Δz|, correlation, and how often the sign flips (a sign flip is
              the failure that matters — it means the card would claim the opposite attribute).
              Controls = flat vs another flat of the same garment (should agree) and two random
              garments (should not).

Honest framing: this is a *proxy* for "customer photo → catalog". Both sides are retailer
photography, so it under-states the real gap (no phone cameras, no living rooms, no crops).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

SEED = 20260918
# MEN_Denim_id_00000089_01_1_front → garment "MEN_Denim_id_00000089_01", view "front"
ID_RE = re.compile(r"^(?P<garment>.+_id_\d+_\d+)_(?P<idx>\d+)_(?P<view>[a-z]+)$")
ON_MODEL = ("front", "side", "back")


def parse_views(items: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for pos, iid in enumerate(items["item_id"].astype(str)):
        m = ID_RE.match(iid)
        if m:
            rows.append((pos, m.group("garment"), m.group("view")))
    return pd.DataFrame(rows, columns=["pos", "garment", "view"])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--catalog", default="agents/bench/catalog/dfinshop")
    ap.add_argument("--encoder", default="hash")
    ap.add_argument("--device", default="auto")
    ap.add_argument("--arm", default="full_zclip3")
    ap.add_argument("--n", type=int, default=800, help="garments to evaluate")
    ap.add_argument("--out", default="reports/ablation")
    a = ap.parse_args()

    from engine02.catalog import Catalog
    from engine02.concepts import element_profile
    from engine02.config import ARMS
    from engine02.encoders import cached_image_embeddings
    from engine02.kansei import KanseiTable

    cat = Catalog.load(ROOT / a.catalog)
    if a.encoder == "hash":
        from engine02.encoders import HashEncoder

        enc = HashEncoder(dim=256, captions={Path(p).name: t for p, t in zip(cat.items["image_path"], cat.texts())})
    else:
        from engine02.models import TorchEncoder

        enc = TorchEncoder(a.encoder, device=a.device)
    index_dir = ROOT / a.catalog / "index"
    index_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", enc.name)
    emb = cached_image_embeddings(enc, cat.image_paths(), index_dir / f"img_{safe}.npy")

    views = parse_views(cat.items)
    if views.empty:
        raise SystemExit("no item_ids matched the DeepFashion view pattern")
    by_garment = views.groupby("garment")
    usable = []
    for g, grp in by_garment:
        flats = grp[grp["view"] == "flat"]["pos"].tolist()
        models = grp[grp["view"].isin(ON_MODEL)]["pos"].tolist()
        if flats and models:
            usable.append((g, flats, models))
    rng = np.random.default_rng(SEED)
    rng.shuffle(usable)
    usable = usable[: a.n]
    print(f"{len(usable)} garments with both a flat and an on-model photo "
          f"(of {by_garment.ngroups} garments, {len(cat)} images)", flush=True)
    if len(usable) < 20:
        raise SystemExit("too few garments with both views")

    # ---------------- retrieval: only flat photos are in the index ----------------
    flat_pos = np.array([f[0] for _, f, _ in usable])          # one flat per garment = the target
    flat_emb = emb[flat_pos]
    flat_emb = flat_emb / (np.linalg.norm(flat_emb, axis=1, keepdims=True) + 1e-12)

    def evaluate(query_pos: list[int], label: str) -> dict:
        q = emb[np.array(query_pos)]
        q = q / (np.linalg.norm(q, axis=1, keepdims=True) + 1e-12)
        sims = q @ flat_emb.T
        order = np.argsort(-sims, axis=1)
        truth = np.arange(len(usable))
        ranks = np.array([int(np.where(order[i] == truth[i])[0][0]) + 1 for i in range(len(truth))])
        return dict(query=label, n=len(ranks), r_at_1=round(float((ranks == 1).mean()), 4),
                    r_at_10=round(float((ranks <= 10).mean()), 4),
                    mrr=round(float((1.0 / ranks).mean()), 4), median_rank=int(np.median(ranks)))

    def evaluate_subset(query_pos: list[int], target_rows: list[int], label: str) -> dict:
        """Same as evaluate(), but only over a subset of garments (the index stays the full set)."""
        q = emb[np.array(query_pos)]
        q = q / (np.linalg.norm(q, axis=1, keepdims=True) + 1e-12)
        sims = q @ flat_emb.T
        order = np.argsort(-sims, axis=1)
        ranks = np.array([int(np.where(order[i] == target_rows[i])[0][0]) + 1 for i in range(len(target_rows))])
        return dict(query=label, n=len(ranks), r_at_1=round(float((ranks == 1).mean()), 4),
                    r_at_10=round(float((ranks <= 10).mean()), 4),
                    mrr=round(float((1.0 / ranks).mean()), 4), median_rank=int(np.median(ranks)))

    on_model_q = [m[0] for _, _, m in usable]
    retrieval = [evaluate(on_model_q, "on-model → flat (domain shift)")]
    # a second on-model view separates "a different photo" from "a different domain"
    second_view = [(i, m[1]) for i, (_, _, m) in enumerate(usable) if len(m) > 1]
    if second_view:
        retrieval.append(evaluate_subset([q for _, q in second_view], [i for i, _ in second_view],
                                         "another on-model view → flat (same domain shift, different photo)"))
    # the true same-domain control needs a SECOND flat: using the only flat as its own query would
    # score R@1 = 1.0 by construction, which is what the first version of this script did.
    two_flats = [(i, f[1]) for i, (_, f, _) in enumerate(usable) if len(f) > 1]
    if two_flats:
        retrieval.append(evaluate_subset([q for _, q in two_flats], [i for i, _ in two_flats],
                                         "another flat → flat (same domain, control)"))
    else:
        print("no garment has two flat photos: the same-domain control is not available", flush=True)
    for r in retrieval:
        print(r, flush=True)

    # ---------------- element profile: same garment, two presentations ----------------
    table = KanseiTable.load()
    cache: dict = {}
    mode = ARMS[a.arm].concept_mode
    n_prof = min(len(usable), 150)  # each profile is 15 catalog-wide matvecs
    print(f"profiling {n_prof} garments ×2 views (mode={mode})", flush=True)

    def prof(pos: int) -> dict[str, float]:
        return {d["element"]: d["z"] for d in element_profile(enc, emb, emb[pos], table, mode=mode,
                                                              prompt_cache=cache)}

    rows = []
    for i in range(n_prof):
        g, flats, models = usable[i]
        p_model, p_flat = prof(models[0]), prof(flats[0])
        p_flat2 = prof(flats[1]) if len(flats) > 1 else None
        other = usable[(i + 1) % len(usable)]
        p_other = prof(other[1][0])
        for el in p_flat:
            rows.append(dict(garment=g, element=el, z_flat=p_flat[el], z_model=p_model[el],
                             z_flat2=(p_flat2 or {}).get(el, np.nan), z_other=p_other[el]))
    df = pd.DataFrame(rows)

    def agreement(col_a: str, col_b: str, label: str) -> dict:
        sub = df[[col_a, col_b]].dropna()
        if sub.empty:
            return dict(pair=label, n=0)
        a_, b_ = sub[col_a].to_numpy(), sub[col_b].to_numpy()
        both = (np.abs(a_) > 0.25) & (np.abs(b_) > 0.25)  # ignore elements the photo barely expresses
        return dict(pair=label, n=len(sub),
                    mean_abs_delta_z=round(float(np.abs(a_ - b_).mean()), 3),
                    pearson=round(float(np.corrcoef(a_, b_)[0, 1]), 3),
                    sign_flip=round(float((np.sign(a_[both]) != np.sign(b_[both])).mean()), 3)
                    if both.any() else None,
                    n_both_expressed=int(both.sum()))

    pairs = [agreement("z_flat", "z_model", "flat vs on-model (same garment, domain shift)"),
             agreement("z_flat", "z_flat2", "flat vs another flat (same garment, control)"),
             agreement("z_flat", "z_other", "flat vs a different garment (control)")]
    for p_ in pairs:
        print(p_, flush=True)

    per_el = (df.assign(d=lambda x: (x.z_flat - x.z_model).abs())
              .groupby("element")["d"].mean().sort_values(ascending=False).round(3))
    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    tag = f"visual_domain_{Path(a.catalog).name}_{enc.name}"
    df.to_csv(out / f"{tag}.csv", index=False)
    (out / f"{tag}.json").write_text(json.dumps(
        {"setup": dict(catalog=a.catalog, encoder=enc.name, arm=a.arm, garments=len(usable),
                       profiled=n_prof, concept_mode=mode),
         "retrieval": retrieval, "profile_agreement": pairs,
         "per_element_mean_abs_delta_z": per_el.to_dict()}, indent=1), encoding="utf-8")
    print("\nper-element |Δz| between the two presentations (worst first):")
    print(per_el.to_string())
    print(f"\nwrote {out / (tag + '.json')}")
    print("\nRead it as: the retrieval gap between the two query types is the domain cost; a sign\n"
          "flip rate well above the same-domain control means the profile cannot be trusted on an\n"
          "uploaded photo without correction. Both sides here are retailer photography, so this\n"
          "UNDER-states a real customer upload.")


if __name__ == "__main__":
    main()
