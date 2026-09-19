"""Offline evaluation tasks for ENGINE 02 that need no LLM and no human labels.

All ground truth comes from catalog metadata (KAGL: subcategory, color, usage, gender),
which the image encoder never sees. These are *proxy* evaluations — report them as such.

T1 retrieval quality   : attribute-grounded queries, lexical vs paraphrased wording
T2 constraint handling : satisfaction@k and relaxation rate with hard filters on
T3 concept validity    : AUROC of c(i,d) against metadata-derived labels (M4 arms)
T4 reason faithfulness : coverage / comprehensiveness / sufficiency per reason mode
T5 feedback loop       : rule-based simulated user, success rate SR@t per round
"""

from __future__ import annotations

import random
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..config import ARMS
from ..contracts import (
    Engine02Options,
    Engine02Request,
    FeedbackState,
    HardConstraints,
    NeedProbability,
    Slot,
    SlotState,
)
from ..fusion import zscore
from ..pipeline import Engine02
from .metrics import bootstrap_ci, mrr, ndcg_at_k, paired_permutation_test

APPAREL = {"top", "bottom", "outerwear", "dress", "shoes", "bag"}

SUBCAT_PARAPHRASE = {
    "Tshirts": "tee", "Shirts": "button-up", "Casual Shoes": "everyday sneakers",
    "Sports Shoes": "running trainers", "Trousers": "pants", "Handbags": "purse",
    "Formal Shoes": "dress shoes", "Sandals": "open-toe summer footwear", "Heels": "high-heeled pumps",
    "Kurtas": "long tunic", "Tops": "blouse", "Flip Flops": "slippers", "Jackets": "outer layer",
    "Sweatshirts": "crewneck pullover", "Shorts": "short pants", "Backpacks": "rucksack",
    "Sweaters": "knit jumper", "Track Pants": "joggers", "Flats": "ballet pumps", "Clutches": "evening purse",
}
COLOR_PARAPHRASE = {
    "Black": "jet", "White": "snow", "Blue": "azure", "Brown": "chocolate", "Grey": "ash",
    "Red": "crimson", "Green": "emerald", "Purple": "violet", "Pink": "blush", "Navy Blue": "midnight",
    "Maroon": "wine", "Yellow": "lemon", "Beige": "sand", "Olive": "army", "Orange": "tangerine",
}
GENDER_PARAPHRASE = {"Men": "guy's", "Women": "lady's", "Unisex": "anyone's", "Boys": "kid's", "Girls": "kid's"}
OCCASION_PARAPHRASE = {"Casual": "everyday", "Sports": "workout", "Formal": "office", "Ethnic": "traditional"}


def _slot(values):
    return Slot(state=SlotState.VALUE, values=list(values))


@dataclass
class Query:
    qid: str
    gender: str
    color: str
    subcategory: str
    category: str
    occasion: str

    def text(self, paraphrase: bool) -> str:
        if not paraphrase:
            return f"{self.gender} {self.color} {self.subcategory} for {self.occasion}"
        return (
            f"{GENDER_PARAPHRASE.get(self.gender, self.gender)} "
            f"{COLOR_PARAPHRASE.get(self.color, self.color)} "
            f"{SUBCAT_PARAPHRASE.get(self.subcategory, self.subcategory)} "
            f"for {OCCASION_PARAPHRASE.get(self.occasion, self.occasion)}"
        )

    def grades(self, items: pd.DataFrame) -> dict[str, float]:
        sub = items["subcategory"] == self.subcategory
        col = items["color"] == self.color
        full = sub & col & (items["gender"] == self.gender) & (items["occasion"] == self.occasion)
        g = np.where(full, 3, np.where(sub & col, 2, np.where(sub, 1, 0)))
        return {str(i): float(v) for i, v in zip(items["item_id"], g) if v > 0}


def make_queries(items: pd.DataFrame, n: int = 60, seed: int = 0, paraphrasable_only: bool = True) -> list[Query]:
    df = items[items["category"].isin(APPAREL)].dropna(subset=["gender", "color", "subcategory", "occasion"])
    if paraphrasable_only:
        df = df[df["subcategory"].isin(SUBCAT_PARAPHRASE) & df["color"].isin(COLOR_PARAPHRASE)]
    groups = df.groupby(["gender", "color", "subcategory", "category", "occasion"]).size()
    groups = groups[groups >= 2].reset_index()
    rng = random.Random(seed)
    idx = list(range(len(groups)))
    rng.shuffle(idx)
    out = []
    for i in idx[:n]:
        r = groups.iloc[i]
        out.append(Query(f"q{i}", r.gender, r.color, r.subcategory, r.category, r.occasion))
    return out


