"""Kansei table K[n,d] (PRD M3) and design-element weights β_d.

β_d = Σ_n p(n)·K[n,d] + step_size · clip(Δsteps_d)
Need n's share of an item's design contribution = p(n)·K[n,d]·c(i,d)  (PRD formula ③)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

RESOURCES = Path(__file__).parent / "resources"
DEFAULT_TABLE = "kansei_v1_literature.json"


@dataclass
class DesignElement:
    id: str
    label: str
    descriptors: list[str]  # visual English descriptions for the image-text encoder
    negative_descriptors: list[str] = field(default_factory=list)  # antonym pole
    applies_to: list[str] = field(default_factory=list)  # coarse categories; empty = all


@dataclass
class KanseiTable:
    version: str
    needs: dict[str, str]  # need_id -> label
    elements: list[DesignElement]
    K: np.ndarray  # (n_needs, n_elements)
    need_ids: list[str]
    step_size: float = 0.25
    max_steps: int = 3

    @property
    def element_ids(self) -> list[str]:
        return [e.id for e in self.elements]

    folded: dict[str, str] = field(default_factory=dict)  # antonym element → canonical element

    @classmethod
    def load(cls, path: str | Path | None = None, fold_antonyms: bool = True) -> "KanseiTable":
        """fold_antonyms: two elements whose descriptor sets are each other's negatives
        (formal ↔ casual) are one bipolar axis — with antonym scoring c(i,b) = −c(i,a)
        exactly — so K[n,b] is folded into K[n,a] with the opposite sign (averaged when both
        poles carry a value) and clipped to [−1, 1]. Otherwise one literature finding entered on both poles is counted twice."""
        path = Path(path) if path else RESOURCES / DEFAULT_TABLE
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        elements = [DesignElement(**e) for e in raw["design_elements"]]
        el_index = {e.id: j for j, e in enumerate(elements)}
        need_ids = list(raw["needs"].keys())
        K = np.zeros((len(need_ids), len(elements)))
        for i, n in enumerate(need_ids):
            for d, w in raw["K"].get(n, {}).items():
                K[i, el_index[d]] = float(w)
        folded: dict[str, str] = {}
        if fold_antonyms:
            for a, ea in enumerate(elements):
                if ea.id in folded:
                    continue
                for b in range(a + 1, len(elements)):
                    eb = elements[b]
                    if eb.id not in folded and ea.negative_descriptors and                             sorted(eb.descriptors) == sorted(ea.negative_descriptors) and                             sorted(eb.negative_descriptors) == sorted(ea.descriptors):
                        both = (K[:, a] != 0) & (K[:, b] != 0)
                        # same finding entered on both poles → average, not sum
                        K[:, a] = np.where(both, (K[:, a] - K[:, b]) / 2.0, K[:, a] - K[:, b])
                        K[:, b] = 0.0
                        folded[eb.id] = ea.id
        return cls(
            folded=folded,
            version=raw["version"],
            needs=raw["needs"],
            elements=elements,
            K=np.clip(K, -1, 1),
            need_ids=need_ids,
            step_size=raw.get("step_size", 0.25),
            max_steps=raw.get("max_steps", 3),
        )

    def need_vector(self, probs: dict[str, float]) -> np.ndarray:
        return np.array([probs.get(n, 0.0) for n in self.need_ids])

    def beta(self, probs: dict[str, float], adjust_steps: dict[str, int]) -> tuple[np.ndarray, np.ndarray]:
        """Returns (β from needs, β from feedback adjustments), both shape (n_elements,)."""
        p = self.need_vector(probs)
        from_needs = p @ self.K
        raw = {d: 0 for d in self.element_ids}
        for d, v in adjust_steps.items():
            if d in self.folded:  # "more casual" on a folded pole = "less formal" on the canonical axis
                raw[self.folded[d]] = raw.get(self.folded[d], 0) - v
            elif d in raw:
                raw[d] += v
        steps = np.array([np.clip(raw[d], -self.max_steps, self.max_steps) for d in self.element_ids],
                         dtype=np.float64)
        return from_needs, steps * self.step_size

    def need_shares(self, probs: dict[str, float], j: int, c_value: float) -> dict[str, float]:
        """p(n)·K[n,d_j]·c for every need with non-zero share."""
        out = {}
        for i, n in enumerate(self.need_ids):
            v = probs.get(n, 0.0) * self.K[i, j] * c_value
            if abs(v) > 1e-9:
                out[n] = float(v)
        return out
