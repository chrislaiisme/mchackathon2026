"""Preference learning from choices ("愈用愈懂你") over the additive model's design features.

ENGINE 03 records, per round, which cards were shown, which one the user chose and
(optionally) which ones were rejected. Every learner here turns that history into a
continuous Δβ over the *canonical* design elements (antonym poles folded, see
`KanseiTable.load`), which is added to β_d = γ·(Σ_n p(n)K[n,d] + step·Δsteps_d). Because
design terms are not re-normalised in pool scope, adding Δβ_d·c(i,d) to the final score
is exactly the same as changing β_d — so every learner stays inside the explainable
additive model (contributions still sum to the score).

Learners
--------
- `NoLearning`          : Δβ = 0.
- `RuleStep`            : PRD baseline. After each choice, adjust(d, ±1) on the element with
                          the largest |c(chosen) − mean c(shown)| (sign of the difference);
                          a rejection gives the opposite step on its own largest deviation.
                          Δβ = step_size · clip(steps, ±max_steps).
- `BayesLogistic`       : Bradley–Terry / reward-rational choice. The user's choice is a
                          Boltzmann-rational choice among the offered options (Jeon, Milli &
                          Dragan, "Reward-rational (implicit) choice", NeurIPS 2020,
                          arXiv:2002.04833). Pairwise likelihood P(i ≻ j) = σ(λ·w·(c_i − c_j))
                          for the chosen item against every other shown item (and every
                          non-rejected item against each rejected one), or the multinomial
                          logit over the shown set (`likelihood="mnl"`). Gaussian prior centred
                          at the Kansei prior β0 = γ·p(n)·K; Laplace approximation (MAP by
                          Newton + inverse Hessian). Exploits the posterior mean.
- `ThompsonLogistic`    : same posterior, ranks with one sample w ~ N(mean, v·Σ) per round
                          (Chapelle & Li, "An Empirical Evaluation of Thompson Sampling",
                          NeurIPS 2011 — they use a diagonal Laplace posterior for logistic
                          regression; we keep the full 11×11 covariance).
- `LinUCB`              : ridge regression of slate-centred rewards on slate-centred features
                          with an optimism bonus α·sqrt(fᵀA⁻¹f) (Li, Chu, Langford & Schapire,
                          WWW 2010, arXiv:1003.0146). The bonus is *item-level* and cannot be
                          written as a Δβ, so it is returned separately (`PreferenceUpdate.bonus`)
                          and would need its own (non-explainable) score term.
- Rocchio on image embeddings already exists in `pipeline.Engine02.query_embedding`.

Integration
-----------
`PreferenceEngine02.run(req, arm, design_weight_delta=...)` is a subclass-based stand-in for
the proposed contract field `FeedbackState.design_weight_delta: dict[str, float]`; the
coordinator hook is one line in `Engine02._terms` (see `docs/research/recsys-preference.md`).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .kansei import KanseiTable
from .pipeline import Engine02
from .rerank import Term

# ---------------------------------------------------------------------------
# data structures
# ---------------------------------------------------------------------------


@dataclass
class ChoiceRound:
    """One round of ENGINE 03's ledger, in catalog positions."""

    shown: list[int]
    chosen: int | None = None
    rejected: list[int] = field(default_factory=list)


@dataclass
class DesignSpace:
    """The canonical (non-folded) design elements the learners operate on."""

    element_ids: list[str]
    columns: np.ndarray  # indices into engine.design_matrix(...) columns
    K: np.ndarray  # (n_needs, d), folded Kansei table restricted to canonical columns
    need_ids: list[str]

    @classmethod
    def from_kansei(cls, kansei: KanseiTable) -> "DesignSpace":
        cols = [j for j, e in enumerate(kansei.elements) if e.id not in kansei.folded]
        return cls(
            element_ids=[kansei.elements[j].id for j in cols],
            columns=np.array(cols, dtype=int),
            K=kansei.K[:, cols].copy(),
            need_ids=list(kansei.need_ids),
        )

    @property
    def dim(self) -> int:
        return len(self.element_ids)

    def features(self, c_full: np.ndarray) -> np.ndarray:
        return np.asarray(c_full, dtype=np.float64)[:, self.columns]

    def need_vector(self, probs: dict[str, float]) -> np.ndarray:
        return np.array([probs.get(n, 0.0) for n in self.need_ids], dtype=np.float64)

    def prior_mean(self, probs: dict[str, float], need_scale: float = 1.0) -> np.ndarray:
        """β0 = γ·Σ_n p(n)K[n,d] — what the pipeline already uses before any feedback."""
        return need_scale * self.need_vector(probs) @ self.K

    def prior_cov(self, prior_sd: float, kind: str = "isotropic", need_scale: float = 1.0,
                  probs: dict[str, float] | None = None, concentration: float = 1.0) -> np.ndarray:
        """isotropic: σ²I. kansei: σ²I/4 + Cov(γ·pK) with p ~ Dirichlet(concentration·m),
        m = the given need probabilities (flat if none) — puts prior mass on directions the
        Kansei table can express, so a few choices move β along K's row space first."""
        d = self.dim
        if kind == "isotropic":
            return (prior_sd**2) * np.eye(d)
        m = self.need_vector(probs or {})
        m = m / m.sum() if m.sum() > 0 else np.full(len(self.need_ids), 1.0 / len(self.need_ids))
        cov_p = (np.diag(m) - np.outer(m, m)) / (concentration + 1.0)
        cov_beta = need_scale**2 * self.K.T @ cov_p @ self.K
        scale = prior_sd**2 / max(np.trace(cov_beta) / d, 1e-12)
        return scale * cov_beta + (prior_sd**2 / 4.0) * np.eye(d)

    def to_dict(self, vec: np.ndarray, tol: float = 1e-9) -> dict[str, float]:
        return {e: float(v) for e, v in zip(self.element_ids, vec) if abs(v) > tol}


