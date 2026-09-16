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
MODES = ("descriptor", "random_words", "antonym")

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
    if mode not in MODES:
        raise ValueError(f"unknown concept mode {mode!r}")
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
