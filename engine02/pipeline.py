"""ENGINE 02 main entry: Engine02Request → Engine02Response.

filter (with relaxation) → candidate retrieval (BM25 / dense / RRF / convex)
→ additive rerank (dense, bm25, design β·c, compat, trend, penalty, optional reranker)
→ optional MMR → reason selection (necessity / contrastive / sufficient)
→ template reasons → optional fact-checked LLM paraphrase.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Protocol

import numpy as np

from . import fusion
from .catalog import Catalog
from .compat import CategoryCooccurrence, compat_scores
from .concepts import design_scores
from .config import ARMS, ArmConfig
from .constraints import filter_with_relaxation, satisfies
from .contracts import (
    ConstraintReport,
    Contribution,
    Engine02Request,
    Engine02Response,
    RankedItem,
    RoundMetrics,
)
from .encoders import Encoder, cached_image_embeddings, l2n
from .explain import explain, template_reasons
from .kansei import KanseiTable
from .rerank import Term, additive_score, counterfactual_ranks, cutoff_explanations
from .sparse import BM25Index


class CrossReranker(Protocol):
    name: str

    def score(self, query: str, item_positions: list[int]) -> np.ndarray: ...


def build_retrieval_text(req: Engine02Request) -> str:
    if req.retrieval_text:
        return req.retrieval_text
    c = req.constraints
    parts: list[str] = []
    for slot in (c.gender, c.color, c.style_keywords, c.season):
        if slot.state.value in ("value", "inferred"):
            parts += slot.values
    parts += c.category.values or ["clothing"]
    if c.occasion.values:
        parts += ["for"] + c.occasion.values
    return " ".join(parts)


def _stats(x: np.ndarray) -> tuple[float, float]:
    x = np.asarray(x, dtype=np.float64)
    return (float(x.mean()), float(x.std())) if x.size else (0.0, 1.0)


class Engine02:
    def __init__(
        self,
        catalog: Catalog,
        encoder: Encoder,
        kansei: KanseiTable | None = None,
        cooccurrence: CategoryCooccurrence | None = None,
        cache_dir: str | Path | None = None,
        llm: Callable[[str], str] | None = None,
        cross_reranker: CrossReranker | None = None,
    ):
        t0 = time.perf_counter()
        self.catalog = catalog
        self.encoder = encoder
        self.kansei = kansei or KanseiTable.load()
        self.cooc = cooccurrence
        self.llm = llm
        self.cross_reranker = cross_reranker
        self.cache = Path(cache_dir) if cache_dir else catalog.root / "index"
        self._safe = encoder.name.replace("/", "__")
        self.image_emb = cached_image_embeddings(encoder, catalog.image_paths(), self.cache / f"img_{self._safe}.npy")
        self._c: dict[tuple, np.ndarray] = {}
        self.bm25 = BM25Index(catalog.texts())
        self.trend_keywords: list[str] = []
        self.vocabulary = list(self.kansei.needs.values()) + [e.label for e in self.kansei.elements]
        self.init_ms = (time.perf_counter() - t0) * 1000

    def set_trends(self, keywords: list[str]) -> None:
        self.trend_keywords = keywords

    def design_matrix(self, arm: ArmConfig) -> np.ndarray:
        key = (arm.concept_mode, arm.concept_dn, arm.concept_applicability)
        if key in self._c:
            return self._c[key]
        f = self.cache / (
            f"design_{self._safe}_{self.kansei.version}_{arm.concept_mode}"
            f"_dn{int(arm.concept_dn)}_mask{int(arm.concept_applicability)}.npy"
        )
        shape = (len(self.catalog), len(self.kansei.elements))
        if arm.concept_mode == "vlm":
            from .concepts import vlm_design_scores

            files = sorted(self.catalog.root.glob("vlm_attributes_*.parquet"))
            if not files:
                raise FileNotFoundError("run scripts/vlm_tag_attributes.py first (concept_mode='vlm')")
            c = vlm_design_scores(self.catalog.items["item_id"].astype(str).tolist(), self.kansei, files[-1])
        elif f.exists() and np.load(f).shape == shape:
            c = np.load(f)
        else:
            cats = self.catalog.items["category"].tolist() if arm.concept_applicability else None
            c = design_scores(self.encoder, self.image_emb, self.kansei, arm.concept_mode, cats, arm.concept_dn)
            f.parent.mkdir(parents=True, exist_ok=True)
            np.save(f, c)
        self._c[key] = c
        return c

    # ------------------------------------------------------------------
    def query_embedding(self, req: Engine02Request, arm: ArmConfig, text: str) -> np.ndarray:
        q = self.encoder.encode_text([text])[0].astype(np.float64)
        fb = req.feedback
        if arm.use_rocchio:
            pos = self.catalog.positions(fb.chosen_item_ids)
            neg = self.catalog.positions(fb.rejected_item_ids)
            if pos:
                q = q + arm.rocchio_a * self.image_emb[pos].mean(axis=0)
            if neg:
                q = q - arm.rocchio_b * self.image_emb[neg].mean(axis=0)
        if arm.concept_image_weight > 0 and fb.concept_image_embedding:
            ci = np.asarray(fb.concept_image_embedding, dtype=np.float64)
            q = (1 - arm.concept_image_weight) * l2n(q) + arm.concept_image_weight * l2n(ci)
        return l2n(q).astype(np.float64)

    def run(self, req: Engine02Request, arm: ArmConfig | str | None = None) -> Engine02Response:
        arm = ARMS[arm] if isinstance(arm, str) else (arm or ARMS[req.options.arm])
        timings: dict[str, float] = {}
        t = time.perf_counter()

        def lap(name: str) -> None:
            nonlocal t
            now = time.perf_counter()
            timings[name] = round((now - t) * 1000, 2)
            t = now

        items = self.catalog.items
        k = req.options.top_k
        excluded = self.catalog.positions(req.feedback.excluded_item_ids)
        fr = filter_with_relaxation(items, req.constraints, max(arm.min_results, k), excluded)
        pool = np.flatnonzero(fr.mask)
        lap("filter")

        text = build_retrieval_text(req)
        q = self.query_embedding(req, arm, text)
        dense_all = self.image_emb[pool] @ q
        bm25_all = self.bm25.scores(text)[pool]
        lap("retrieve")

        if arm.candidate_fusion == "bm25":
            fused = bm25_all
        elif arm.candidate_fusion == "dense":
            fused = dense_all
        elif arm.candidate_fusion == "convex":
            fused = fusion.convex(dense_all, bm25_all, arm.convex_alpha, arm.convex_norm)
        else:
            fused = fusion.rrf([dense_all, bm25_all], k=arm.rrf_k, depth=arm.rrf_depth)
        n_cand = min(req.options.n_candidates, len(pool))
        top = np.argsort(-fused, kind="stable")[:n_cand]
        cand = pool[top]
        lap("fuse")

        terms = self._terms(req, arm, pool, cand, dense_all, bm25_all, top, text)
        sc = additive_score(terms)
        order = sc.order()
        if arm.use_mmr and len(order) > 1:
            depth = min(len(order), max(4 * k, 20))
            sel = fusion.mmr(sc.scores[order[:depth]], self.image_emb[cand[order[:depth]]], k, arm.mmr_lambda)
            head = order[:depth][sel]
            order = np.concatenate([head, np.setdiff1d(order, head, assume_unique=True)])
        shown = [int(p) for p in order[:k]]
        lap("rerank")

        do_cf = arm.counterfactual and req.options.counterfactual_check
        cf = counterfactual_ranks(sc, shown) if do_cf else {}
        cut = cutoff_explanations(sc, order, k)
        lap("counterfactual")

        probs = {n.need_id: n.prob for n in req.needs}
        el_labels = {e.id: e.label for e in self.kansei.elements}
        c_mat = self.design_matrix(arm)
        out_items: list[RankedItem] = []
        for rank, p in enumerate(shown, start=1):
            pos = int(cand[p])
            ce = cut[p]
            contribs = []
            for j, term in enumerate(sc.terms):
                cval = float(sc.contrib[p, j])
                shares = {}
                if term.group == "design":
                    shares = {n: v * float(sc.norm[p, j]) for n, v in term.need_shares_per_unit.items()}
                rw = cf[p][j] if p in cf else None
                necessary = (rw > k) if rw is not None else None
                sufficient = j in ce.sufficient
                if arm.reason_mode == "necessity":
                    cited = bool(necessary) if do_cf else False
                elif arm.reason_mode == "contrastive":
                    cited = ce.diffs[j] > 0 and ce.margin - ce.diffs[j] < 0
                else:
                    cited = sufficient
                contribs.append(
                    Contribution(
                        term=term.name,
                        group=term.group,
                        raw=float(term.raw[p]),
                        normalized=float(sc.norm[p, j]),
                        weight=float(term.weight),
                        contribution=cval,
                        need_shares=shares,
                        rank_without=rw,
                        necessary=necessary,
                        diff_vs_cutoff=float(ce.diffs[j]),
                        sufficient=sufficient,
                        cited=bool(cited and cval > 0),
                    )
                )
            # display cap: the minimal sufficient set is shown whole (trimming it would break
            # the sufficiency guarantee); other modes show at most 3 reasons
            cap = None if arm.reason_mode == "sufficient" else 3
            if cap is not None:
                keep = sorted((cb for cb in contribs if cb.cited), key=lambda cb: -cb.contribution)[:cap]
                keep_ids = {id(cb) for cb in keep}
                for cb in contribs:
                    cb.cited = id(cb) in keep_ids
            need_contrib: dict[str, float] = {}
            for cb in contribs:
                for n, v in cb.need_shares.items():
                    need_contrib[n] = need_contrib.get(n, 0.0) + v
            reasons, facts = template_reasons(contribs, el_labels, self.kansei.needs, fr.relaxed)
            use_llm = self.llm if req.options.explain_with_llm else None
            text_expl, src = explain(reasons, facts, self.vocabulary, use_llm)
            price = self.catalog.attr(pos, "price")
            out_items.append(
                RankedItem(
                    item_id=str(items.at[pos, "item_id"]),
                    rank=rank,
                    title=str(items.at[pos, "title"]),
                    image_path=str(items.at[pos, "image_path"]),
                    category=self.catalog.attr(pos, "category"),
                    color=self.catalog.attr(pos, "color"),
                    price=float(price) if price is not None else None,
                    score=float(sc.scores[p]),
                    contributions=contribs,
                    need_contributions=need_contrib,
                    design_scores={e.id: float(c_mat[pos, j]) for j, e in enumerate(self.kansei.elements)},
                    margin_vs_cutoff=ce.margin if ce.cutoff_position is not None else None,
                    reason_mode=arm.reason_mode,
                    reasons=reasons,
                    explanation=text_expl,
                    explanation_source=src,
                )
            )
        lap("explain")

        shown_pos = [int(cand[p]) for p in shown]
        return Engine02Response(
            session_id=req.session_id,
            round=req.round,
            arm=arm.name,
            items=out_items,
            constraint_report=ConstraintReport(
                applied=fr.applied, relaxed=fr.relaxed, n_catalog=len(items), n_after_filter=int(len(pool))
            ),
            metrics=self._metrics(req, shown_pos),
            kansei_version=self.kansei.version,
            encoder=self.encoder.name,
            query_embedding=[float(x) for x in q],
            timings_ms=timings,
        )

    # ------------------------------------------------------------------
    def _terms(self, req, arm: ArmConfig, pool, cand, dense_all, bm25_all, top, text) -> list[Term]:
        dense, bm25 = dense_all[top], bm25_all[top]
        if not arm.additive_rerank:
            if arm.candidate_fusion == "rrf":
                d = (1.0 / (arm.rrf_k + fusion.ranks_desc(dense_all)))[top]
                b = (1.0 / (arm.rrf_k + fusion.ranks_desc(bm25_all)))[top]
                return [Term("dense", "dense", d, 1.0, normalize=False), Term("bm25", "bm25", b, 1.0, normalize=False)]
            if arm.candidate_fusion == "convex":
                f = fusion.minmax if arm.convex_norm == "minmax" else fusion.zscore
                return [
                    Term("dense", "dense", f(dense_all)[top], arm.convex_alpha, normalize=False),
                    Term("bm25", "bm25", f(bm25_all)[top], 1 - arm.convex_alpha, normalize=False),
                ]
            single = dense if arm.candidate_fusion == "dense" else bm25
            return [Term(arm.candidate_fusion, arm.candidate_fusion, single, 1.0, normalize=False)]

        pool_scope = arm.norm_scope == "pool"
        terms = [
            Term("dense", "dense", dense, arm.w_dense, stats=_stats(dense_all) if pool_scope else None),
            Term("bm25", "bm25", bm25, arm.w_bm25, stats=_stats(bm25_all) if pool_scope else None),
        ]
        if arm.use_design and len(self.kansei.elements):
            c_mat = self.design_matrix(arm)
            probs = {n.need_id: n.prob for n in req.needs}
            beta_needs, beta_fb = self.kansei.beta(probs, req.feedback.design_adjust_steps)
            for j, el in enumerate(self.kansei.elements):
                w = float(beta_needs[j] + beta_fb[j])
                if abs(w) < 1e-9:
                    continue
                per_unit = {}
                for i, n in enumerate(self.kansei.need_ids):
                    v = probs.get(n, 0.0) * self.kansei.K[i, j]
                    if abs(v) > 1e-9:
                        per_unit[n] = float(v)
                if abs(beta_fb[j]) > 1e-9:
                    per_unit["feedback_adjust"] = float(beta_fb[j])
                # c(i,d) is already z-scored over the whole catalog → no re-normalisation in pool scope
                terms.append(Term(f"design:{el.id}", "design", c_mat[cand, j], w, per_unit, normalize=not pool_scope))
        if arm.use_compat and req.feedback.anchor_item_ids:
            anchors = self.catalog.positions(req.feedback.anchor_item_ids)
            cs = compat_scores(
                [self.catalog.attr(int(p), "category") for p in cand],
                [self.catalog.attr(a, "category") for a in anchors],
                self.cooc,
            )
            if cs is not None:  # NPMI is already on a fixed [-1, 1] scale
                terms.append(Term("compat", "compat", cs, arm.w_compat, normalize=not pool_scope))
        if arm.use_trend and self.trend_keywords:
            tr_all = self.bm25.scores(" ".join(self.trend_keywords))[pool]
            terms.append(Term("trend", "trend", tr_all[top], arm.w_trend, stats=_stats(tr_all) if pool_scope else None))
        if arm.use_penalty and req.feedback.rejected_item_ids:
            neg = self.catalog.positions(req.feedback.rejected_item_ids)
            if neg:
                sim_all = (self.image_emb[pool] @ self.image_emb[neg].T).max(axis=1)
                terms.append(
                    Term("penalty:rejected_similarity", "penalty", sim_all[top], -arm.w_penalty,
                         stats=_stats(sim_all) if pool_scope else None)
                )
        if arm.use_cross_reranker and self.cross_reranker is not None:
            rs = self.cross_reranker.score(text, [int(p) for p in cand])
            terms.append(Term(f"rerank:{self.cross_reranker.name}", "rerank", rs, arm.w_rerank))
        return terms

    def _metrics(self, req: Engine02Request, shown_pos: list[int]) -> RoundMetrics:
        items = self.catalog.items
        if not shown_pos:
            return RoundMetrics()
        sat = np.mean([satisfies(items, p, req.constraints) for p in shown_pos])
        hits = 0
        for attr, vals in req.constraints.excluded_values.items():
            if attr in items.columns:
                lv = {v.lower() for v in vals}
                hits += sum(str(items.at[p, attr]).lower() in lv for p in shown_pos)
        bad_ids = set(req.feedback.excluded_item_ids) | set(req.feedback.rejected_item_ids)
        viol = hits + sum(str(items.at[p, "item_id"]) in bad_ids for p in shown_pos)
        return RoundMetrics(hard_constraint_satisfaction=float(sat), excluded_value_hits=hits, feedback_violations=viol)
