"""Zero-shot design-element scores c(i,d) (PRD M4), several variants for ablation.

- "descriptor": mean image–descriptor cosine minus similarity to a neutral prompt
  (Menon & Vondrick, ICLR 2023; post-hoc concept bottlenecks, ICLR 2023). PRD original.
- "random_words": same pipeline with random word strings as descriptors. Control arm
  required by WaffleCLIP (ICCV 2023): if it scores as well, c(i,d) isn't measuring d.
- "antonym": CLIP-IQA style paired prompts (AAAI 2023): softmax over positive vs
  negative descriptor sets, i.e. a bipolar semantic-differential scale as in Kansei.

Options: distribution normalisation (subtract catalog-mean image embedding, Zhou et al.
NeurIPS 2023) and an applicability mask (shoulder structure means nothing on shoes).
Every column is z-scored across the catalog; masked items get 0 (neutral).
"""

from __future__ import annotations

import random

import numpy as np

from .encoders import Encoder, l2n
from .fusion import zscore
from .kansei import KanseiTable

NEUTRAL_PROMPT = "a photo of a clothing item"
MODES = ("descriptor", "random_words", "antonym", "vlm")

_WAFFLE_VOCAB = (
    "table river piano orbit candle velvet tunnel pepper glacier harbor lantern meadow "
    "copper violin saddle marble pencil canyon walnut ribbon falcon kettle prism anchor "
    "cactus ladder mosaic nectar pebble quartz"
).split()


def _random_descriptors(n: int, seed: int) -> list[str]:
    rng = random.Random(seed)
    return [" ".join(rng.sample(_WAFFLE_VOCAB, 3)) for _ in range(max(n, 1))]


def applicability_mask(categories: list[str | None], table: KanseiTable) -> np.ndarray:
    """(n_items, n_elements) bool. Elements without `applies_to` apply everywhere."""
    mask = np.ones((len(categories), len(table.elements)), dtype=bool)
    cats = [str(c).lower() if c else None for c in categories]
    for j, el in enumerate(table.elements):
        if el.applies_to:
            allowed = {a.lower() for a in el.applies_to}
            mask[:, j] = [c in allowed for c in cats]
    return mask


def design_scores(
    encoder: Encoder,
    image_emb: np.ndarray,
    table: KanseiTable,
    mode: str = "descriptor",
    categories: list[str | None] | None = None,
    distribution_normalize: bool = False,
    temperature: float = 0.01,
    seed: int = 0,
) -> np.ndarray:
    """Returns (n_items, n_elements) catalog-z-scored concept scores."""
    if mode not in MODES or mode == "vlm":
        raise ValueError(f"unsupported concept mode {mode!r} here (use vlm_design_scores for 'vlm')")
    img = image_emb.astype(np.float64)
    if distribution_normalize and len(img):
        img = l2n(img - img.mean(axis=0, keepdims=True)).astype(np.float64)
    neutral = encoder.encode_text([NEUTRAL_PROMPT])[0].astype(np.float64)

    cols = []
    for j, el in enumerate(table.elements):
        if mode == "antonym" and el.negative_descriptors:
            pos = encoder.encode_text(el.descriptors).astype(np.float64)
            neg = encoder.encode_text(el.negative_descriptors).astype(np.float64)
            sp = (img @ pos.T).mean(axis=1)
            sn = (img @ neg.T).mean(axis=1)
            # two-way softmax = sigmoid of the scaled difference
            score = 1.0 / (1.0 + np.exp(-(sp - sn) / temperature))
        else:
            desc = el.descriptors if mode != "random_words" else _random_descriptors(len(el.descriptors), seed + j)
            d = encoder.encode_text(desc).astype(np.float64)
            score = (img @ d.T).mean(axis=1) - img @ neutral
        cols.append(zscore(score))
    c = np.stack(cols, axis=1) if cols else np.zeros((len(img), 0))
    if categories is not None:
        c = np.where(applicability_mask(categories, table), c, 0.0)
    return c


def element_profile(encoder: Encoder, catalog_emb: np.ndarray, emb: np.ndarray, table: KanseiTable,
                    mode: str = "antonym", temperature: float = 0.01,
                    prompt_cache: dict | None = None) -> list[dict]:
    """Where one image sits on each design-element axis, **relative to this catalog**.

    Same prompts and same formula as :func:`design_scores`, but for a single embedding (an uploaded
    photo, or a generated concept image). The raw score is meaningless on its own — "0.61 matte" is
    not a unit anyone can read — so it is reported two ways against the catalog's own distribution:
    a z-score and a percentile ("more matte than 87% of the catalog"). That is the same scale the
    cards' design terms use, so a profile and a reason can be read side by side.
    """
    img = np.asarray(emb, dtype=np.float64).reshape(1, -1)
    cat = np.asarray(catalog_emb, dtype=np.float64)
    cache = prompt_cache if prompt_cache is not None else {}
    neutral = cache.get("__neutral__")
    if neutral is None:
        neutral = cache["__neutral__"] = encoder.encode_text([NEUTRAL_PROMPT])[0].astype(np.float64)

    out = []
    for el in table.elements:
        key = (el.id, mode)
        vecs = cache.get(key)
        if vecs is None:
            pos = encoder.encode_text(el.descriptors).astype(np.float64)
            neg = (encoder.encode_text(el.negative_descriptors).astype(np.float64)
                   if el.negative_descriptors else None)
            vecs = cache[key] = (pos, neg)
        pos, neg = vecs

        def raw(x: np.ndarray) -> np.ndarray:
            if mode == "antonym" and neg is not None:
                d = (x @ pos.T).mean(axis=1) - (x @ neg.T).mean(axis=1)
                return 1.0 / (1.0 + np.exp(-d / temperature))
            return (x @ pos.T).mean(axis=1) - x @ neutral

        r_cat = raw(cat)
        r_img = float(raw(img)[0])
        sd = float(r_cat.std()) or 1e-9
        out.append(dict(element=el.id, label=el.label,
                        z=round((r_img - float(r_cat.mean())) / sd, 3),
                        percentile=round(float((r_cat < r_img).mean()), 3)))
    out.sort(key=lambda d: -abs(d["z"]))
    return out


def vlm_design_scores(item_ids: list[str], table: KanseiTable, vlm_file, na_threshold: float = 0.5,
                      return_mask: bool = False):
    """c(i,d) from offline VLM tagging (scripts/vlm_tag_attributes.py): P(pos) − P(neg),
    z-scored across tagged items, zeroed where the VLM says "not applicable" or the item
    was not tagged. Elements the VLM was not asked about stay 0."""
    import pandas as pd

    df = pd.read_parquet(vlm_file).set_index("item_id")
    c = np.zeros((len(item_ids), len(table.elements)))
    tagged = np.zeros_like(c, dtype=bool)  # VLM gave a usable answer (applicable or explicitly n/a)
    idx = [str(i) for i in item_ids]
    present = np.array([i in df.index for i in idx])
    sub = df.reindex(idx)
    for j, el in enumerate(table.elements):
        col = f"c_{el.id}"
        if col not in df.columns:
            continue
        v = sub[col].to_numpy(dtype=np.float64)
        na = sub[f"na_{el.id}"].to_numpy(dtype=np.float64)
        ok = present & ~np.isnan(v) & ~(na > na_threshold)
        tagged[:, j] = present & ~np.isnan(v)
        if ok.sum() > 1:
            c[ok, j] = zscore(v[ok])
    return (c, tagged) if return_mask else c
