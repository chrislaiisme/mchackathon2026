"""Additive reranker (PRD M6) and counterfactual necessity check (PRD M7).

Every term is z-scored within the candidate set, multiplied by its weight, and summed,
so the per-term contributions add up exactly to the final score. That decomposition is
the explanation (cf. LinkedIn CrystalCandle attribution→template; concept bottlenecks).

Necessity follows CountER (CIKM 2021) in its simplest form: zero one term for one item,
keep other items unchanged, and see whether the item leaves the top-k.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .fusion import zscore


@dataclass
class Term:
    name: str
    group: str
    raw: np.ndarray  # (n_candidates,)
    weight: float
    need_shares_per_unit: dict[str, float] = field(default_factory=dict)  # for design terms
    normalize: bool = True

    def normalized(self) -> np.ndarray:
        return zscore(self.raw) if self.normalize else np.asarray(self.raw, dtype=np.float64)


@dataclass
class ScoredCandidates:
    scores: np.ndarray  # (n,)
    terms: list[Term]
    contrib: np.ndarray  # (n, n_terms)
    norm: np.ndarray  # (n, n_terms)

    def order(self) -> np.ndarray:
        return np.argsort(-self.scores, kind="stable")


def additive_score(terms: list[Term]) -> ScoredCandidates:
    terms = [t for t in terms if abs(t.weight) > 1e-12]
    n = len(terms[0].raw) if terms else 0
    norm = np.stack([t.normalized() for t in terms], axis=1) if terms else np.zeros((n, 0))
    w = np.array([t.weight for t in terms])
    contrib = norm * w
    return ScoredCandidates(scores=contrib.sum(axis=1), terms=terms, contrib=contrib, norm=norm)


def counterfactual_ranks(sc: ScoredCandidates, positions: list[int]) -> dict[int, list[int]]:
    """For each candidate position, rank (1-based) after removing each term's contribution."""
    out: dict[int, list[int]] = {}
    for p in positions:
        ranks = []
        for j in range(len(sc.terms)):
            s = sc.scores.copy()
            s[p] -= sc.contrib[p, j]
            ranks.append(int((s > s[p]).sum()) + 1)
        out[p] = ranks
    return out