# ---------------------------------------------------------------------------
def t1_retrieval(engine: Engine02, queries: list[Query], arms: list[str], k: int = 10) -> pd.DataFrame:
    rows = []
    items = engine.catalog.items
    for q in queries:
        grades = q.grades(items)
        relevant3 = {i for i, g in grades.items() if g >= 3}
        for paraphrase in (False, True):
            for arm in arms:
                req = Engine02Request(
                    session_id=q.qid, retrieval_text=q.text(paraphrase),
                    options=Engine02Options(top_k=k, n_candidates=100, explain_with_llm=False, counterfactual_check=False),
                )
                resp = engine.run(req, arm)
                ids = [it.item_id for it in resp.items]
                rows.append(dict(
                    qid=q.qid, wording="paraphrase" if paraphrase else "lexical", arm=arm,
                    ndcg5=ndcg_at_k(ids, grades, 5), ndcg10=ndcg_at_k(ids, grades, 10),
                    mrr_exact=mrr(ids, relevant3), latency_ms=sum(resp.timings_ms.values()),
                ))
    return pd.DataFrame(rows)


def summarize_paired(df: pd.DataFrame, metric: str, baseline: str, by: str = "wording") -> pd.DataFrame:
    rows = []
    for w, sub in df.groupby(by):
        piv = sub.pivot(index="qid", columns="arm", values=metric)
        for arm in piv.columns:
            lo, hi = bootstrap_ci(piv[arm].to_numpy())
            p = paired_permutation_test(piv[arm].to_numpy(), piv[baseline].to_numpy()) if arm != baseline else float("nan")
            rows.append({by: w, "arm": arm, metric: piv[arm].mean(), "ci95_lo": lo, "ci95_hi": hi,
                         f"p_vs_{baseline}": p, "n_queries": len(piv)})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
def t2_constraints(engine: Engine02, queries: list[Query], arm: str = "full", k: int = 5) -> pd.DataFrame:
    rows = []
    for q in queries:
        c = HardConstraints(category=_slot([q.category]), color=_slot([q.color]), gender=_slot([q.gender]),
                            occasion=_slot([q.occasion]))
        req = Engine02Request(session_id=q.qid, retrieval_text=q.text(False), constraints=c,
                              options=Engine02Options(top_k=k, explain_with_llm=False))
        resp = engine.run(req, arm)
        rows.append(dict(qid=q.qid, arm=arm, satisfaction=resp.metrics.hard_constraint_satisfaction,
                         n_after_filter=resp.constraint_report.n_after_filter,
                         relaxed=";".join(resp.constraint_report.relaxed), n_items=len(resp.items)))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
DARK = {"Black", "Navy Blue", "Charcoal", "Maroon", "Coffee Brown", "Burgundy"}
LIGHT = {"White", "Beige", "Cream", "Off White", "Peach", "Lavender", "Yellow", "Skin"}
BRIGHT = {"Red", "Yellow", "Orange", "Pink", "Green", "Magenta", "Turquoise Blue", "Teal"}
MUTED = {"Black", "White", "Grey", "Beige", "Navy Blue", "Charcoal", "Cream", "Off White", "Grey Melange", "Khaki", "Tan"}


def concept_labels(items: pd.DataFrame, allow_predicted: bool = False) -> dict[str, np.ndarray]:
    """Metadata-derived binary labels: 1 / 0 / -1 (= not labelled).

    On a filled catalog `occasion` and `color` may themselves be model predictions, and scoring a
    model against its own output is circular (the VLM filled `occasion`, the probe on Marqo
    embeddings filled `color`). So predicted values are dropped from the ground truth unless the
    caller explicitly asks for them.
    """
    from engine02.attribute_fill import is_predicted

    apparel = items["category"].isin(APPAREL).to_numpy()
    use = items["occasion"].to_numpy().copy()
    col = items["color"].to_numpy().copy()
    if not allow_predicted and "attr_source" in items.columns:
        use[is_predicted(items, "occasion")] = None
        col[is_predicted(items, "color")] = None

    def lab(pos_mask, neg_mask):
        y = np.full(len(items), -1)
        y[pos_mask & apparel] = 1
        y[neg_mask & apparel] = 0
        return y

    return {
        "formal_style": lab(use == "Formal", np.isin(use, ["Casual", "Sports"])),
        "casual_style": lab(np.isin(use, ["Casual", "Sports"]), use == "Formal"),
        "dark_tone": lab(np.isin(col, list(DARK)), np.isin(col, list(LIGHT))),
        "bright_color": lab(np.isin(col, list(BRIGHT)), np.isin(col, list(MUTED))),
    }