@dataclass
class PreferenceUpdate:
    delta: np.ndarray  # Δβ over DesignSpace.element_ids, added to the pipeline's β
    mean: np.ndarray | None = None  # posterior mean of the full β (for diagnostics)
    cov: np.ndarray | None = None
    bonus_cov: np.ndarray | None = None  # LinUCB: A⁻¹
    bonus_alpha: float = 0.0

    def bonus(self, F: np.ndarray) -> np.ndarray:
        """Optimism bonus per item (LinUCB only; zeros otherwise)."""
        if self.bonus_cov is None or self.bonus_alpha == 0:
            return np.zeros(len(F))
        q = np.einsum("ij,jk,ik->i", F, self.bonus_cov, F)
        return self.bonus_alpha * np.sqrt(np.clip(q, 0, None))

    def weights(self, beta0: np.ndarray) -> np.ndarray:
        return beta0 + self.delta


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def comparison_pairs(history: list[ChoiceRound], F: np.ndarray) -> np.ndarray:
    """Feature differences x = c(winner) − c(loser) implied by the ledger.

    chosen ≻ every other shown item; every non-rejected shown item ≻ each rejected item
    (chosen ≻ rejected is counted once)."""
    rows = []
    for r in history:
        rej = set(r.rejected)
        if r.chosen is not None:
            rows += [F[r.chosen] - F[j] for j in r.shown if j != r.chosen]
        for b in r.rejected:
            rows += [F[j] - F[b] for j in r.shown if j != b and j != r.chosen and j not in rej]
    return np.array(rows, dtype=np.float64).reshape(-1, F.shape[1])


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return np.where(z >= 0, 1.0 / (1.0 + np.exp(-np.abs(z))), np.exp(-np.abs(z)) / (1.0 + np.exp(-np.abs(z))))


def _log1pexp(z: np.ndarray) -> np.ndarray:
    return np.logaddexp(0.0, z)


def laplace_pairwise(X: np.ndarray, m0: np.ndarray, S0: np.ndarray, lam: float,
                     n_iter: int = 50) -> tuple[np.ndarray, np.ndarray]:
    """MAP and Laplace covariance of  N(w; m0, S0) · Π σ(λ w·x)."""
    P0 = np.linalg.inv(S0)
    w = m0.copy()
    if len(X) == 0:
        return w, S0.copy()

    def obj(v):
        d = v - m0
        return 0.5 * d @ P0 @ d + _log1pexp(-lam * (X @ v)).sum()

    for _ in range(n_iter):
        p = _sigmoid(lam * (X @ w))
        g = P0 @ (w - m0) - lam * X.T @ (1 - p)
        H = P0 + lam**2 * (X.T * (p * (1 - p))) @ X
        step = np.linalg.solve(H, g)
        t, f0 = 1.0, obj(w)
        while obj(w - t * step) > f0 + 1e-12 and t > 1e-6:
            t *= 0.5
        w = w - t * step
        if np.linalg.norm(t * step) < 1e-9:
            break
    p = _sigmoid(lam * (X @ w))
    H = P0 + lam**2 * (X.T * (p * (1 - p))) @ X
    cov = np.linalg.inv(H)
    return w, (cov + cov.T) / 2


