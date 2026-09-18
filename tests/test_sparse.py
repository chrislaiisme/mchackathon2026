"""Our postings-list BM25 must equal rank_bm25.BM25Okapi score for score."""

import math

import numpy as np
import pytest
from rank_bm25 import BM25Okapi

from engine02.sparse import BM25Index, tokenize

WORDS = ["navy", "blue", "shirt", "cotton", "slim", "dress", "women", "men", "linen", "casual",
         "formal", "jacket", "wool", "print", "stripe"]


def corpus(n: int, seed: int) -> list[str]:
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        k = int(rng.integers(2, 9))
        out.append(" ".join(rng.choice(WORDS, size=k)))
    return out


@pytest.mark.parametrize("n, seed", [(50, 0), (300, 1), (1000, 2)])
def test_scores_match_rank_bm25(n, seed):
    texts = corpus(n, seed)
    ours = BM25Index(texts)
    theirs = BM25Okapi([tokenize(t) or ["_empty_"] for t in texts])
    for q in ("navy blue shirt", "women formal dress", "wool", "navy navy blue",
              "unseen token here", "", "stripe print casual jacket cotton"):
        got = ours.scores(q)
        want = (np.asarray(theirs.get_scores(tokenize(q)), dtype=np.float64)
                if tokenize(q) else np.zeros(n))
        assert np.allclose(got, want, atol=1e-12, rtol=1e-12), (q, got[:5], want[:5])


def test_epsilon_floor_applies_to_terms_in_most_documents():
    """A term in >half the documents has negative raw idf; rank_bm25 floors it to eps·avg_idf.

    The corpus needs enough rare terms for the average idf (and so the floor) to be positive —
    with a symmetric two-word corpus the average is 0 and the floor lands exactly on 0.
    """
    texts = [f"navy shirt rare{i}" for i in range(8)] + ["blue dress", "olive coat"]
    ours = BM25Index(texts)
    theirs = BM25Okapi([tokenize(t) for t in texts])
    assert ours.idf["navy"] == pytest.approx(theirs.idf["navy"])
    assert ours.idf["navy"] == pytest.approx(ours.epsilon * (sum(
        math.log(len(texts) - len(ours.postings[w][0]) + 0.5) - math.log(len(ours.postings[w][0]) + 0.5)
        for w in ours.postings) / len(ours.postings)))
    assert ours.idf["navy"] > 0  # floored above zero, not left negative
    assert np.allclose(ours.scores("navy"), theirs.get_scores(["navy"]), atol=1e-12)


def test_coverage_unchanged():
    ours = BM25Index(["navy shirt", "blue dress"])
    assert ours.coverage("navy dress") == 1.0
    assert ours.coverage("navy unseen") == 0.5
    assert ours.coverage("") == 0.0
