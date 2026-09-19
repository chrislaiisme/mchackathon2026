"""External-benchmark adapters and their *canonical* metrics.

Everything here reimplements a metric exactly as the originating paper / competition / benchmark
repository computes it, so ENGINE 02 numbers can be put next to published numbers. Nothing in this
module touches the shipped pipeline; it only reads `Engine02`/`Catalog` objects.

Benchmarks covered
------------------
1. **Marqo fashion benchmark** (`marqo-ai/marqo-FashionCLIP`, the eval suite behind
   Marqo-FashionCLIP / Marqo-FashionSigLIP, https://www.marqo.ai/blog/search-model-for-fashion).
   Task ``text-to-image``: the benchmark ships, per dataset, a file
   ``data/<Dataset>/gt_query_doc/ground_truth_text-image.json`` = 2,000 sampled query strings →
   {item_ID: 1}. Their `eval.py` retrieves **top-10 only** (``Ks=[1,10]``, ``k=max(Ks)``) and scores it
   with BEIR's `EvaluateRetrieval` (pytrec_eval) plus their own MRR. So the published
   "Recall@1 / Recall@10 / MRR" are, precisely:

   - ``Recall@k = |top-k ∩ rel| / |rel|``  (trec_eval semantics: the denominator is *all* relevant
     docs, so a query with 20 relevant items can score at most 1/20 at k=1),
   - ``MRR`` = reciprocal rank of the first relevant doc **within the top-10**, 0 otherwise (= MRR@10),
   - ``AvgRecall`` = mean(Recall@1, Recall@10).

   `marqo_t2i_metrics` reproduces those three per query, which is what lets us bootstrap them.
   Attribute tasks (``category-to-product`` …) are scored with P@1 / P@10 / MRR instead.

2. **Polyvore outfit compatibility** (Han et al., "Learning Fashion Compatibility with Bidirectional
   LSTMs", ACM MM 2017, arXiv:1707.05691; Vasileva et al., "Learning Type-Aware Embeddings for
   Fashion Compatibility", ECCV 2018, arXiv:1803.09196). Two canonical tasks:

   - **FITB**: one item is removed from an outfit and must be picked out of 4 candidates
     (1 true + 3 negatives) → accuracy, chance 25 %.
   - **Compatibility AUC**: score whole outfits, positives = real outfits, negatives = outfits whose
     items were randomly substituted → area under the ROC curve.

   Han 2017 draws FITB/compatibility negatives uniformly from the dataset; Vasileva 2018 draws them
   from the *same category* (much harder). Both regimes are implemented (``neg_mode``).

3. **Amazon ESCI / Shopping Queries Dataset** (Reddy et al., arXiv:2206.06588; KDD Cup 2022).
   Task 1 (query-product ranking) is scored with nDCG over the four human labels using the
   competition gain map ``E=1.0, S=0.1, C=0.01, I=0.0`` and **linear** gains (the official baseline
   uses `sklearn.metrics.ndcg_score`, i.e. gain g, discount 1/log2(rank+1)) — *not* the 2^g-1 form
   used elsewhere in `engine02/eval/metrics.py`. `ndcg_linear` implements the competition form.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

# --------------------------------------------------------------------------------------
# 1. Marqo fashion benchmark
# --------------------------------------------------------------------------------------
MARQO_TOPK = 10  # marqo-FashionCLIP/eval.py: Ks=[1,10] → run_retrieval(..., k=max(Ks))


def load_marqo_ground_truth(path: str | Path) -> dict[str, dict[str, int]]:
    """`ground_truth_<query_col>-<doc_col>.json` → {query: {item_ID: gain}}."""
    with open(path, encoding="utf-8") as f:
        return {str(q): {str(d): int(g) for d, g in rel.items()} for q, rel in json.load(f).items()}


def rank_ids(scores: np.ndarray, ids: Sequence[str], k: int = MARQO_TOPK) -> list[str]:
    """Top-k item ids by score, ties broken by id (deterministic, like trec_eval)."""
    scores = np.asarray(scores, dtype=np.float64)
    n = len(scores)
    k = min(k, n)
    if k == 0:
        return []
    if k < n:
        cut = np.argpartition(-scores, k - 1)[:k]
        # argpartition picks arbitrarily among values tied at the cut-off, so widen the candidate
        # set with every item on that boundary before the deterministic sort
        boundary = np.flatnonzero(scores == scores[cut].min())
        cut = np.unique(np.concatenate([cut, boundary]))
    else:
        cut = np.arange(n)
    cut = sorted(cut, key=lambda i: (-scores[i], str(ids[i])))[:k]
    return [str(ids[i]) for i in cut]


def marqo_t2i_metrics(ranked: Sequence[str], relevant: Iterable[str], ks=(1, 10)) -> dict[str, float]:
    """Per-query Recall@k (trec_eval denominator = |rel|) and MRR over the truncated run."""
    rel = {str(r) for r in relevant}
    out: dict[str, float] = {}
    n_rel = len(rel)
    for k in ks:
        hit = len(rel & {str(d) for d in ranked[:k]})
        out[f"recall@{k}"] = hit / n_rel if n_rel else 0.0
    out["mrr"] = 0.0
    for r, d in enumerate(ranked, start=1):
        if str(d) in rel:
            out["mrr"] = 1.0 / r
            break
    out["avg_recall"] = float(np.mean([out[f"recall@{k}"] for k in ks]))
    return out


def marqo_attr_metrics(ranked: Sequence[str], relevant: Iterable[str], ks=(1, 10)) -> dict[str, float]:
    """Attribute tasks (`*-to-product`) are reported as Precision@k + MRR in the Marqo leaderboard."""
    rel = {str(r) for r in relevant}
    out = {f"p@{k}": (len(rel & {str(d) for d in ranked[:k]}) / k if k else 0.0) for k in ks}
    out["mrr"] = 0.0
    for r, d in enumerate(ranked, start=1):
        if str(d) in rel:
            out["mrr"] = 1.0 / r
            break
    out["avg_p"] = float(np.mean([out[f"p@{k}"] for k in ks]))
    return out


# --------------------------------------------------------------------------------------
# 2. Polyvore: FITB + compatibility AUC
# --------------------------------------------------------------------------------------
APPAREL = ("top", "bottom", "outerwear", "dress", "shoes", "bag")


def outfit_index(items, apparel_only: bool = True) -> dict[str, list[int]]:
    keep = set(APPAREL) if apparel_only else None
    out: dict[str, list[int]] = {}
    cats = items["category"].tolist()
    for pos, ids in enumerate(items["outfit_ids"]):
        if keep is not None and cats[pos] not in keep:
            continue
        for o in (ids if ids is not None else []):
            out.setdefault(str(o), []).append(pos)
    return out


@dataclass
class FitbQuestion:
    outfit_id: str
    anchors: list[int]  # remaining outfit items (positions)
    candidates: list[int]  # n_cands positions, shuffled
    gold: int  # index into candidates


def fitb_questions(items, n: int, seed: int = 0, n_cands: int = 4, neg_mode: str = "same_category",
                   min_outfit: int = 3) -> list[FitbQuestion]:
    """Canonical fill-in-the-blank: hide one item, give `n_cands` candidates.

    neg_mode="same_category" (Vasileva et al. 2018) | "random" (Han et al. 2017).
    Negatives never come from the same outfit.
    """
    rng = random.Random(seed)
    cats = items["category"].tolist()
    outfits = outfit_index(items)
    by_cat: dict[str, list[int]] = {}
    for pos, c in enumerate(cats):
        by_cat.setdefault(c, []).append(pos)
    all_pos = [p for p in range(len(cats)) if cats[p] in APPAREL]
    qs: list[FitbQuestion] = []
    for oid, members in outfits.items():
        if len(members) < min_outfit:
            continue
        hidden = rng.choice(members)
        pool = by_cat[cats[hidden]] if neg_mode == "same_category" else all_pos
        pool = [p for p in pool if p not in members]
        if len(pool) < n_cands - 1:
            continue
        cands = [hidden] + rng.sample(pool, n_cands - 1)
        rng.shuffle(cands)
        qs.append(FitbQuestion(oid, [p for p in members if p != hidden], cands, cands.index(hidden)))
    rng.shuffle(qs)
    return qs[:n] if n else qs


def fitb_hit(scores: np.ndarray, gold: int) -> float:
    """Accuracy with ties splitting credit (a model that ties all candidates gets 1/n_cands)."""
    s = np.asarray(scores, dtype=np.float64)
    best = np.flatnonzero(s >= s.max() - 1e-12)
    return 1.0 / len(best) if gold in best else 0.0


@dataclass
class CompatPair:
    outfit_id: str
    positive: list[int]
    negative: list[int]


def compat_pairs(items, n: int, seed: int = 0, neg_mode: str = "same_category",
                 min_outfit: int = 3, max_outfit: int = 8) -> list[CompatPair]:
    """Outfit-compatibility pairs: the real outfit vs. one with *every* item substituted.

    Han et al. 2017 build negatives by random substitution; Vasileva et al. 2018 substitute within
    the same category. AUC is computed over the union of positives (label 1) and negatives (label 0),
    so a paired construction keeps the size distribution identical between classes.
    """
    rng = random.Random(seed)
    cats = items["category"].tolist()
    by_cat: dict[str, list[int]] = {}
    for pos, c in enumerate(cats):
        by_cat.setdefault(c, []).append(pos)
    all_pos = [p for p in range(len(cats)) if cats[p] in APPAREL]
    pairs: list[CompatPair] = []
    for oid, members in outfit_index(items).items():
        if not (min_outfit <= len(members) <= max_outfit):
            continue
        neg = []
        for p in members:
            pool = by_cat[cats[p]] if neg_mode == "same_category" else all_pos
            pool = [q for q in pool if q not in members]
            if not pool:
                neg = []
                break
            neg.append(rng.choice(pool))
        if len(neg) == len(members):
            pairs.append(CompatPair(oid, list(members), neg))
    rng.shuffle(pairs)
    return pairs[:n] if n else pairs


def auroc(scores: Sequence[float], labels: Sequence[int]) -> float:
    """Rank-based AUC (Mann–Whitney U), ties get 0.5 credit."""
    s = np.asarray(scores, dtype=np.float64)
    y = np.asarray(labels, dtype=np.int64)
    pos, neg = s[y == 1], s[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    order = np.argsort(s, kind="mergesort")
    ranks = np.empty(len(s), dtype=np.float64)
    r = np.arange(1, len(s) + 1, dtype=np.float64)
    ranks[order] = r
    # average ranks within tie groups
    sv = s[order]
    i = 0
    while i < len(sv):
        j = i
        while j + 1 < len(sv) and sv[j + 1] == sv[i]:
            j += 1
        if j > i:
            ranks[order[i : j + 1]] = (i + j + 2) / 2.0
        i = j + 1
    return float((ranks[y == 1].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def bootstrap_auc_ci(scores: np.ndarray, labels: np.ndarray, n_boot: int = 2000,
                     seed: int = 0) -> tuple[float, float]:
    """95 % CI of a single AUC by resampling the evaluated units."""
    rng = np.random.default_rng(seed)
    n = len(labels)
    vals = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        v = auroc(scores[idx], labels[idx])
        if not np.isnan(v):
            vals.append(v)
    if not vals:
        return (float("nan"), float("nan"))
    return tuple(float(x) for x in np.quantile(vals, [0.025, 0.975]))  # type: ignore[return-value]


def paired_auc_delta_test(sa: np.ndarray, sb: np.ndarray, labels: np.ndarray,
                          n_boot: int = 2000, seed: int = 0) -> dict[str, float]:
    """Paired bootstrap for AUC(a) − AUC(b) scored on the *same* units.

    Two-sided p = 2·min(P(Δ*≤0), P(Δ*≥0)) over the bootstrap distribution of the difference — the
    standard paired-bootstrap test for two correlated AUCs (cf. Smucker et al., CIKM 2007, for the
    same logic applied to IR metrics).
    """
    rng = np.random.default_rng(seed)
    n = len(labels)
    obs = auroc(sa, labels) - auroc(sb, labels)
    deltas = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        d = auroc(sa[idx], labels[idx]) - auroc(sb[idx], labels[idx])
        if not np.isnan(d):
            deltas.append(d)
    if not deltas:
        return {"delta": float(obs), "p": 1.0, "ci_lo": float("nan"), "ci_hi": float("nan")}
    d = np.asarray(deltas)
    lo, hi = np.quantile(d, [0.025, 0.975])
    p = 2 * min((d <= 0).mean(), (d >= 0).mean())
    return {"delta": float(obs), "p": float(min(1.0, max(p, 1.0 / (len(d) + 1)))),
            "ci_lo": float(lo), "ci_hi": float(hi)}


def mean_pairwise_similarity(emb: np.ndarray, positions: Sequence[int]) -> float:
    """Outfit score baseline: mean cosine over all item pairs (embeddings are L2-normalised)."""
    p = list(positions)
    if len(p) < 2:
        return 0.0
    m = emb[p] @ emb[p].T
    iu = np.triu_indices(len(p), k=1)
    return float(m[iu].mean())


def mean_pairwise_npmi(cooc, categories: Sequence[str]) -> float:
    c = [x for x in categories if x]
    if len(c) < 2:
        return 0.0
    return float(np.mean([cooc.npmi(c[i], c[j]) for i in range(len(c)) for j in range(i + 1, len(c))]))


# --------------------------------------------------------------------------------------
# 3. Amazon ESCI
# --------------------------------------------------------------------------------------
# KDD Cup 2022 / Reddy et al. 2022, Task 1 gain map.
ESCI_GAINS = {"E": 1.0, "S": 0.1, "C": 0.01, "I": 0.0}


def ndcg_linear(ranked_ids: Sequence[str], grades: dict[str, float], k: int) -> float:
    """nDCG with **linear** gains and 1/log2(rank+1) discount (sklearn.metrics.ndcg_score form).

    This is the form the ESCI baseline / KDD Cup 2022 Task 1 use, hence the separate function:
    `engine02.eval.metrics.ndcg_at_k` uses the exponential (2^g − 1) gain and would give
    different numbers for the fractional ESCI gains.
    """
    g = np.asarray([grades.get(str(i), 0.0) for i in ranked_ids[:k]], dtype=np.float64)
    disc = 1.0 / np.log2(np.arange(2, len(g) + 2))
    ideal = np.asarray(sorted(grades.values(), reverse=True)[:k], dtype=np.float64)
    idisc = 1.0 / np.log2(np.arange(2, len(ideal) + 2))
    idcg = float((ideal * idisc).sum())
    return float((g * disc).sum() / idcg) if idcg > 0 else 0.0


APPAREL_QUERY_TOKENS = (
    # conservative apparel/footwear vocabulary used to carve an apparel slice out of ESCI;
    # matched against the query string (whole word), documented as a heuristic, not a label.
    "shirt", "tshirt", "t-shirt", "tee", "blouse", "top", "tank", "sweater", "sweatshirt", "hoodie",
    "cardigan", "jacket", "coat", "blazer", "vest", "parka", "windbreaker", "dress", "gown", "skirt",
    "pants", "trousers", "jeans", "shorts", "leggings", "jumpsuit", "romper", "suit", "tuxedo",
    "socks", "tights", "underwear", "bra", "panties", "boxers", "briefs", "pajamas", "pyjamas",
    "robe", "swimsuit", "bikini", "swim", "trunks", "shoes", "sneakers", "boots", "sandals", "heels",
    "loafers", "flats", "slippers", "hat", "cap", "beanie", "scarf", "gloves", "belt", "tie",
    "uniform", "overalls", "kurta", "saree", "abaya", "hijab", "polo", "jersey", "apparel",
    "clothing", "clothes", "outfit", "wear",
)


def is_apparel_query(query: str, tokens: Sequence[str] = APPAREL_QUERY_TOKENS) -> bool:
    q = " " + "".join(ch if ch.isalnum() or ch == "-" else " " for ch in str(query).lower()) + " "
    return any(f" {t} " in q for t in tokens)
