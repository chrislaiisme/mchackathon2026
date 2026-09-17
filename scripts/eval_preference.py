"""T7: does ENGINE 02 learn the user's taste from choices? (simulated users)

  python scripts/eval_preference.py --catalog data/catalog/kagl --encoder marqo-fashionSigLIP --device cuda \
      --cache-dir /tmp/neil/agents/preference/index_kagl --stage tune --out reports/agents/preference/kagl
  python scripts/eval_preference.py ... --stage main --best reports/agents/preference/kagl/best.json

Simulated user (NOT a real person; see docs/research/recsys-preference.md for caveats)
- query target = a (gender, color, subcategory, category, occasion) group from eval/tasks.make_queries;
  the system only gets hard filters category+gender and the text "{gender} {subcategory}".
- hidden taste: p*(n) ~ Dirichlet(0.3), w̃ = p*·K + noise·η (η ~ N(0, I)) over canonical design elements.
  hidden utility u(i) = relevance(i) + strength · z_pool(w̃·c(i))      (utility="design", CIRCULAR:
  the simulator uses the same c(i,d) features the learners use)
  or u(i) = relevance(i) + strength · z_pool(v*·m(i)) with m = metadata colour-family / occasion /
  season one-hots, v* ~ N(0, I)                                       (utility="metadata", no c(i,d))
  relevance(i) = Query.grades (3 all attributes, 2 subcategory+colour, 1 subcategory, 0 otherwise).
- the system does not know p*: needs="flat" gives it uniform p(n); needs="informed" a noisy estimate.
- each round: top-5 shown; user picks argmax(u/τ + Gumbel) (softmax / Bradley–Terry choice, common
  random numbers per item across methods) or argmax u (τ=0); optionally rejects the worst shown item.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from engine02.catalog import Catalog  # noqa: E402
from engine02.config import ARMS  # noqa: E402
from engine02.constraints import filter_with_relaxation  # noqa: E402
from engine02.contracts import (  # noqa: E402
    Engine02Options,
    Engine02Request,
    FeedbackState,
    HardConstraints,
    NeedProbability,
    Slot,
    SlotState,
)
from engine02.eval.metrics import bootstrap_ci, ndcg_at_k, paired_permutation_test  # noqa: E402
from engine02.eval.tasks import BRIGHT, DARK, LIGHT, MUTED, make_queries  # noqa: E402
from engine02.preference import (  # noqa: E402
    BayesLogistic,
    ChoiceRound,
    DesignSpace,
    LinUCB,
    NoLearning,
    PreferenceEngine02,
    PreferenceUpdate,
    RuleStep,
    ThompsonLogistic,
    rerank_candidates,
)

LEARN_ARM = replace(ARMS["full"], name="pref_learn", use_rocchio=False, use_penalty=False)
ROCCHIO_ARM = ARMS["full"]  # Rocchio on image embeddings + rejected-similarity penalty


# ---------------------------------------------------------------------------
class MemoText:
    """Text embeddings do not change between rounds; cache them."""

    def __init__(self, enc):
        self.enc, self.name, self.dim, self.cache = enc, enc.name, enc.dim, {}

    def encode_text(self, texts):
        missing = [t for t in texts if t not in self.cache]
        if missing:
            for t, v in zip(missing, self.enc.encode_text(missing)):
                self.cache[t] = v
        return np.stack([self.cache[t] for t in texts])

    def encode_images(self, paths):
        return self.enc.encode_images(paths)


class MemoBM25:
    def __init__(self, bm25):
        self.bm25, self.cache = bm25, {}

    def scores(self, text):
        if text not in self.cache:
            self.cache[text] = self.bm25.scores(text)
        return self.cache[text]

    def __getattr__(self, name):
        return getattr(self.bm25, name)


@dataclass(frozen=True)
class Condition:
    name: str
    tau: float = 0.5
    noise: float = 0.1
    utility: str = "design"  # | "metadata"
    needs: str = "flat"  # | "informed"
    reject: bool = True
    prior: str = "isotropic"  # | "kansei"
    strength: float = 1.0


MAIN = Condition("main")
CONDITIONS = [
    MAIN,
    replace(MAIN, name="tau0_argmax", tau=0.0),
    replace(MAIN, name="tau0.25", tau=0.25),
    replace(MAIN, name="tau1", tau=1.0),
    replace(MAIN, name="tau2", tau=2.0),
    replace(MAIN, name="noise0", noise=0.0),
    replace(MAIN, name="noise0.3", noise=0.3),
    replace(MAIN, name="no_reject", reject=False),
    replace(MAIN, name="needs_informed", needs="informed"),
    replace(MAIN, name="prior_kansei", prior="kansei"),
    replace(MAIN, name="metadata_utility", utility="metadata"),
    replace(MAIN, name="metadata_utility_tau0", utility="metadata", tau=0.0),
]

META_COLS = (
    [("color", "dark", DARK), ("color", "light", LIGHT), ("color", "bright", BRIGHT), ("color", "muted", MUTED)]
    + [("occasion", v, {v}) for v in ("Casual", "Formal", "Sports", "Ethnic")]
    + [("season", v, {v}) for v in ("Summer", "Fall", "Winter", "Spring")]
)


def metadata_features(items: pd.DataFrame) -> np.ndarray:
    return np.stack([items[col].isin(list(vals)).to_numpy(dtype=np.float64) for col, _, vals in META_COLS], axis=1)


@dataclass
class Method:
    name: str
    learner: object | None  # None → oracle
    rocchio: bool = False
    oracle: str | None = None  # "cand" | "w"


def make_methods(best: dict) -> list[Method]:
    return [
        Method("none", NoLearning()),
        Method("rocchio", NoLearning(), rocchio=True),
        Method("rulestep_prd", RuleStep(step_size=0.25)),
        Method("rulestep", RuleStep(**best.get("rulestep", {}))),
        Method("bayes", BayesLogistic(**best.get("bayes", {}))),
        Method("bayes_mnl", BayesLogistic(likelihood="mnl", **best.get("bayes_mnl", {}))),
        Method("thompson", ThompsonLogistic(**best.get("thompson", {}))),
        Method("linucb", LinUCB(**best.get("linucb", {}))),
        Method("bayes+rocchio", BayesLogistic(**best.get("bayes", {})), rocchio=True),
        Method("oracle_w", None, oracle="w"),
        Method("oracle_cand", None, oracle="cand"),
    ]


TUNE_GRID = {
    "rulestep": [dict(step_size=s) for s in (0.25, 0.5, 1.0, 2.0, 4.0)],
    "bayes": [dict(rationality=l, prior_sd=s) for l, s in itertools.product((0.25, 0.5, 1, 2, 4), (0.25, 0.5, 1.0, 2.0))],
    "bayes_mnl": [dict(rationality=l, prior_sd=s) for l, s in itertools.product((0.25, 0.5, 1, 2, 4), (0.25, 0.5, 1.0, 2.0))],
    "thompson": [dict(rationality=l, prior_sd=s, var_scale=v)
                 for l, s, v in itertools.product((0.5, 1, 2, 4), (0.5, 1.0, 2.0), (0.25, 1.0))],
    "linucb": [dict(alpha=a, reward=r) for a, r in itertools.product((0.0, 0.1, 0.3, 1.0), (0.5, 1.0, 2.0, 4.0))],
}
FAMILY = {"rulestep": RuleStep, "bayes": BayesLogistic, "thompson": ThompsonLogistic, "linucb": LinUCB,
          "bayes_mnl": lambda **kw: BayesLogistic(likelihood="mnl", **kw)}


# ---------------------------------------------------------------------------
class Sim:
    def __init__(self, engine: PreferenceEngine02, n_cand: int, k: int, rounds: int, seed: int):
        self.e, self.n_cand, self.k, self.rounds, self.seed = engine, n_cand, k, rounds, seed
        self.items = engine.catalog.items
        self.space = DesignSpace.from_kansei(engine.kansei)
        self.F = self.space.features(engine.design_matrix(LEARN_ARM))
        self.M = metadata_features(self.items)
        self._base: dict = {}
        self.ids = self.items["item_id"].astype(str).to_numpy()

    def build_users(self, n: int, offset: int = 0, min_pool: int = 30) -> list[dict]:
        qs = make_queries(self.items, n=100000, seed=0, paraphrasable_only=False)
        users = []
        for q in qs:
            c = HardConstraints(category=Slot(state=SlotState.VALUE, values=[q.category]),
                                gender=Slot(state=SlotState.VALUE, values=[q.gender]))
            pool = np.flatnonzero(filter_with_relaxation(self.items, c, self.k).mask)
            if len(pool) < min_pool:
                continue
            users.append(dict(q=q, constraints=c, pool=pool))
        users = users[offset:offset + n]
        it = self.items
        for uid, u in enumerate(users, start=offset):
            q, pool = u["q"], u["pool"]
            sub = (it["subcategory"].to_numpy()[pool] == q.subcategory)
            col = (it["color"].to_numpy()[pool] == q.color)
            full = sub & col & (it["gender"].to_numpy()[pool] == q.gender) & (it["occasion"].to_numpy()[pool] == q.occasion)
            u["rel"] = np.where(full, 3.0, np.where(sub & col, 2.0, np.where(sub, 1.0, 0.0)))
            u["attr_grades"] = {self.ids[p]: g for p, g in zip(pool, u["rel"]) if g > 0}
            rng = np.random.default_rng([self.seed, uid, 11])
            u["uid"] = uid
            u["p_star"] = rng.dirichlet(np.full(len(self.space.need_ids), 0.3))
            u["eta"] = rng.normal(size=self.space.dim)
            u["v_meta"] = rng.normal(size=self.M.shape[1])
            noisy = 0.5 * u["p_star"] + 0.5 * rng.dirichlet(np.ones(len(self.space.need_ids)))
            u["p_informed"] = noisy / noisy.sum()
            u["text"] = f"{q.gender} {q.subcategory}"
        return users

    # ------------------------------------------------------------------
    def request(self, user, probs: dict[str, float], fb: FeedbackState, rnd: int) -> Engine02Request:
        return Engine02Request(
            session_id=f"u{user['uid']}", round=rnd, retrieval_text=user["text"], constraints=user["constraints"],
            needs=[NeedProbability(need_id=n, prob=float(p)) for n, p in probs.items() if p > 0],
            feedback=fb,
            options=Engine02Options(top_k=self.n_cand, n_candidates=self.n_cand, explain_with_llm=False,
                                    counterfactual_check=False),
        )

    def candidates(self, user, probs, fb: FeedbackState | None, rnd: int, arm) -> tuple[np.ndarray, np.ndarray]:
        key = (user["uid"], tuple(sorted(probs.items())))
        if fb is None and key in self._base:
            return self._base[key]
        resp = self.e.run(self.request(user, probs, fb or FeedbackState(), rnd), arm)
        out = (np.array(self.e.catalog.positions([it.item_id for it in resp.items])),
               np.array([it.score for it in resp.items]))
        if fb is None:
            self._base[key] = out
        return out

    def probs(self, user, cond: Condition) -> dict[str, float]:
        need_ids = self.space.need_ids
        if cond.needs == "flat":
            return {n: 1.0 / len(need_ids) for n in need_ids}
        return {n: float(p) for n, p in zip(need_ids, user["p_informed"])}

    def utility(self, user, cond: Condition) -> tuple[np.ndarray, np.ndarray | None, float]:
        pool = user["pool"]
        if cond.utility == "design":
            w = user["p_star"] @ self.space.K + cond.noise * user["eta"]
            taste = self.F[pool] @ w
        else:
            w = None
            taste = self.M[pool] @ user["v_meta"]
        sd = taste.std() if taste.std() > 1e-12 else 1.0
        u = user["rel"] + cond.strength * (taste - taste.mean()) / sd
        return u, w, cond.strength / sd

    # ------------------------------------------------------------------
    def simulate(self, user, cond: Condition, method: Method) -> list[dict]:
        pool = user["pool"]
        u_pool, w_star, w_scale = self.utility(user, cond)
        u_cat = np.full(len(self.items), np.nan)
        u_cat[pool] = u_pool
        top10 = set(pool[np.argsort(-u_pool, kind="stable")[:10]].tolist())
        q99, q95, q80 = np.quantile(u_pool, [0.99, 0.95, 0.80])
        g_u = np.where(u_pool >= q99, 3.0, np.where(u_pool >= q95, 2.0, np.where(u_pool >= q80, 1.0, 0.0)))
        u_grades = {self.ids[p]: g for p, g in zip(pool, g_u) if g > 0}
        probs = self.probs(user, cond)
        beta0 = self.space.prior_mean(probs, LEARN_ARM.need_scale)
        prior_cov = None
        if cond.prior == "kansei" and isinstance(method.learner, BayesLogistic):
            prior_cov = self.space.prior_cov(method.learner.prior_sd, "kansei", LEARN_ARM.need_scale, probs)
        history: list[ChoiceRound] = []
        chosen_ids: list[str] = []
        rejected_ids: list[str] = []
        rows = []
        for r in range(1, self.rounds + 1):
            if method.rocchio and r > 1:
                fb = FeedbackState(chosen_item_ids=list(chosen_ids), rejected_item_ids=list(rejected_ids))
                cand, base = self.candidates(user, probs, fb, r, ROCCHIO_ARM)
            else:
                cand, base = self.candidates(user, probs, None, r, LEARN_ARM)
            rng = np.random.default_rng([self.seed, user["uid"], r, 3])
            if method.oracle == "cand":
                order = np.argsort(-u_cat[cand], kind="stable")
                w_hat = None
                d_used = np.zeros(self.space.dim)
            else:
                if method.oracle == "w":
                    if w_star is None:
                        return []
                    upd = PreferenceUpdate(delta=w_scale * w_star - beta0, mean=w_scale * w_star)
                elif isinstance(method.learner, BayesLogistic):
                    upd = method.learner.update(history, self.F, beta0, rng=rng, prior_cov=prior_cov)
                else:
                    upd = method.learner.update(history, self.F, beta0, rng=rng)
                s = rerank_candidates(base, self.F[cand], upd, LEARN_ARM.need_scale)
                order = np.argsort(-s, kind="stable")
                w_hat = upd.mean if upd.mean is not None else beta0 + upd.delta
                d_used = np.asarray(upd.delta, dtype=np.float64)
            slate = cand[order[: self.k]]
            slate_ids = [self.ids[p] for p in slate]
            cos = np.nan
            if w_star is not None and w_hat is not None and np.linalg.norm(w_hat) > 1e-12:
                cos = float(w_hat @ w_star / (np.linalg.norm(w_hat) * np.linalg.norm(w_star) + 1e-12))
            rows.append(dict(
                condition=cond.name, method=method.name, uid=user["uid"], round=r,
                util=float(np.mean(u_cat[slate])),
                util_gain=float(np.mean(u_cat[slate]) - u_pool.mean()),
                hit10_at5=float(any(int(p) in top10 for p in slate)),
                ceiling_hit=float(any(int(p) in top10 for p in cand)),
                ndcg_u=ndcg_at_k(slate_ids, u_grades, self.k),
                attr_ndcg=ndcg_at_k(slate_ids, user["attr_grades"], self.k),
                cos=cos, n_pool=len(pool),
                dmean_abs=float(np.abs(d_used).mean()), dmax_abs=float(np.abs(d_used).max()),
            ))
            # --- the simulated user reacts -------------------------------------------------
            us = u_cat[slate]
            if cond.tau > 0:
                gpos = np.searchsorted(pool, slate)
                gumbel = np.random.default_rng([self.seed, user["uid"], r, 7]).gumbel(size=len(pool))[gpos]
                ci = int(np.argmax(us / cond.tau + gumbel))
            else:
                ci = int(np.argmax(us))
            chosen = int(slate[ci])
            rejected = []
            wi = int(np.argmin(us))
            if cond.reject and wi != ci:
                rejected = [int(slate[wi])]
            history.append(ChoiceRound(shown=[int(p) for p in slate], chosen=chosen, rejected=rejected))
            chosen_ids.append(self.ids[chosen])
            rejected_ids += [self.ids[p] for p in rejected]
        self.last_history = history
        return rows


# ---------------------------------------------------------------------------
def paired_summary(df: pd.DataFrame, metric: str, rnd: int | str, baselines=("none", "rocchio")) -> pd.DataFrame:
    sub = df if rnd == "2-5" else df[df["round"] == rnd]
    if rnd == "2-5":
        sub = sub[sub["round"] >= 2]
    piv = sub.groupby(["method", "uid"])[metric].mean().unstack("method")
    rows = []
    for m in piv.columns:
        x = piv[m].to_numpy()
        ok = ~np.isnan(x)
        if not ok.any():
            continue
        lo, hi = bootstrap_ci(x[ok])
        row = dict(round=rnd, metric=metric, method=m, mean=float(np.nanmean(x)), ci_lo=lo, ci_hi=hi, n=int(ok.sum()))
        for b in baselines:
            if b in piv.columns and b != m:
                y = piv[b].to_numpy()
                both = ok & ~np.isnan(y)
                if both.sum() == 0:
                    continue
                d = x[both] - y[both]
                dlo, dhi = bootstrap_ci(d)
                row[f"diff_vs_{b}"] = float(d.mean())
                row[f"diff_ci_{b}"] = f"[{dlo:.3f}, {dhi:.3f}]"
                row[f"p_vs_{b}"] = paired_permutation_test(x[both], y[both])
        rows.append(row)
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default="data/catalog/kagl")
    ap.add_argument("--encoder", default="marqo-fashionSigLIP")
    ap.add_argument("--device", default="auto")
    ap.add_argument("--cache-dir", default=None)
    ap.add_argument("--stage", choices=["tune", "main"], default="main")
    ap.add_argument("--best", default=None, help="best.json from --stage tune")
    ap.add_argument("--users", type=int, default=200)
    ap.add_argument("--tune-users", type=int, default=60)
    ap.add_argument("--rounds", type=int, default=5)
    ap.add_argument("--n-candidates", type=int, default=100)
    ap.add_argument("--conditions", default="all")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    cat = Catalog.load(ROOT / args.catalog)
    if args.encoder == "hash":
        from engine02.encoders import HashEncoder

        enc = HashEncoder(dim=128, captions={Path(p).name: t for p, t in zip(cat.items["image_path"], cat.texts())})
    else:
        from engine02.models import TorchEncoder

        enc = TorchEncoder(args.encoder, device=args.device)
    engine = PreferenceEngine02(cat, MemoText(enc), cache_dir=args.cache_dir)
    engine.bm25 = MemoBM25(engine.bm25)
    sim = Sim(engine, args.n_candidates, 5, args.rounds, args.seed)
    print(json.dumps(dict(catalog=args.catalog, n_items=len(cat), setup_s=round(time.perf_counter() - t0, 1),
                          elements=sim.space.element_ids)), flush=True)

    if args.stage == "tune":
        # tuning users are disjoint (by list position) from evaluation users; only the main condition
        users = sim.build_users(args.tune_users, offset=args.users)
        print(f"tune users: {len(users)}", flush=True)
        rows = []
        for fam, grid in TUNE_GRID.items():
            for cfg in grid:
                m = Method(f"{fam}|{json.dumps(cfg, sort_keys=True)}", FAMILY[fam](**cfg))
                for u in users:
                    rows += sim.simulate(u, MAIN, m)
            print(f"tuned {fam} ({time.perf_counter() - t0:.0f}s)", flush=True)
        for m in (Method("none", NoLearning()),):
            for u in users:
                rows += sim.simulate(u, MAIN, m)
        df = pd.DataFrame(rows)
        df.to_csv(out / "tune_rounds.csv", index=False)
        score = df[df["round"] >= 2].groupby("method")["util"].mean().sort_values(ascending=False)
        score.to_csv(out / "tune_scores.csv")
        best = {}
        for fam in TUNE_GRID:
            fs = score[[i for i in score.index if i.startswith(fam + "|")]]
            best[fam] = json.loads(fs.index[0].split("|", 1)[1])
        (out / "best.json").write_text(json.dumps(best, indent=2))
        print(score.head(30).to_string(), flush=True)
        print(json.dumps(best), flush=True)
        return

    best = json.loads(Path(args.best).read_text()) if args.best else {}
    methods = make_methods(best)
    users = sim.build_users(args.users, offset=0)
    conds = CONDITIONS if args.conditions == "all" else [c for c in CONDITIONS if c.name in args.conditions.split(",")]
    meta = dict(n_users=len(users), n_candidates=args.n_candidates, rounds=args.rounds, best=best,
                conditions=[asdict(c) for c in conds], pool_size_median=float(np.median([len(u["pool"]) for u in users])))
    (out / "meta.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta), flush=True)
    all_rows = []
    for cond in conds:
        rows = []
        for m in methods:
            for u in users:
                rows += sim.simulate(u, cond, m)
        df = pd.DataFrame(rows)
        df.to_csv(out / f"rounds_{cond.name}.csv", index=False)
        all_rows.append(df)
        print(f"{cond.name} done ({time.perf_counter() - t0:.0f}s)", flush=True)
        print(df[df["round"] == args.rounds].groupby("method")[["util", "hit10_at5", "ndcg_u", "attr_ndcg", "cos"]]
              .mean().round(3).to_string(), flush=True)
    df = pd.concat(all_rows)
    summ = []
    for cond, sub in df.groupby("condition"):
        for metric in ("util", "hit10_at5", "ndcg_u", "attr_ndcg", "cos"):
            for rnd in (args.rounds, "2-5"):
                s = paired_summary(sub, metric, rnd)
                s.insert(0, "condition", cond)
                summ.append(s)
    pd.concat(summ).to_csv(out / "summary.csv", index=False)
    curves = df.groupby(["condition", "method", "round"])[["util", "hit10_at5", "ndcg_u", "attr_ndcg", "cos"]].mean()
    curves.round(4).to_csv(out / "curves.csv")
    print(f"total {time.perf_counter() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
