"""Score normalisation and rank fusion.

- RRF: Cormack, Clarke & Buettcher, SIGIR 2009.
- Convex combination of normalised scores: Bruch et al., TOIS 2023
  ("An Analysis of Fusion Functions for Hybrid Retrieval").
"""

from __future__ import annotations

import numpy as np


def zscore(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    if x.size == 0:
        return x
    sd = x.std()
    if sd < 1e-12:
        return np.zeros_like(x)
    return (x - x.mean()) / sd


def minmax(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    if x.size == 0:
        return x
    lo, hi = x.min(), x.max()
    if hi - lo < 1e-12:
        return np.zeros_like(x)
    return (x - lo) / (hi - lo)


def ranks_desc(scores: np.ndarray) -> np.ndarray:
    """1-based rank of each position when sorted by descending score (stable)."""
    order = np.argsort(-np.asarray(scores), kind="stable")
    r = np.empty(len(order), dtype=np.int64)
    r[order] = np.arange(1, len(order) + 1)
    return r


def rrf(score_lists: list[np.ndarray], k: int = 60, depth: int | None = None) -> np.ndarray:
    """Reciprocal rank fusion over aligned score arrays (same item order).

    Items beyond `depth` in a list contribute nothing from that list, mirroring
    the usual "fuse the top-N of each retriever" setup.
    """
    fused = np.zeros(len(score_lists[0]), dtype=np.float64)
    for s in score_lists:
        r = ranks_desc(s)
        contrib = 1.0 / (k + r)
        if depth is not None:
            contrib = np.where(r <= depth, contrib, 0.0)
        fused += contrib
    return fused


def convex(dense: np.ndarray, sparse: np.ndarray, alpha: float = 0.5, norm: str = "minmax") -> np.ndarray:
    f = minmax if norm == "minmax" else zscore
    return alpha * f(dense) + (1.0 - alpha) * f(sparse)


def mmr(
    relevance: np.ndarray,
    embeddings: np.ndarray,
    k: int,
    lam: float = 0.7,
) -> list[int]:
    """Maximal Marginal Relevance (Carbonell & Goldstein, SIGIR 1998).

    relevance: (n,) scores; embeddings: (n, d) L2-normalised. Returns positions.
    """
    n = len(relevance)
    if n == 0:
        return []
    rel = minmax(relevance)
    sims = embeddings @ embeddings.T
    selected: list[int] = [int(np.argmax(rel))]
    remaining = set(range(n)) - set(selected)
    while remaining and len(selected) < k:
        cand = np.array(sorted(remaining))
        max_sim = sims[np.ix_(cand, selected)].max(axis=1)
        val = lam * rel[cand] - (1 - lam) * max_sim
        best = int(cand[int(np.argmax(val))])
        selected.append(best)
        remaining.remove(best)
    return selected
