"""Learning the additive ranking weights without giving up the additive explanation.

ENGINE 02 scores a candidate as S(i) = Σ_t w_t · x_t(i) (engine02/rerank.py). The weights
w_dense, w_bm25 (and RRF k / convex α of the candidate stage) were set by hand. This module
learns them from graded queries while keeping the scorer a **non-negative linear** function of
the same normalised terms, so contributions still sum to the score and every term keeps its sign
("more of this evidence never lowers the score").

Learners
- Coordinate ascent on NDCG@k — Metzler & Croft, "Linear feature-based models for information
  retrieval", Information Retrieval 10(3), 2007. One weight at a time, line search, L1-normalised,
  random restarts; we additionally restrict the search to w ≥ 0.
- Pairwise logistic loss on a linear scorer — RankNet (Burges et al., ICML 2005) with a linear
  "network"; projected gradient descent (w ← max(w, 0)) keeps the model non-negative.
- Grid search over (w_dense : w_bm25) × candidate stage (RRF k or dense-only), and over RRF k /
  convex α for the pure fusion arms (Cormack et al. SIGIR 2009; Bruch et al. TOIS 2023).
- Query-type-aware variant: separate weights for queries whose tokens are covered by the catalog
  vocabulary (BM25Index.coverage ≥ θ) and those that are not — lexical and paraphrased wording
  behave in opposite directions (T1), and coverage is observable at run time (no oracle).

Everything is simulated offline from features captured once per query by `CapturingEngine02`
(a subclass; pipeline.py is untouched). `LinearRanker.rank` reproduces Engine02.run exactly for the
full / hybrid / dense / adaptive arms (checked in scripts/eval_ltr.py against the real engine). `LearnedWeightsEngine`
is the integration hook: it loads a learned-weights JSON and swaps ArmConfig values per query.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

import numpy as np

from .config import ARMS, ArmConfig
from .contracts import Engine02Options, Engine02Request
from .eval.metrics import dcg
from .fusion import ranks_desc
from .pipeline import Engine02, build_retrieval_text
from .rerank import additive_score

CORE_FEATURES = ("dense", "bm25")
EXT_FEATURES = ("dense", "bm25", "dense_rrf", "bm25_rrf")


# ---------------------------------------------------------------------------
# feature capture
class CapturingEngine02(Engine02):
    """Engine02 that keeps the internals of the last run (pool scores, candidate terms, sc.norm)."""

    last_capture: dict | None = None

    def _terms(self, req, arm, pool, cand, dense_all, bm25_all, top, text):
        terms = super()._terms(req, arm, pool, cand, dense_all, bm25_all, top, text)
        sc = additive_score(terms)
        self.last_capture = dict(
            arm=arm, pool=np.asarray(pool), dense_all=np.asarray(dense_all, dtype=np.float64).copy(),
            bm25_all=np.asarray(bm25_all, dtype=np.float64).copy(), cand=np.asarray(cand).copy(),
            term_names=[t.name for t in sc.terms], term_groups=[t.group for t in sc.terms],
            term_weights=np.array([t.weight for t in sc.terms]), norm=sc.norm.copy(), scores=sc.scores.copy(),
        )
        return terms


def _stats(x: np.ndarray) -> tuple[float, float]:
    return (float(x.mean()), float(x.std())) if x.size else (0.0, 1.0)


@dataclass
class QueryFeatures:
    """Everything needed to re-rank one (query, wording) offline for any weight/fusion setting.

    Arrays are over U = union of the top-`depth` pool items by dense and by BM25, sorted by pool
    order (so stable sorts break ties exactly like the pipeline)."""

    qid: str
    group: str  # base query id: both wordings of a query share it (CV folds split by group)
    wording: str
    text: str
    coverage: float
    n_pool: int
    item_ids: list[str]
    dense_raw: np.ndarray
    bm25_raw: np.ndarray
    dense_rank: np.ndarray  # 1-based rank inside the filtered pool
    bm25_rank: np.ndarray
    dense_stats: tuple[float, float]  # pool mean / std (norm_scope="pool")
    bm25_stats: tuple[float, float]
    dense_minmax: tuple[float, float]
    bm25_minmax: tuple[float, float]
    design: np.ndarray  # Σ_d β_d c(i,d) with the request's needs (0 without needs)
    grades: np.ndarray  # graded relevance of each U item
    idcg: dict[int, float] = field(default_factory=dict)  # over the whole catalog, per cutoff
    n_exact: int = 0  # number of grade-3 items in the catalog
    engine_top: dict[str, list[str]] = field(default_factory=dict)  # engine.run output, for validation


def capture_query(engine: CapturingEngine02, qid: str, group: str, wording: str, text: str,
                  grades: dict[str, float], depth: int = 500, top_k: int = 10, n_candidates: int = 100,
                  needs=None, arm: ArmConfig | None = None) -> QueryFeatures:
    arm = arm or ARMS["full"]
    req = Engine02Request(session_id=qid, retrieval_text=text, needs=needs or [],
                          options=Engine02Options(top_k=top_k, n_candidates=n_candidates, explain_with_llm=False,
                                                  counterfactual_check=False))
    resp = engine.run(req, arm)
    cap = engine.last_capture
    pool, d_all, b_all = cap["pool"], cap["dense_all"], cap["bm25_all"]
    rd, rb = ranks_desc(d_all), ranks_desc(b_all)
    u = np.flatnonzero((rd <= depth) | (rb <= depth))  # sorted = pool order
    ids_all = engine.catalog.items["item_id"].astype(str).to_numpy()
    item_ids = [str(x) for x in ids_all[pool[u]]]
    design = np.zeros(len(u))
    if arm.use_design and req.needs:
        probs = {n.need_id: n.prob for n in req.needs}
        bn, bf = engine.kansei.beta(probs, req.feedback.design_adjust_steps)
        design = engine.design_matrix(arm)[pool[u]] @ (arm.need_scale * (bn + bf))
    g = np.array([grades.get(i, 0.0) for i in item_ids])
    ideal = sorted(grades.values(), reverse=True)
    return QueryFeatures(
        qid=qid, group=group, wording=wording, text=text, coverage=float(engine.bm25.coverage(text)),
        n_pool=int(len(pool)), item_ids=item_ids, dense_raw=d_all[u], bm25_raw=b_all[u], dense_rank=rd[u],
        bm25_rank=rb[u], dense_stats=_stats(d_all), bm25_stats=_stats(b_all),
        dense_minmax=(float(d_all.min()), float(d_all.max())), bm25_minmax=(float(b_all.min()), float(b_all.max())),
        design=design, grades=g, idcg={k: dcg(ideal, k) for k in (5, 10)},
        n_exact=int(sum(v >= 3 for v in grades.values())),
        engine_top={arm.name: [it.item_id for it in resp.items]},
    )


# ---------------------------------------------------------------------------
# rankers
def _z(x, stats):
    mu, sd = stats
    return (x - mu) / (sd if sd > 1e-12 else 1.0)


def _mm(x, lohi):
    lo, hi = lohi
    return np.zeros_like(x) if hi - lo < 1e-12 else (x - lo) / (hi - lo)


def feature_matrix(qf: QueryFeatures, features=EXT_FEATURES, rrf_k: int = 60) -> np.ndarray:
    cols = []
    for f in features:
        if f == "dense":
            cols.append(_z(qf.dense_raw, qf.dense_stats))
        elif f == "bm25":
            cols.append(_z(qf.bm25_raw, qf.bm25_stats))
        elif f == "dense_rrf":  # (k+1)/(k+rank) ∈ (0, 1]: rank-based evidence, 1 for the top item
            cols.append((rrf_k + 1) / (rrf_k + qf.dense_rank))
        elif f == "bm25_rrf":
            cols.append((rrf_k + 1) / (rrf_k + qf.bm25_rank))
        elif f == "design":
            cols.append(qf.design)
        else:
            raise KeyError(f)
    return np.stack(cols, axis=1) if cols else np.zeros((len(qf.item_ids), 0))


@dataclass(frozen=True)
class LinearRanker:
    """Candidate stage (as Engine02) + optional non-negative linear rerank over named features.

    weights == {} → final order is the candidate-fusion order (the hybrid_* arms)."""

    weights: tuple[tuple[str, float], ...] = (("dense", 1.0), ("bm25", 0.5))
    fusion: str = "rrf"  # rrf | convex | dense | bm25
    rrf_k: int = 60
    rrf_depth: int = 200
    convex_alpha: float = 0.5
    n_candidates: int = 100
    adaptive_bm25: bool = False  # mirror ArmConfig.bm25_adaptive
    min_coverage: float = 0.5

    @property
    def w(self) -> dict[str, float]:
        return dict(self.weights)

    def candidates(self, qf: QueryFeatures) -> tuple[np.ndarray, "LinearRanker"]:
        me = self
        if self.adaptive_bm25:
            scale = qf.coverage if qf.coverage >= self.min_coverage else 0.0
            w = {k: (v * scale if k in ("bm25", "bm25_rrf") else v) for k, v in self.weights}
            fusion = "dense" if scale == 0.0 and self.fusion in ("rrf", "convex") else self.fusion
            me = replace(self, weights=tuple(w.items()), fusion=fusion)
        if me.fusion == "dense":
            fused = qf.dense_raw
        elif me.fusion == "bm25":
            fused = qf.bm25_raw
        elif me.fusion == "convex":
            fused = me.convex_alpha * _mm(qf.dense_raw, qf.dense_minmax) + (1 - me.convex_alpha) * _mm(
                qf.bm25_raw, qf.bm25_minmax)
        else:
            fused = np.zeros(len(qf.item_ids))
            for r in (qf.dense_rank, qf.bm25_rank):
                fused += np.where(r <= me.rrf_depth, 1.0 / (me.rrf_k + r), 0.0)
        n = min(me.n_candidates, qf.n_pool)
        return np.argsort(-fused, kind="stable")[:n], me

    def rank(self, qf: QueryFeatures, top_k: int = 10) -> list[str]:
        cand, me = self.candidates(qf)
        w = {k: v for k, v in me.weights if abs(v) > 1e-12}
        if w:
            X = feature_matrix(qf, tuple(w), me.rrf_k)[cand]
            order = cand[np.argsort(-(X @ np.array(list(w.values()))), kind="stable")]
        elif me.fusion == "rrf":
            # pipeline._terms re-scores the fusion-only RRF arm *without* the depth cut-off
            s = 1.0 / (me.rrf_k + qf.dense_rank[cand]) + 1.0 / (me.rrf_k + qf.bm25_rank[cand])
            order = cand[np.argsort(-s, kind="stable")]
        else:
            order = cand
        return [qf.item_ids[i] for i in order[:top_k]]

    def to_arm_values(self) -> dict:
        w = self.w
        extra = sorted(set(w) - {"dense", "bm25"})
        out = dict(w_dense=w.get("dense", 0.0), w_bm25=w.get("bm25", 0.0), candidate_fusion=self.fusion,
                   rrf_k=self.rrf_k, convex_alpha=self.convex_alpha,
                   additive_rerank=bool(w))
        if extra:
            out["extra_terms"] = {k: w[k] for k in extra}  # need new Terms in pipeline._terms
        return out


@dataclass(frozen=True)
class TypeAwareRanker:
    covered: LinearRanker
    uncovered: LinearRanker
    threshold: float = 0.5

    def pick(self, coverage: float) -> LinearRanker:
        return self.covered if coverage >= self.threshold else self.uncovered

    def rank(self, qf: QueryFeatures, top_k: int = 10) -> list[str]:
        return self.pick(qf.coverage).rank(qf, top_k)


def rescale(weights: dict[str, float], total: float = 1.5) -> dict[str, float]:
    """Ranking is scale-invariant; fix Σw to the hand-set w_dense + w_bm25 (1.5) so the retrieval
    terms keep the same magnitude relative to the design/compat/trend terms."""
    s = sum(weights.values())
    return {k: (v / s * total if s > 0 else 0.0) for k, v in weights.items()}


# ---------------------------------------------------------------------------
# vectorised training batch (candidate stage fixed)
@dataclass
class Batch:
    X: np.ndarray  # (Q, N, F) features of candidates in fusion order
    G: np.ndarray  # (Q, N) gains 2^g - 1
    R: np.ndarray  # (Q, N) raw grades
    M: np.ndarray  # (Q, N) valid mask
    idcg: np.ndarray  # (Q,)
    features: tuple[str, ...]
    k: int


def make_batch(qfs: list[QueryFeatures], features=CORE_FEATURES, cand_ranker: LinearRanker | None = None,
               k: int = 5) -> Batch:
    cand_ranker = cand_ranker or LinearRanker()
    n = cand_ranker.n_candidates
    Q, F = len(qfs), len(features)
    X, G, R, M = np.zeros((Q, n, F)), np.zeros((Q, n)), np.zeros((Q, n)), np.zeros((Q, n), dtype=bool)
    for q, qf in enumerate(qfs):
        cand, me = cand_ranker.candidates(qf)
        m = len(cand)
        X[q, :m] = feature_matrix(qf, features, me.rrf_k)[cand]
        R[q, :m] = qf.grades[cand]
        G[q, :m] = 2 ** qf.grades[cand] - 1
        M[q, :m] = True
    idcg = np.array([qf.idcg[k] for qf in qfs])
    return Batch(X, G, R, M, idcg, tuple(features), k)


_DISC = {}


def batch_ndcg(b: Batch, w: np.ndarray) -> np.ndarray:
    s = np.where(b.M, b.X @ w, -np.inf)
    top = np.argsort(-s, axis=1, kind="stable")[:, : b.k]
    if b.k not in _DISC:
        _DISC[b.k] = 1.0 / np.log2(np.arange(2, b.k + 2))
    g = np.take_along_axis(b.G, top, axis=1) * np.take_along_axis(b.M, top, axis=1)
    return np.where(b.idcg > 0, (g * _DISC[b.k][: g.shape[1]]).sum(axis=1) / np.maximum(b.idcg, 1e-12), 0.0)


def coordinate_ascent(b: Batch, n_restarts: int = 5, max_iter: int = 20, seed: int = 0, tol: float = 1e-6
                      ) -> tuple[np.ndarray, float]:
    """Metzler & Croft (2007) coordinate ascent with the extra constraint w ≥ 0 and ||w||₁ = 1."""
    F = b.X.shape[2]
    rng = np.random.default_rng(seed)
    grid = np.concatenate([[0.0], np.logspace(-3, 3, 37)])
    best_w, best_v = np.full(F, 1.0 / F), -1.0
    for r in range(n_restarts):
        w = np.full(F, 1.0 / F) if r == 0 else rng.dirichlet(np.ones(F))
        v = batch_ndcg(b, w).mean()
        for _ in range(max_iter):
            improved = False
            for j in rng.permutation(F):
                others = w.sum() - w[j]
                scale = others if others > 0 else 1.0
                for val in grid * scale:
                    cand = w.copy()
                    cand[j] = val
                    if cand.sum() <= 0:
                        continue
                    cand = cand / cand.sum()
                    cv = batch_ndcg(b, cand).mean()
                    if cv > v + tol:
                        w, v, improved = cand, cv, True
            if not improved:
                break
        if v > best_v + tol:
            best_w, best_v = w, v
    return best_w, float(best_v)


def pairwise_logistic(b: Batch, l2: float = 1e-3, lr: float = 0.1, epochs: int = 500, max_pairs: int = 300,
                      seed: int = 0) -> np.ndarray:
    """Linear RankNet (Burges et al. 2005): minimise mean log(1+exp(-(s_i - s_j))) over pairs with
    grade_i > grade_j, projected gradient descent onto w ≥ 0. Features are standardised for the
    optimisation and mapped back (division by a positive std keeps w ≥ 0)."""
    rng = np.random.default_rng(seed)
    F = b.X.shape[2]
    sd = b.X[b.M].std(axis=0)
    sd = np.where(sd > 1e-12, sd, 1.0)
    diffs = []
    for q in range(b.X.shape[0]):
        m = np.flatnonzero(b.M[q])
        g = b.R[q, m]
        hi, lo = np.nonzero(g[:, None] > g[None, :])
        if len(hi) == 0:
            continue
        if len(hi) > max_pairs:
            sel = rng.choice(len(hi), max_pairs, replace=False)
            hi, lo = hi[sel], lo[sel]
        diffs.append((b.X[q, m[hi]] - b.X[q, m[lo]]) / sd)
    if not diffs:
        return np.full(F, 1.0 / F)
    D = np.concatenate(diffs)
    w = np.full(F, 1.0 / F)
    m1, m2 = np.zeros(F), np.zeros(F)
    for t in range(1, epochs + 1):  # Adam + projection
        z = D @ w
        p = 1.0 / (1.0 + np.exp(np.clip(z, -50, 50)))  # = sigmoid(-z)
        grad = -(D * p[:, None]).mean(axis=0) + 2 * l2 * w
        m1 = 0.9 * m1 + 0.1 * grad
        m2 = 0.999 * m2 + 0.001 * grad**2
        w = np.maximum(w - lr * (m1 / (1 - 0.9**t)) / (np.sqrt(m2 / (1 - 0.999**t)) + 1e-8), 0.0)
    w = w / sd
    return w / w.sum() if w.sum() > 0 else np.full(F, 1.0 / F)


def mean_ndcg(qfs: list[QueryFeatures], ranker, k: int = 5) -> float:
    vals = []
    for qf in qfs:
        ids = ranker.rank(qf, k)
        grades = {i: g for i, g in zip(qf.item_ids, qf.grades) if g > 0}
        gains = [grades.get(i, 0.0) for i in ids]
        vals.append(dcg(gains, k) / qf.idcg[k] if qf.idcg[k] > 0 else 0.0)
    return float(np.mean(vals)) if vals else 0.0


# ---------------------------------------------------------------------------
# learners that return rankers
RRF_KS = (1, 5, 10, 20, 40, 60, 100, 200)
RATIOS = tuple(np.round(np.linspace(0, 1, 21), 3))  # share of bm25 in (dense, bm25)


def learn_grid_full(qfs, k: int = 5, ks=RRF_KS, ratios=RATIOS) -> LinearRanker:
    """Grid over candidate stage (dense-only or RRF k) × w_bm25/(w_dense+w_bm25)."""
    best, best_v = None, -1.0
    stages = [LinearRanker(fusion="dense")] + [LinearRanker(fusion="rrf", rrf_k=kk) for kk in ks]
    for st in stages:
        b = make_batch(qfs, CORE_FEATURES, st, k)
        for r in ratios:
            w = np.array([1 - r, r])
            v = batch_ndcg(b, w).mean()
            if v > best_v + 1e-9:
                best_v, best = v, replace(st, weights=tuple(zip(CORE_FEATURES, rescale(dict(zip(CORE_FEATURES, w))).values())))
    return best


def learn_grid_rrf(qfs, k: int = 5, ks=RRF_KS) -> LinearRanker:
    return max((LinearRanker(weights=(), fusion="rrf", rrf_k=kk) for kk in ks), key=lambda r: mean_ndcg(qfs, r, k))


def learn_grid_convex(qfs, k: int = 5, alphas=tuple(np.round(np.linspace(0, 1, 21), 3))) -> LinearRanker:
    return max((LinearRanker(weights=(), fusion="convex", convex_alpha=float(a)) for a in alphas),
               key=lambda r: mean_ndcg(qfs, r, k))


def learn_linear(qfs, method: str = "ca", features=CORE_FEATURES, k: int = 5, seed: int = 0,
                 stage: LinearRanker | None = None) -> LinearRanker:
    stage = stage or LinearRanker()  # candidate stage as in the full arm (RRF k=60, top-100)
    b = make_batch(qfs, features, stage, k)
    w = coordinate_ascent(b, seed=seed)[0] if method == "ca" else pairwise_logistic(b, seed=seed)
    return replace(stage, weights=tuple(rescale(dict(zip(features, map(float, w)))).items()))


THRESHOLDS = (0.5, 0.6, 0.7, 0.8, 0.9, 1.0)


def learn_type_aware(qfs, learner, thresholds=THRESHOLDS, k: int = 5, **kw) -> TypeAwareRanker:
    """Fit one ranker per coverage group; the threshold θ itself is chosen on the training queries
    (coverage is observable at run time, so this uses no wording oracle)."""
    fallback = learner(qfs, **kw)
    best, best_v = None, -1.0
    for th in thresholds:
        hi = [q for q in qfs if q.coverage >= th]
        lo = [q for q in qfs if q.coverage < th]
        r = TypeAwareRanker(covered=learner(hi, **kw) if hi else fallback,
                            uncovered=learner(lo, **kw) if lo else fallback, threshold=float(th))
        v = mean_ndcg(qfs, r, k)
        if v > best_v + 1e-9:
            best, best_v = r, v
    return best


# ---------------------------------------------------------------------------
# integration hook
def ranker_to_json(r, provenance: dict | None = None) -> dict:
    def one(x: LinearRanker) -> dict:
        return x.to_arm_values()

    if isinstance(r, TypeAwareRanker):
        groups = {"covered": one(r.covered), "uncovered": one(r.uncovered)}
        thr = r.threshold
    else:
        groups = {"covered": one(r), "uncovered": one(r)}
        thr = 0.0
    return {"schema": "engine02.ltr/v1", "coverage_threshold": thr, "groups": groups,
            "provenance": provenance or {}}


class LearnedWeightsEngine(Engine02):
    """Engine02 that swaps the retrieval weights per query from a learned-weights JSON.

    For each request: coverage = bm25.coverage(retrieval text); group = covered if coverage ≥
    threshold else uncovered; the arm's w_dense, w_bm25, candidate_fusion, rrf_k, convex_alpha are
    replaced by the group's values. Only arms with additive_rerank=True are changed, so the
    fusion-only ablation arms stay as they are. All other terms (design, compat, trend, penalty)
    keep their weights, and the contributions still sum to the score."""

    def __init__(self, *args, learned: dict | str | Path, **kw):
        super().__init__(*args, **kw)
        self.learned = json.loads(Path(learned).read_text(encoding="utf-8")) if not isinstance(learned, dict) else learned

    def arm_for(self, text: str, arm: ArmConfig) -> ArmConfig:
        if not arm.additive_rerank:
            return arm
        cov = self.bm25.coverage(text)
        g = self.learned["groups"]["covered" if cov >= self.learned["coverage_threshold"] else "uncovered"]
        if not g.get("additive_rerank", True):
            return arm
        return replace(arm, name=f"{arm.name}+ltr", w_dense=float(g["w_dense"]), w_bm25=float(g["w_bm25"]),
                       candidate_fusion=g["candidate_fusion"], rrf_k=int(g["rrf_k"]),
                       convex_alpha=float(g["convex_alpha"]), bm25_adaptive=False)

    def run(self, req: Engine02Request, arm: ArmConfig | str | None = None):
        arm = ARMS[arm] if isinstance(arm, str) else (arm or ARMS[req.options.arm])
        return super().run(req, self.arm_for(build_retrieval_text(req), arm))


def qf_to_dict(qf: QueryFeatures) -> dict:
    d = asdict(qf)
    return {k: (v.tolist() if isinstance(v, np.ndarray) else v) for k, v in d.items()}


def qf_from_dict(d: dict) -> QueryFeatures:
    arr = {"dense_raw", "bm25_raw", "dense_rank", "bm25_rank", "design", "grades"}
    kw = {k: (np.asarray(v) if k in arr else v) for k, v in d.items()}
    for k in ("dense_stats", "bm25_stats", "dense_minmax", "bm25_minmax"):
        kw[k] = tuple(kw[k])
    kw["idcg"] = {int(k): v for k, v in kw["idcg"].items()}
    return QueryFeatures(**kw)
