"""Kansei table K[n,d] (PRD M3) and design-element weights β_d.

β_d = Σ_n p(n)·K[n,d] + step_size · clip(Δsteps_d)
Need n's share of an item's design contribution = p(n)·K[n,d]·c(i,d)  (PRD formula ③)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

RESOURCES = Path(__file__).parent / "resources"


@dataclass
class DesignElement:
    id: str
    label: str
    descriptors: list[str]  # visual English descriptions for the image-text encoder


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

    @classmethod
    def load(cls, path: str | Path | None = None) -> "KanseiTable":
        path = Path(path) if path else RESOURCES / "kansei_v0.json"
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        elements = [DesignElement(**e) for e in raw["design_elements"]]
        el_index = {e.id: j for j, e in enumerate(elements)}
        need_ids = list(raw["needs"].keys())
        K = np.zeros((len(need_ids), len(elements)))
        for i, n in enumerate(need_ids):
            for d, w in raw["K"].get(n, {}).items():
                K[i, el_index[d]] = float(w)
        return cls(
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
        steps = np.array(
            [np.clip(adjust_steps.get(d, 0), -self.max_steps, self.max_steps) for d in self.element_ids],
            dtype=np.float64,
        )
        return from_needs, steps * self.step_size

    def need_shares(self, probs: dict[str, float], j: int, c_value: float) -> dict[str, float]:
        """p(n)·K[n,d_j]·c for every need with non-zero share."""
        out = {}
        for i, n in enumerate(self.need_ids):
            v = probs.get(n, 0.0) * self.K[i, j] * c_value
            if abs(v) > 1e-9:
                out[n] = float(v)
        return out
