"""Offline IR metrics and small-sample statistics for the ablation study.

Paired permutation / bootstrap follow Smucker, Allan & Carterette (CIKM 2007).
"""

from __future__ import annotations

import numpy as np


def dcg(gains: list[float], k: int) -> float:
    g = np.asarray(gains[:k], dtype=np.float64)
    return float(((2**g - 1) / np.log2(np.arange(2, len(g) + 2))).sum())


def ndcg_at_k(ranked_ids: list[str], grades: dict[str, float], k: int) -> float:
    gains = [grades.get(i, 0.0) for i in ranked_ids[:k]]
    ideal = sorted(grades.values(), reverse=True)
    idcg = dcg(ideal, k)
    return dcg(gains, k) / idcg if idcg > 0 else 0.0


def hit_at_k(ranked_ids: list[str], relevant: set[str], k: int) -> float:
    return float(any(i in relevant for i in ranked_ids[:k]))


def recall_at_k(ranked_ids: list[str], relevant: set[str], k: int) -> float:
    return len(set(ranked_ids[:k]) & relevant) / len(relevant) if relevant else 0.0


def mrr(ranked_ids: list[str], relevant: set[str]) -> float:
    for r, i in enumerate(ranked_ids, start=1):
        if i in relevant:
            return 1.0 / r
    return 0.0


def paired_permutation_test(a: np.ndarray, b: np.ndarray, n_perm: int = 10000, seed: int = 0) -> float:
    """Two-sided p-value for mean(a - b) != 0 with random sign flips."""
    d = np.asarray(a, dtype=np.float64) - np.asarray(b, dtype=np.float64)
    if len(d) == 0 or np.allclose(d, 0):
        return 1.0
    rng = np.random.default_rng(seed)
    obs = abs(d.mean())
    signs = rng.choice([-1.0, 1.0], size=(n_perm, len(d)))
    null = np.abs((signs * d).mean(axis=1))
    return float((np.sum(null >= obs - 1e-12) + 1) / (n_perm + 1))


def bootstrap_ci(x: np.ndarray, n_boot: int = 10000, alpha: float = 0.05, seed: int = 0) -> tuple[float, float]:
    x = np.asarray(x, dtype=np.float64)
    if len(x) == 0:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    means = rng.choice(x, size=(n_boot, len(x)), replace=True).mean(axis=1)
    return float(np.quantile(means, alpha / 2)), float(np.quantile(means, 1 - alpha / 2))


def cohen_kappa(a: list, b: list) -> float:
    labels = sorted(set(a) | set(b))
    n = len(a)
    if n == 0:
        return float("nan")
    po = sum(x == y for x, y in zip(a, b)) / n
    pe = sum((a.count(l) / n) * (b.count(l) / n) for l in labels)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0
