"""Outfit compatibility term — only defined when the user supplies anchor items.

Every compatibility task in the literature (FITB, complementary retrieval, Complete the
Look, P-Companion) conditions on an anchor; for a single-item request there is nothing
to be compatible with, so the term is disabled (returns None).

Default scorer: normalised PMI of coarse-category co-occurrence in outfits (PRD M6 uses
Polyvore category co-occurrence). Category-first follows Amazon P-Companion (CIKM 2020).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np


class CategoryCooccurrence:
    def __init__(self, counts: dict[str, dict[str, float]]):
        # symmetrise so either upper-triangular or full matrices work
        sym: dict[str, dict[str, float]] = {}
        for a, row in counts.items():
            for b, v in row.items():
                if a == b:
                    sym.setdefault(a, {})[a] = sym.get(a, {}).get(a, 0.0) + float(v)
                    continue
                sym.setdefault(a, {})[b] = sym.get(a, {}).get(b, 0.0) + float(v)
                sym.setdefault(b, {})[a] = sym.get(b, {}).get(a, 0.0) + float(v)
        self.counts = sym
        self.total = sum(sum(v.values()) for v in sym.values()) or 1.0
        self.marg = {a: sum(v.values()) for a, v in sym.items()}

    @classmethod
    def load(cls, path: str | Path) -> "CategoryCooccurrence":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def npmi(self, a: str | None, b: str | None) -> float:
        if not a or not b:
            return 0.0
        joint = self.counts.get(a, {}).get(b, 0.0)
        if joint <= 0:
            return -1.0
        p_ab = joint / self.total
        p_a = self.marg.get(a, 0.0) / self.total
        p_b = self.marg.get(b, 0.0) / self.total
        if p_a <= 0 or p_b <= 0 or p_ab >= 1:
            return 0.0
        return math.log(p_ab / (p_a * p_b)) / -math.log(p_ab)


def compat_scores(
    cand_categories: list[str | None],
    anchor_categories: list[str | None],
    cooc: CategoryCooccurrence | None,
) -> np.ndarray | None:
    if not anchor_categories or cooc is None:
        return None
    out = np.zeros(len(cand_categories))
    for i, c in enumerate(cand_categories):
        vals = [cooc.npmi(c, a) for a in anchor_categories]
        # same category as the anchor is a substitute, not a complement
        vals = [-1.0 if (c is not None and c == a) else v for v, a in zip(vals, anchor_categories)]
        out[i] = float(np.mean(vals))
    return out