def laplace_mnl(history: list[ChoiceRound], F: np.ndarray, m0: np.ndarray, S0: np.ndarray, lam: float,
                n_iter: int = 50) -> tuple[np.ndarray, np.ndarray]:
    """Multinomial-logit (Boltzmann choice among the shown set) version; rejections are
    modelled as 'least preferred' = choice under −w among the shown set."""
    sets = []  # (features of the offered set, index of the picked one, sign)
    for r in history:
        S = F[r.shown]
        if r.chosen is not None and r.chosen in r.shown:
            sets.append((S, r.shown.index(r.chosen), 1.0))
        for b in r.rejected:
            if b in r.shown:
                sets.append((S, r.shown.index(b), -1.0))
    P0 = np.linalg.inv(S0)
    w = m0.copy()
    if not sets:
        return w, S0.copy()

    def parts(v):
        f = 0.5 * (v - m0) @ P0 @ (v - m0)
        g = P0 @ (v - m0)
        H = P0.copy()
        for S, i, s in sets:
            z = s * lam * (S @ v)
            z = z - z.max()
            pr = np.exp(z) / np.exp(z).sum()
            f -= np.log(pr[i] + 1e-300)
            mu = pr @ S
            g -= s * lam * (S[i] - mu)
            Sc = S - mu
            H += lam**2 * (Sc.T * pr) @ Sc
        return f, g, H

    for _ in range(n_iter):
        f0, g, H = parts(w)
        step = np.linalg.solve(H, g)
        t = 1.0
        while parts(w - t * step)[0] > f0 + 1e-12 and t > 1e-6:
            t *= 0.5
        w = w - t * step
        if np.linalg.norm(t * step) < 1e-9:
            break
    cov = np.linalg.inv(parts(w)[2])
    return w, (cov + cov.T) / 2


# ---------------------------------------------------------------------------
# learners
# ---------------------------------------------------------------------------


class NoLearning:
    name = "none"

    def update(self, history, F, beta0, rng=None) -> PreferenceUpdate:
        return PreferenceUpdate(delta=np.zeros(F.shape[1]), mean=beta0.copy())


@dataclass
class RuleStep:
    """PRD adjust(d, ±1): one step per choice on the most distinctive element."""

    step_size: float = 0.25
    max_steps: int = 3
    use_rejected: bool = True
    name: str = "rulestep"

    def steps(self, history: list[ChoiceRound], F: np.ndarray) -> np.ndarray:
        s = np.zeros(F.shape[1])
        for r in history:
            mean_shown = F[r.shown].mean(axis=0)
            if r.chosen is not None:
                diff = F[r.chosen] - mean_shown
                d = int(np.argmax(np.abs(diff)))
                s[d] += np.sign(diff[d])
            if self.use_rejected:
                for b in r.rejected:
                    diff = F[b] - mean_shown
                    d = int(np.argmax(np.abs(diff)))
                    s[d] -= np.sign(diff[d])
        return np.clip(s, -self.max_steps, self.max_steps)

    def update(self, history, F, beta0, rng=None) -> PreferenceUpdate:
        delta = self.step_size * self.steps(history, F)
        return PreferenceUpdate(delta=delta, mean=beta0 + delta)


@dataclass
class BayesLogistic:
    """Bradley–Terry / reward-rational choice with a Kansei-centred Gaussian prior."""

    rationality: float = 1.0  # λ: how deterministic we assume the user is, in score units
    prior_sd: float = 0.5
    prior: str = "isotropic"  # | "kansei"
    likelihood: str = "pairwise"  # | "mnl"
    name: str = "bayes"
    # damping of early updates (defaults = undamped). Applied to Δβ in this order:
    # shrink_kappa κ: Δβ ← Δβ · n/(n+κ), n = number of rounds with a choice or rejection
    # max_abs_delta c: per-element clip |Δβ_d| ≤ c (PRD adjust cap is 3 steps × 0.25 = 0.75)
    shrink_kappa: float | None = None
    max_abs_delta: float | None = None

    def damp(self, delta: np.ndarray, history: list[ChoiceRound]) -> np.ndarray:
        delta = np.asarray(delta, dtype=np.float64)
        if self.shrink_kappa is not None:
            n = sum(1 for r in history if r.chosen is not None or r.rejected)
            delta = delta * (n / (n + self.shrink_kappa) if n > 0 else 0.0)
        if self.max_abs_delta is not None:
            delta = np.clip(delta, -self.max_abs_delta, self.max_abs_delta)
        return delta

    def posterior(self, history, F, beta0, prior_cov=None) -> tuple[np.ndarray, np.ndarray]:
        S0 = prior_cov if prior_cov is not None else self.prior_sd**2 * np.eye(F.shape[1])
        if self.likelihood == "mnl":
            return laplace_mnl(history, F, beta0, S0, self.rationality)
        return laplace_pairwise(comparison_pairs(history, F), beta0, S0, self.rationality)

    def update(self, history, F, beta0, rng=None, prior_cov=None) -> PreferenceUpdate:
        mean, cov = self.posterior(history, F, beta0, prior_cov)
        return PreferenceUpdate(delta=self.damp(mean - beta0, history), mean=mean, cov=cov)


