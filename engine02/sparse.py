"""BM25 over catalog text.

Scores are BM25Okapi exactly as `rank_bm25` computes them (same k1, b, epsilon-floored idf), but
evaluated over postings lists instead of the whole corpus. `rank_bm25.BM25Okapi.get_scores` runs
`[(doc.get(q) or 0) for doc in self.doc_freqs]` — a Python loop over **every document for every
query term** — which is the most expensive part of the retrieval stage on a large catalog. A
document with zero occurrences of a term contributes exactly 0 for that term, so iterating the
term's postings gives the identical result. `tests/test_sparse.py` checks that equality against
rank_bm25 itself on random corpora.
"""

from __future__ import annotations

import math
import re

import numpy as np

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = frozenset("a an the and or of for with in on to by is are this that".split())


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall((text or "").lower()) if t not in _STOP]


class BM25Index:
    """Okapi BM25 with postings-list scoring. Defaults match rank_bm25.BM25Okapi."""

    def __init__(self, texts: list[str], k1: float = 1.5, b: float = 0.75, epsilon: float = 0.25):
        self.k1, self.b, self.epsilon = k1, b, epsilon
        tokens = [tokenize(t) or ["_empty_"] for t in texts]
        self.corpus_size = len(tokens)
        self.doc_len = np.array([len(d) for d in tokens], dtype=np.float64)
        self.avgdl = float(self.doc_len.sum() / self.corpus_size) if self.corpus_size else 0.0

        postings: dict[str, list[tuple[int, int]]] = {}
        for i, doc in enumerate(tokens):
            freq: dict[str, int] = {}
            for w in doc:
                freq[w] = freq.get(w, 0) + 1
            for w, f in freq.items():
                postings.setdefault(w, []).append((i, f))

        self.postings: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        idf: dict[str, float] = {}
        idf_sum = 0.0
        negative: list[str] = []
        for w, plist in postings.items():
            idx = np.fromiter((i for i, _ in plist), dtype=np.int64, count=len(plist))
            tf = np.fromiter((f for _, f in plist), dtype=np.float64, count=len(plist))
            self.postings[w] = (idx, tf)
            # identical to rank_bm25._calc_idf, including the epsilon floor for very common terms
            v = math.log(self.corpus_size - len(plist) + 0.5) - math.log(len(plist) + 0.5)
            idf[w] = v
            idf_sum += v
            if v < 0:
                negative.append(w)
        if idf:
            eps = epsilon * (idf_sum / len(idf))
            for w in negative:
                idf[w] = eps
        self.idf = idf
        self.vocab = set(self.postings)
        # k1·(1 − b + b·|d|/avgdl) does not depend on the query
        self._len_norm = (self.k1 * (1 - self.b + self.b * self.doc_len / self.avgdl)
                          if self.avgdl else None)

    def coverage(self, query: str) -> float:
        """Share of query tokens that occur in the catalog. Low coverage means BM25 can
        only add noise (paraphrased or out-of-vocabulary wording)."""
        q = tokenize(query)
        return sum(t in self.vocab for t in q) / len(q) if q else 0.0

    def scores(self, query: str) -> np.ndarray:
        out = np.zeros(self.corpus_size, dtype=np.float64)
        q = tokenize(query)
        if not q or self._len_norm is None:
            return out
        for t in q:  # a repeated query term counts twice, as in rank_bm25
            hit = self.postings.get(t)
            if hit is None:
                continue
            w = self.idf.get(t, 0.0)
            if w == 0.0:
                continue
            idx, tf = hit
            out[idx] += w * (tf * (self.k1 + 1) / (tf + self._len_norm[idx]))
        return out
