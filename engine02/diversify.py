"""Slate diversification that keeps the explanation faithful.

A relevance ranking often shows five near-identical shirts. This module re-orders **only the
candidates the additive reranker already scored** and returns, for every card, whether it is
there on relevance alone or was *promoted by diversification* (so the card can say
「為了多樣性而納入」 instead of pretending its relevance terms put it there).

Methods (all greedy, O(k·n) or O(k²·n) on the top-`depth` candidates):

- MMR — Carbonell & Goldstein, SIGIR 1998. Reuses ``fusion.mmr``:
  argmax λ·rel(i) − (1−λ)·max_{j∈S} cos(i, j).
- DPP fast greedy MAP — Chen, Zhang & Zhou, NeurIPS 2018, "Fast Greedy MAP Inference for
  Determinantal Point Process to Improve Recommendation Diversity" (arXiv 1709.05135), Alg. 1
  with the relevance/diversity trade-off of their Eq. (13):
  argmax θ·r_i + (1−θ)·log d_i², where d_i² is the incremental-Cholesky residual of the
  similarity kernel S_ij = (1 + cos_ij)/2 (their §6 mapping that keeps S PSD and in [0,1]).
  Deployed at YouTube: Wilhelm et al., CIKM 2018 (doi 10.1145/3269206.3272018).
- xQuAD — Santos, Macdonald & Ounis, WWW 2010 (doi 10.1145/1772690.1772780), with the
  user's top hidden needs as the "aspects":
  argmax (1−λ)·rel(i) + λ·Σ_n P(n)·P(i|n)·Π_{j∈S}(1 − P(j|n)),
  P(n) ∝ p(n) over the top needs, P(i|n) = max(0, share_n(i)) / max_i share_n(i) where
  share_n(i) = Σ_d γ·p(n)·K[n,d]·c(i,d) is the need's part of the item's design contribution
  (``RankedItem.need_contributions``).

Faithfulness rules implemented in ``diversify_response``:
- the slate is a subset of the relevance candidates; scores and contributions are unchanged
  (still sum exactly to ``score``);
- ``relevance_rank`` is the rank under pure relevance; ``promoted_by_diversity`` = relevance_rank > k;
- for non-promoted cards, the cited terms are the minimal sufficient set against the score of the
  relevance rank-(k+1) item (same guarantee as the pipeline); for promoted cards no relevance-only
  sufficient set exists, so their strongest positive terms are shown as strengths
  (``sufficient=False``) and the first reason states the diversity rationale with numbers;
- ``diversification.displaced`` lists relevance top-k items that were dropped, with the selected
  item they are most similar to (cosine), so "dropped because it duplicates X" is checkable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .contracts import Engine02Request, Engine02Response, RankedItem
from .explain import explain, template_reasons
from .fusion import minmax, mmr
from .rerank import ScoredCandidates, cutoff_explanations

METHODS = ("none", "mmr", "dpp", "xquad")


# ---------------------------------------------------------------------------
# selection algorithms (pure numpy)
# ---------------------------------------------------------------------------
def select_relevance(rel: np.ndarray, k: int) -> list[int]:
    return [int(i) for i in np.argsort(-np.asarray(rel, dtype=np.float64), kind="stable")[:k]]


def select_mmr(rel: np.ndarray, emb: np.ndarray, k: int, lam: float) -> list[int]:
    """MMR; λ=1 → pure relevance order."""
    if lam >= 1.0:
        return select_relevance(rel, k)
    return mmr(np.asarray(rel, dtype=np.float64), np.asarray(emb, dtype=np.float64), k, lam)


def select_dpp(rel: np.ndarray, emb: np.ndarray, k: int, theta: float, eps: float = 1e-10) -> list[int]:
    """Chen et al. 2018, Algorithm 1 on S with the θ-trade-off gain θ·r_i + (1−θ)·log d_i².

    rel is min-max normalised to [0,1]; S_ij = (1 + <f_i,f_j>)/2. θ=1 → pure relevance.
    Stops early (returns fewer items) only if every residual d_i² < eps (exact duplicates);
    the remaining slots are then filled by relevance so the slate always has k items.
    """
    n = len(rel)
    if n == 0:
        return []
    if theta >= 1.0:
        return select_relevance(rel, k)
    r = minmax(rel)
    f = np.asarray(emb, dtype=np.float64)
    S = (1.0 + f @ f.T) / 2.0
    k = min(k, n)
    cis = np.zeros((k, n))
    d2 = np.diag(S).copy()
    gain = lambda: theta * r + (1.0 - theta) * np.log(np.clip(d2, eps, None))  # noqa: E731
    selected: list[int] = []
    avail = np.ones(n, dtype=bool)
    j = int(np.argmax(np.where(avail, gain(), -np.inf)))
    selected.append(j)
    avail[j] = False
    while len(selected) < k:
        t = len(selected) - 1
        dj = np.sqrt(max(d2[j], eps))
        e = (S[j, :] - cis[:t, j] @ cis[:t, :]) / dj
        cis[t, :] = e
        d2 = d2 - e**2
        if not np.any(avail & (d2 >= eps)):
            break
        g = np.where(avail & (d2 >= eps), gain(), -np.inf)
        j = int(np.argmax(g))
        selected.append(j)
        avail[j] = False
    for i in select_relevance(rel, n):  # fill (only when exact duplicates exhausted the kernel)
        if len(selected) >= k:
            break
        if i not in selected:
            selected.append(i)
    return selected


def select_xquad(rel: np.ndarray, aspect_rel: np.ndarray, aspect_w: np.ndarray, k: int, lam: float) -> list[int]:
    """xQuAD. aspect_rel: (n, A) in [0,1]; aspect_w: (A,) sums to 1. λ=0 → pure relevance."""
    n = len(rel)
    if n == 0:
        return []
    if lam <= 0.0 or aspect_rel.size == 0 or aspect_w.sum() <= 0:
        return select_relevance(rel, k)
    r = minmax(rel)
    not_covered = np.ones(aspect_rel.shape[1])  # Π_{j∈S}(1 − P(j|n))
    selected: list[int] = []
    avail = np.ones(n, dtype=bool)
    while len(selected) < min(k, n):
        div = aspect_rel @ (aspect_w * not_covered)
        val = np.where(avail, (1.0 - lam) * r + lam * div, -np.inf)
        j = int(np.argmax(val))
        selected.append(j)
        avail[j] = False
        not_covered = not_covered * (1.0 - aspect_rel[j])
    return selected


def need_aspects(need_probs: dict[str, float], share_matrix: np.ndarray, need_ids: list[str],
                 n_aspects: int = 3) -> tuple[list[str], np.ndarray, np.ndarray]:
    """Top-`n_aspects` needs by p(n); P(i|n) = positive share scaled by the best candidate."""
    ranked = [n for n, p in sorted(need_probs.items(), key=lambda kv: -kv[1]) if p > 0 and n in need_ids]
    aspects = ranked[:n_aspects]
    if not aspects:
        return [], np.zeros((share_matrix.shape[0], 0)), np.zeros(0)
    cols = [need_ids.index(a) for a in aspects]
    sh = np.clip(share_matrix[:, cols], 0.0, None)
    mx = sh.max(axis=0)
    P = np.where(mx > 1e-12, sh / np.where(mx > 1e-12, mx, 1.0), 0.0)
    w = np.array([need_probs[a] for a in aspects], dtype=np.float64)
    return aspects, P, w / w.sum()


@dataclass(frozen=True)
class DiversityConfig:
    method: str = "none"  # none | mmr | dpp | xquad
    # mmr: λ (1 = relevance only); dpp: θ (1 = relevance only); xquad: λ (0 = relevance only)
    param: float = 1.0
    depth: int = 20  # re-order only among the top-`depth` relevance candidates
    n_aspects: int = 3

    @property
    def label(self) -> str:
        return "none" if self.method == "none" else f"{self.method}_{self.param:g}"


def select(cfg: DiversityConfig, rel: np.ndarray, emb: np.ndarray, k: int,
           aspect_rel: np.ndarray | None = None, aspect_w: np.ndarray | None = None) -> list[int]:
    if cfg.method == "none":
        return select_relevance(rel, k)
    if cfg.method == "mmr":
        return select_mmr(rel, emb, k, cfg.param)
    if cfg.method == "dpp":
        return select_dpp(rel, emb, k, cfg.param)
    if cfg.method == "xquad":
        A = aspect_rel if aspect_rel is not None else np.zeros((len(rel), 0))
        W = aspect_w if aspect_w is not None else np.zeros(0)
        return select_xquad(rel, A, W, k, cfg.param)
    raise ValueError(f"unknown diversification method {cfg.method!r}; expected one of {METHODS}")


# ---------------------------------------------------------------------------
# response-level wrapper (faithful explanation)
# ---------------------------------------------------------------------------
class DiversifiedRankedItem(RankedItem):
    relevance_rank: int  # rank under the additive relevance score alone (1-based)
    promoted_by_diversity: bool = False  # relevance_rank > k: on the slate only because of diversification
    max_similarity_to_higher: float | None = None  # max image cosine to the cards shown above it
    new_aspects: list[str] = []  # xQuAD: need aspects this card newly covers (P(i|n) ≥ 0.5)


class DiversifiedResponse(Engine02Response):
    items: list[DiversifiedRankedItem]
    diversification: dict[str, Any] = {}


def deep_request(req: Engine02Request, depth: int) -> Engine02Request:
    """Same request, asking the pipeline for `depth` scored cards (no LLM, no per-term counterfactual)."""
    r = req.model_copy(deep=True)
    r.options.top_k = max(depth, req.options.top_k) + 1  # +1 so the relevance rank-(k+1) item is always known
    r.options.n_candidates = max(r.options.n_candidates, r.options.top_k)
    r.options.explain_with_llm = False
    r.options.counterfactual_check = False
    return r


def _cosine_matrix(engine, items: list[RankedItem]) -> np.ndarray:
    pos = engine.catalog.positions([it.item_id for it in items])
    E = np.asarray(engine.image_emb[pos], dtype=np.float64)
    return E @ E.T


def diversify_response(engine, req: Engine02Request, deep: Engine02Response, cfg: DiversityConfig,
                       k: int | None = None) -> DiversifiedResponse:
    """Select k cards out of the relevance-ranked `deep` response (see ``deep_request``)."""
    k = k or req.options.top_k
    cands = list(deep.items)[: max(cfg.depth, k)]
    n = len(cands)
    rel = np.array([it.score for it in cands], dtype=np.float64)
    sims = _cosine_matrix(engine, cands) if n else np.zeros((0, 0))
    emb = np.asarray(engine.image_emb[engine.catalog.positions([it.item_id for it in cands])], dtype=np.float64)

    probs = {x.need_id: x.prob for x in req.needs}
    need_ids = sorted({nid for it in cands for nid in it.need_contributions} | set(probs))
    share = np.array([[it.need_contributions.get(nid, 0.0) for nid in need_ids] for it in cands]) \
        if n else np.zeros((0, len(need_ids)))
    aspects, P, w = need_aspects(probs, share, need_ids, cfg.n_aspects)

    sel = select(cfg, rel, emb, k, P, w) if n else []
    # relevance cut-off = full score of the relevance rank-(k+1) item (deep list is score-sorted)
    cut_idx = k if len(deep.items) > k else None
    all_items = list(deep.items)
    n_terms = len(all_items[0].contributions) if all_items else 0
    contrib = np.array([[c.contribution for c in it.contributions] for it in all_items]) if all_items \
        else np.zeros((0, n_terms))
    sc = ScoredCandidates(scores=np.array([it.score for it in all_items]), terms=[], contrib=contrib,
                          norm=np.zeros_like(contrib))

    el_labels = {e.id: e.label for e in engine.kansei.elements}
    need_labels = engine.kansei.needs
    use_llm = engine.llm if req.options.explain_with_llm else None
    out: list[DiversifiedRankedItem] = []
    covered = np.zeros(P.shape[1])
    for rank, i in enumerate(sel, start=1):
        it = cands[i]
        promoted = i >= k
        contribs = [c.model_copy(deep=True) for c in it.contributions]
        if cut_idx is not None:
            ce = cutoff_explanations(sc, np.array([i, cut_idx]), 1)[i]
            margin = ce.margin
            suff = set(ce.sufficient) if not promoted else set()
        else:
            margin, suff = None, set(range(len(contribs)))
        for j, cb in enumerate(contribs):
            cb.sufficient = j in suff
            cb.rank_without = None
            cb.necessary = None
            cb.diff_vs_cutoff = float(contrib[i, j] - contrib[cut_idx, j]) if cut_idx is not None else None
            cb.cited = bool(cb.sufficient and cb.contribution > 0)
        if promoted:  # show strengths, explicitly not claimed sufficient
            for j in sorted(range(len(contribs)), key=lambda j: -contribs[j].contribution)[:3]:
                contribs[j].cited = contribs[j].contribution > 0
        prev = [sel[r] for r in range(rank - 1)]
        max_sim = float(sims[i, prev].max()) if prev else None
        new_aspects = [aspects[a] for a in range(P.shape[1]) if P[i, a] >= 0.5 and covered[a] < 0.5]
        if P.shape[1]:
            covered = np.maximum(covered, P[i])
        reasons, facts = template_reasons(contribs, el_labels, need_labels, deep.constraint_report.relaxed)
        reasons += [f"注意：{n}" for n in it.attribute_notes]
        if promoted:
            note = f"為了多樣性而納入（純相關度排第 {i + 1} 名"
            if max_sim is not None:
                note += f"，和前面卡片的最高圖片相似度 {max_sim:.2f}"
            if cfg.method == "xquad" and new_aspects:
                note += "，補上需求「" + "、".join(need_labels.get(a, a) for a in new_aspects) + "」"
            note += "）"
            reasons = [note] + reasons
            facts = [{"type": "diversity", "label": "為了多樣性而納入", "relevance_rank": i + 1,
                      "max_similarity": round(max_sim, 2) if max_sim is not None else None}] + facts
        text, src = explain(reasons, facts, engine.vocabulary, use_llm)
        data = it.model_dump()
        data.update(rank=rank, contributions=contribs, margin_vs_cutoff=margin, reasons=reasons,
                    explanation=text, explanation_source=src, relevance_rank=i + 1,
                    promoted_by_diversity=promoted, max_similarity_to_higher=max_sim, new_aspects=new_aspects)
        out.append(DiversifiedRankedItem(**data))

    displaced = []
    for i in range(min(k, n)):
        if i not in sel:
            j = int(np.argmax([sims[i, s] for s in sel])) if sel else None
            displaced.append({"item_id": cands[i].item_id, "relevance_rank": i + 1,
                              "most_similar_shown": cands[sel[j]].item_id if j is not None else None,
                              "cosine": round(float(sims[i, sel[j]]), 4) if j is not None else None})
    base = deep.model_dump(exclude={"items"})
    return DiversifiedResponse(
        **base,
        items=out,
        diversification={"method": cfg.method, "param": cfg.param, "depth": cfg.depth, "aspects": aspects,
                         "promoted": [cands[i].item_id for i in sel if i >= k], "displaced": displaced},
    )


def run_diversified(engine, req: Engine02Request, arm=None, cfg: DiversityConfig = DiversityConfig()) -> DiversifiedResponse:
    """Engine02.run + diversification as post-processing (no pipeline change needed)."""
    deep = engine.run(deep_request(req, cfg.depth), arm)
    return diversify_response(engine, req, deep, cfg)


# ---------------------------------------------------------------------------
# slate metrics (used by scripts/eval_slate.py and tests)
# ---------------------------------------------------------------------------
def ild(sim: np.ndarray) -> float:
    """Intra-list diversity: 1 − mean pairwise cosine."""
    n = sim.shape[0]
    if n < 2:
        return 0.0
    iu = np.triu_indices(n, 1)
    return float(1.0 - sim[iu].mean())


def near_duplicate_rate(sim: np.ndarray, thr: float = 0.95) -> float:
    n = sim.shape[0]
    if n < 2:
        return 0.0
    iu = np.triu_indices(n, 1)
    return float((sim[iu] > thr).mean())


def alpha_ndcg(J: np.ndarray, order: list[int], k: int, alpha: float = 0.5,
               weights: np.ndarray | None = None) -> float:
    """α-NDCG@k (Clarke et al., SIGIR 2008) over binary judgements J (n, A), intent weights optional.
    Ideal ranking by the standard greedy approximation over all n candidates."""
    n, A = J.shape
    if A == 0 or J.sum() == 0:
        return float("nan")
    w = np.ones(A) if weights is None else np.asarray(weights, dtype=np.float64)
    disc = 1.0 / np.log2(np.arange(2, k + 2))

    def dcg(seq):
        seen = np.zeros(A)
        tot = 0.0
        for r, i in enumerate(seq[:k]):
            tot += disc[r] * float((w * J[i] * (1 - alpha) ** seen).sum())
            seen += J[i]
        return tot

    seen = np.zeros(A)
    ideal, left = [], set(range(n))
    for _ in range(min(k, n)):
        best = max(left, key=lambda i: float((w * J[i] * (1 - alpha) ** seen).sum()))
        ideal.append(best)
        left.remove(best)
        seen += J[best]
    idcg = dcg(ideal)
    return dcg(list(order)) / idcg if idcg > 0 else float("nan")
