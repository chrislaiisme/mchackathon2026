"""Zero-shot design-element scores c(i,d) (PRD M4).

Descriptor-based concept scoring in the spirit of Menon & Vondrick (ICLR 2023) and
post-hoc concept bottlenecks (Yuksekgonul et al., ICLR 2023): average image–descriptor
cosine, optionally minus the image's similarity to a neutral prompt, then z-score each
concept across the catalog so values are comparable between concepts.
"""

from __future__ import annotations

import numpy as np

from .encoders import Encoder
from .fusion import zscore
from .kansei import KanseiTable

NEUTRAL_PROMPT = "a photo of a clothing item"


def design_scores(
    encoder: Encoder,
    image_emb: np.ndarray,
    table: KanseiTable,
    contrast_neutral: bool = True,
) -> np.ndarray:
    """Returns (n_items, n_elements) catalog-z-scored concept scores."""
    cols = []
    neutral = encoder.encode_text([NEUTRAL_PROMPT])[0] if contrast_neutral else None
    for el in table.elements:
        desc = encoder.encode_text(el.descriptors)  # (m, dim), L2-normalised
        sim = (image_emb @ desc.T).mean(axis=1)
        if neutral is not None:
            sim = sim - image_emb @ neutral
        cols.append(zscore(sim))
    return np.stack(cols, axis=1) if cols else np.zeros((len(image_emb), 0))