@dataclass
class ThompsonLogistic(BayesLogistic):
    var_scale: float = 1.0
    name: str = "thompson"

    def update(self, history, F, beta0, rng=None, prior_cov=None) -> PreferenceUpdate:
        mean, cov = self.posterior(history, F, beta0, prior_cov)
        rng = rng if rng is not None else np.random.default_rng()
        if not history:  # nothing learned yet: do not perturb the first page
            return PreferenceUpdate(delta=np.zeros_like(mean), mean=mean, cov=cov)
        w = rng.multivariate_normal(mean, self.var_scale * cov, method="cholesky")
        return PreferenceUpdate(delta=self.damp(w - beta0, history), mean=mean, cov=cov)


@dataclass
class LinUCB:
    """Ridge on slate-centred rewards (chosen +1, rejected −1, others 0) with optimism."""

    alpha: float = 0.3
    reward: float = 1.0
    ridge: float = 1.0
    name: str = "linucb"

    def update(self, history, F, beta0, rng=None) -> PreferenceUpdate:
        d = F.shape[1]
        A = self.ridge * np.eye(d)
        b = self.ridge * beta0.copy()
        for r in history:
            S = F[r.shown]
            y = np.zeros(len(r.shown))
            for i, p in enumerate(r.shown):
                if p == r.chosen:
                    y[i] += self.reward
                if p in r.rejected:
                    y[i] -= self.reward
            Sc, yc = S - S.mean(axis=0), y - y.mean()
            A += Sc.T @ Sc
            b += Sc.T @ yc
        A_inv = np.linalg.inv(A)
        theta = A_inv @ b
        if not history:
            return PreferenceUpdate(delta=np.zeros(d), mean=theta)
        return PreferenceUpdate(delta=theta - beta0, mean=theta, bonus_cov=A_inv, bonus_alpha=self.alpha)


def rerank_candidates(base_scores: np.ndarray, F_cand: np.ndarray, update: PreferenceUpdate,
                      need_scale: float = 1.0, use_bonus: bool = True) -> np.ndarray:
    """Score after the hook: base + γ·Δβ·c(i) (+ LinUCB bonus). Identical to re-running the
    pipeline with the Δβ hook, because design terms are not re-normalised in pool scope."""
    s = np.asarray(base_scores, dtype=np.float64) + need_scale * F_cand @ update.delta
    if use_bonus:
        s = s + update.bonus(F_cand)
    return s


# ---------------------------------------------------------------------------
# pipeline wrapper (stand-in for the proposed contract field)
# ---------------------------------------------------------------------------


class PreferenceEngine02(Engine02):
    """Engine02 + `design_weight_delta` without touching pipeline.py.

    The proposed hook is `FeedbackState.design_weight_delta: dict[str, float]` read in
    `Engine02._terms` right after `beta_needs, beta_fb = self.kansei.beta(...)`:

        for d, v in req.feedback.design_weight_delta.items():
            canon = self.kansei.folded.get(d, d); sign = -1.0 if d in self.kansei.folded else 1.0
            beta_fb[self.kansei.element_ids.index(canon)] += sign * v

    Here the same effect is obtained by editing the design terms after `_terms` runs; the
    learned part is attributed to the "feedback_adjust" need share, so cards say
    「你上一輪的回饋」 and contributions still sum to the score.
    """

    _delta: dict[str, float] = {}

    def run(self, req, arm=None, design_weight_delta: dict[str, float] | None = None):
        self._delta = dict(design_weight_delta or {})
        try:
            return super().run(req, arm)
        finally:
            self._delta = {}

    def _terms(self, req, arm, pool, cand, dense_all, bm25_all, top, text):
        terms = super()._terms(req, arm, pool, cand, dense_all, bm25_all, top, text)
        if not self._delta or not arm.additive_rerank or not arm.use_design:
            return terms
        c_mat = self.design_matrix(arm)
        ids = self.kansei.element_ids
        by_name = {t.name: t for t in terms}
        for d, v in self._delta.items():
            canon = self.kansei.folded.get(d, d)
            if canon not in ids:
                continue
            add = float(arm.need_scale * (-v if d in self.kansei.folded else v))
            if abs(add) < 1e-12:
                continue
            name = f"design:{canon}"
            if name in by_name:
                t = by_name[name]
                t.weight = float(t.weight + add)
                t.need_shares_per_unit["feedback_adjust"] = t.need_shares_per_unit.get("feedback_adjust", 0.0) + add
            else:
                j = ids.index(canon)
                t = Term(name, "design", c_mat[cand, j], add, {"feedback_adjust": add},
                         normalize=arm.norm_scope != "pool")
                terms.append(t)
                by_name[name] = t
        return terms
