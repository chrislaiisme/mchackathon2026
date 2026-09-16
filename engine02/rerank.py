"""Additive reranker (PRD M6) and three ways to decide which terms are "the reason".

Every term is normalised, multiplied by its weight and summed, so contributions add up
exactly to the score; the decomposition is the explanation (cf. LinkedIn CrystalCandle).

Reason selection (PRD M7 and the fixes suggested by the method inventory):
- necessity (PRD original, CountER-style): zero one term for one item; the term is a
  reason if the item then leaves the top-k. Often yields *no* reason for the #1 item,
  because it wins on several terms at once.
- contrastive margin: compare with the first item below the cut (rank k+1). For an
  additive model the margin splits exactly into per-term differences — no reranking.
- minimal sufficient set (ERASER sufficiency / LENS-style PS): the fewest terms whose
  contributions *alone* (all other terms of this item zeroed) still beat the full score
  of the rank k+1 item. Guarantees ≥1 reason whenever the item has a positive term that
  can carry it.
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
    # normalise with statistics from a wider population (e.g. the whole filtered pool),
    # so a card's explanation does not change when the candidate cut-off changes
    stats: tuple[float, float] | None = None

    def normalized(self) -> np.ndarray:
        if not self.normalize:
            return np.asarray(self.raw, dtype=np.float64)
        if self.stats is not None:
            mu, sd = self.stats
            return (np.asarray(self.raw, dtype=np.float64) - mu) / (sd if sd > 1e-12 else 1.0)
        return zscore(self.raw)


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


@dataclass
class CutoffExplanation:
    cutoff_position: int | None  # candidate position of the rank k+1 item
    margin: float
    diffs: np.ndarray  # per-term contribution difference vs the cut-off item
    sufficient: list[int]  # term indices in the minimal sufficient set


def cutoff_explanations(sc: ScoredCandidates, order: np.ndarray, k: int) -> dict[int, CutoffExplanation]:
    shown = [int(p) for p in order[:k]]
    cut = int(order[k]) if len(order) > k else None
    out: dict[int, CutoffExplanation] = {}
    for p in shown:
        if cut is None:
            diffs = sc.contrib[p].copy()
            margin = float(sc.scores[p])
        else:
            diffs = sc.contrib[p] - sc.contrib[cut]
            margin = float(sc.scores[p] - sc.scores[cut])
        # ERASER-style sufficiency: keep only the terms in S (all others zeroed for this
        # item, every other item unchanged) — does the item still beat the cut-off item?
        threshold = float(sc.scores[cut]) if cut is not None else -np.inf
        suff: list[int] = []
        total = 0.0
        for j in np.argsort(-sc.contrib[p], kind="stable"):
            if sc.contrib[p, j] <= 0:
                break
            suff.append(int(j))
            total += float(sc.contrib[p, j])
            if total > threshold:
                break
        if total <= threshold:
            suff = []  # not achievable (only possible with non-positive scores); cite nothing
        out[p] = CutoffExplanation(cutoff_position=cut, margin=margin, diffs=diffs, sufficient=suff)
    return out
