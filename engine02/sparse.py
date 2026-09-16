"""BM25 over catalog text (rank_bm25.BM25Okapi)."""

from __future__ import annotations

import re

import numpy as np
from rank_bm25 import BM25Okapi

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = frozenset("a an the and or of for with in on to by is are this that".split())


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall((text or "").lower()) if t not in _STOP]


class BM25Index:
    def __init__(self, texts: list[str]):
        tokens = [tokenize(t) or ["_empty_"] for t in texts]
        self._bm25 = BM25Okapi(tokens)

    def scores(self, query: str) -> np.ndarray:
        q = tokenize(query)
        if not q:
            return np.zeros(self._bm25.corpus_size, dtype=np.float64)
        return np.asarray(self._bm25.get_scores(q), dtype=np.float64)