def auroc(scores: np.ndarray, y: np.ndarray) -> float:
    m = y >= 0
    s, t = scores[m], y[m]
    npos, nneg = int(t.sum()), int((1 - t).sum())
    if npos == 0 or nneg == 0:
        return float("nan")
    ranks = pd.Series(s).rank().to_numpy()
    return float((ranks[t == 1].sum() - npos * (npos + 1) / 2) / (npos * nneg))


def t3_concepts(engine: Engine02, arm_names: list[str], n_boot: int = 1000, seed: int = 0) -> pd.DataFrame:
    labels = concept_labels(engine.catalog.items)
    ids = engine.kansei.element_ids
    rng = np.random.default_rng(seed)
    rows = []
    for name in arm_names:
        c = engine.design_matrix(ARMS[name])
        for el, y in labels.items():
            j = ids.index(el)
            score = c[:, j]
            a = auroc(score, y)
            m = np.flatnonzero(y >= 0)
            boots = []
            for _ in range(n_boot):
                b = rng.choice(m, size=len(m), replace=True)
                boots.append(auroc(score[b], y[b]))
            rows.append(dict(arm=name, concept_mode=ARMS[name].concept_mode, dn=ARMS[name].concept_dn,
                             element=el, auroc=a, ci95_lo=float(np.nanquantile(boots, 0.025)),
                             ci95_hi=float(np.nanquantile(boots, 0.975)), n_pos=int((y == 1).sum()),
                             n_neg=int((y == 0).sum())))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
def random_needs(rng: random.Random, need_ids: list[str], n: int = 3) -> list[NeedProbability]:
    chosen = rng.sample(need_ids, n)
    w = np.array([rng.random() for _ in chosen])
    w = w / w.sum()
    return [NeedProbability(need_id=i, prob=float(p)) for i, p in zip(chosen, w)]


def t4_faithfulness(engine: Engine02, queries: list[Query], modes: list[str], k: int = 5, seed: int = 0) -> pd.DataFrame:
    """For each card: remove the cited terms (comprehensiveness) or keep only them
    (sufficiency) and check the item against the full score of the rank k+1 item.
    Compared with a random set of the same size drawn from the item's positive terms."""
    rng = random.Random(seed)
    rows = []
    for q in queries:
        needs = random_needs(rng, engine.kansei.need_ids)
        c = HardConstraints(category=_slot([q.category]), gender=_slot([q.gender]))
        for mode in modes:
            req = Engine02Request(session_id=q.qid, retrieval_text=q.text(False), constraints=c, needs=needs,
                                  options=Engine02Options(top_k=k, explain_with_llm=False))
            resp = engine.run(req, mode)
            for it in resp.items:
                contrib = np.array([cb.contribution for cb in it.contributions])
                cited = np.array([cb.cited for cb in it.contributions])
                cut_score = it.score - it.margin_vs_cutoff if it.margin_vs_cutoff is not None else None
                row = dict(qid=q.qid, arm=mode, rank=it.rank, has_reason=bool(cited.any()), n_cited=int(cited.sum()))
                if cut_score is not None and cited.any():
                    row["comprehensive"] = bool(it.score - contrib[cited].sum() <= cut_score)
                    row["sufficient"] = bool(contrib[cited].sum() > cut_score)
                    pos_idx = np.flatnonzero(contrib > 0)
                    rnd = np.array(rng.sample(list(pos_idx), min(int(cited.sum()), len(pos_idx))), dtype=int)
                    row["rand_comprehensive"] = bool(it.score - contrib[rnd].sum() <= cut_score)
                    row["rand_sufficient"] = bool(contrib[rnd].sum() > cut_score)
                rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
def _match(items: pd.DataFrame, pos: int, target: pd.Series) -> int:
    r = items.iloc[pos]
    return int(r["subcategory"] == target["subcategory"]) + int(r["color"] == target["color"]) + int(
        r["occasion"] == target["occasion"]
    )


