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


def test_match_stats_separate_a_real_query_from_a_paraphrase():
    """The gate signal must be a count: the collapse comes from rare words, not silent ones."""
    from engine02.sparse import BM25Index

    texts = [f"men navy blue formal shirt cotton {i}" for i in range(200)]
    texts += [f"women red casual dress {i}" for i in range(200)]
    texts.append("nike everyday running shoe")          # "everyday" occurs exactly once
    idx = BM25Index(texts)

    lexical = idx.match_stats("men navy blue formal shirt")
    para = idx.match_stats("guy's midnight everyday tee")
    assert lexical["share_docs_touched"] > 0.4
    assert para["share_docs_touched"] < 0.05, para
    # and the old signal does NOT separate them: "everyday" is in the vocabulary
    assert idx.coverage("guy's midnight everyday tee") > 0.0
    assert para["median_df"] <= 2, "the matched terms are the rare ones"


def test_docs_touched_gate_turns_the_lexical_side_off_only_when_it_is_noise(tmp_path):
    import numpy as np
    import pandas as pd

    from engine02.catalog import Catalog
    from engine02.contracts import Engine02Options, Engine02Request
    from engine02.encoders import HashEncoder
    from engine02.pipeline import Engine02

    rows = [dict(item_id=str(i), title=f"men navy blue formal shirt {i}", description=None,
                 category="top", subcategory="shirt", color="navy", season=None, occasion=None,
                 gender="Men", price=None, image_path=f"images/{i}.jpg") for i in range(120)]
    rows.append(dict(item_id="x", title="nike everyday running shoe", description=None,
                     category="shoes", subcategory="shoes", color="white", season=None,
                     occasion=None, gender="Men", price=None, image_path="images/x.jpg"))
    cat = Catalog(items=pd.DataFrame(rows), root=tmp_path, name="toy")
    eng = Engine02(cat, HashEncoder(dim=64, captions={f"{r['item_id']}.jpg": r["title"] for r in rows}),
                   cache_dir=tmp_path / "index")

    def run(text, arm):
        req = Engine02Request(session_id="s", retrieval_text=text,
                              options=Engine02Options(top_k=5, explain_with_llm=False))
        return eng.run(req, arm)

    lex = run("men navy blue formal shirt", "full_zclip3")
    assert not any("對不上" in w for w in lex.constraint_report.input_warnings), "must not fire here"
    assert any(c.group == "bm25" for it in lex.items for c in it.contributions)

    para = run("guy's everyday tee", "full_zclip3")
    assert any("對不上" in w for w in para.constraint_report.input_warnings), para.constraint_report
    assert not any(c.group == "bm25" and c.contribution != 0 for it in para.items
                   for c in it.contributions), "the lexical term must be switched off, not shrunk"