def t5_feedback(engine: Engine02, arms: dict[str, dict], n_targets: int = 100, rounds: int = 4, k: int = 5,
                seed: int = 0) -> pd.DataFrame:
    """Rule-based simulated user with a hidden target item.

    Round 1 query is vague ("{gender} {category}"). After each round the user
    (a) chooses the shown item that matches the target on most attributes (Rocchio +),
    (b) rejects shown items that match on none (penalty / Rocchio −),
    (c) reveals one more attribute in order subcategory → color → occasion as a critique.
    Arm options: use_choice, use_critique (False/False = no feedback, rerun same query).
    """
    items = engine.catalog.items
    rng = random.Random(seed)
    cand = items[items["category"].isin({"top", "bottom", "shoes", "bag"})].dropna(
        subset=["gender", "color", "subcategory", "occasion"])
    targets = rng.sample(list(cand.index), min(n_targets, len(cand)))
    rows = []
    for tpos in targets:
        target = items.loc[tpos]
        tid = str(target["item_id"])
        for arm_name, opts in arms.items():
            fb = FeedbackState()
            reveal: list[str] = []
            success_round = None
            for r in range(1, rounds + 1):
                words = [target["gender"]]
                c = HardConstraints(category=_slot([target["category"]]), gender=_slot([target["gender"]]))
                for attr in reveal:
                    words.append(str(target[attr]))
                    if attr in ("color", "occasion"):
                        setattr(c, attr, _slot([target[attr]]))
                if "subcategory" not in reveal:
                    words.append(target["category"])
                req = Engine02Request(session_id=f"t{tpos}", round=r, retrieval_text=" ".join(words),
                                      constraints=c, feedback=fb,
                                      options=Engine02Options(top_k=k, explain_with_llm=False,
                                                              counterfactual_check=False))
                resp = engine.run(req, opts["arm"])
                ids = [it.item_id for it in resp.items]
                if tid in ids:
                    success_round = r
                    break
                shown_pos = engine.catalog.positions(ids)
                if opts.get("use_choice"):
                    scores = [_match(items, p, target) for p in shown_pos]
                    if scores and max(scores) > 0:
                        best = ids[int(np.argmax(scores))]
                        fb.chosen_item_ids = list(dict.fromkeys(fb.chosen_item_ids + [best]))
                    fb.rejected_item_ids = list(dict.fromkeys(
                        fb.rejected_item_ids + [i for i, s in zip(ids, scores) if s == 0]))
                if opts.get("use_critique"):
                    for attr in ("subcategory", "color", "occasion"):
                        if attr not in reveal:
                            reveal.append(attr)
                            break
            for r in range(1, rounds + 1):
                rows.append(dict(target=tid, arm=arm_name, round=r,
                                 success=bool(success_round is not None and success_round <= r)))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
def t6_need_tradeoff(engine: Engine02, queries: list[Query], scales=(0, 0.5, 1, 2, 4, 8), k: int = 5,
                     seed: int = 0, base_arm: str = "full") -> pd.DataFrame:
    """Sponsor's difficulty: keep quality under constraints while honouring hidden needs.

    For each query draw random need probabilities, then sweep γ (need_scale):
    - ndcg5: attribute-grounded relevance (as T1, lexical wording, hard category+gender filter)
    - need_alignment: mean over top-k of Σ_d β_d(γ=1)·c(i,d) — how well shown items express the needs
    - changed: share of top-k not present at γ=0 (how much needs actually move the result)
    """
    from dataclasses import replace

    rng = random.Random(seed)
    base = ARMS[base_arm]
    c_mat = engine.design_matrix(base)
    rows = []
    for q in queries:
        needs = random_needs(rng, engine.kansei.need_ids)
        probs = {n.need_id: n.prob for n in needs}
        beta = engine.kansei.beta(probs, {})[0]
        grades = q.grades(engine.catalog.items)
        c = HardConstraints(category=_slot([q.category]), gender=_slot([q.gender]))
        top0 = None
        for g in scales:
            arm = replace(base, name=f"{base_arm}_g{g}", need_scale=float(g))
            req = Engine02Request(session_id=q.qid, retrieval_text=q.text(False), constraints=c, needs=needs,
                                  options=Engine02Options(top_k=k, explain_with_llm=False, counterfactual_check=False))
            resp = engine.run(req, arm)
            ids = [it.item_id for it in resp.items]
            pos = engine.catalog.positions(ids)
            align = float(np.mean(c_mat[pos] @ beta)) if pos else float("nan")
            if top0 is None:
                top0 = set(ids)
            rows.append(dict(qid=q.qid, gamma=g, ndcg5=ndcg_at_k(ids, grades, k), need_alignment=align,
                             changed=len(set(ids) - top0) / max(1, len(ids))))
    return pd.DataFrame(rows)
