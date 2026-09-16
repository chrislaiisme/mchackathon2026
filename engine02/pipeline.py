"""ENGINE 02 main entry: Engine02Request → Engine02Response.

filter (with relaxation) → candidate retrieval (BM25 / dense / RRF / convex)
→ additive rerank (dense, bm25, design β·c, compat, trend, penalty, optional reranker)
→ optional MMR → counterfactual necessity → reasons → optional LLM paraphrase.
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
from .rerank import Term, additive_score, counterfactual_ranks
from .sparse import BM25Index


class CrossReranker(Protocol):
    name: str

    def score(self, query: str, item_positions: list[int]) -> np.ndarray: ...


def build_retrieval_text(req: Engine02Request) -> str:
    if req.retrieval_text:
        return req.retrieval_text
    c = req.constraints
    parts: list[str] = []
    for slot in (c.color, c.style_keywords, c.season):
        if slot.state.value in ("value", "inferred"):
            parts += slot.values
    parts += c.category.values or ["clothing"]
    if c.occasion.values:
        parts += ["for"] + c.occasion.values
    return " ".join(parts)


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
        cache = Path(cache_dir) if cache_dir else catalog.root / "index"
        safe = encoder.name.replace("/", "__")
        self.image_emb = cached_image_embeddings(encoder, catalog.image_paths(), cache / f"img_{safe}.npy")
        c_file = cache / f"design_{safe}_{self.kansei.version}.npy"
        if c_file.exists() and np.load(c_file).shape == (len(catalog), len(self.kansei.elements)):
            self.c = np.load(c_file)
        else:
            self.c = design_scores(encoder, self.image_emb, self.kansei)
            np.save(c_file, self.c)
        self.bm25 = BM25Index(catalog.texts())
        self.trend_keywords: list[str] = []
        self.vocabulary = list(self.kansei.needs.values()) + [e.label for e in self.kansei.elements]
        self.init_ms = (time.perf_counter() - t0) * 1000

    def set_trends(self, keywords: list[str]) -> None:
        self.trend_keywords = keywords

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

        terms = self._terms(req, arm, cand, dense_all[top], bm25_all[top], fused[top], text)
        sc = additive_score(terms)
        order = sc.order()
        if arm.use_mmr and len(order) > 1:
            depth = min(len(order), max(4 * k, 20))
            sel = fusion.mmr(sc.scores[order[:depth]], self.image_emb[cand[order[:depth]]], k, arm.mmr_lambda)
            order = np.concatenate([order[:depth][sel], np.setdiff1d(order, order[:depth][sel], assume_unique=True)])
        shown = [int(p) for p in order[:k]]
        lap("rerank")

        cf = counterfactual_ranks(sc, shown) if (arm.counterfactual and req.options.counterfactual_check) else {}
        lap("counterfactual")

        probs = {n.need_id: n.prob for n in req.needs}
        el_labels = {e.id: e.label for e in self.kansei.elements}
        out_items: list[RankedItem] = []
        for rank, p in enumerate(shown, start=1):
            pos = int(cand[p])
            contribs = []
            for j, term in enumerate(sc.terms):
                cval = float(sc.contrib[p, j])
                shares = {}
                if term.group == "design":
                    shares = {n: v * float(sc.norm[p, j]) for n, v in term.need_shares_per_unit.items()}
                rw = cf.get(p, [None] * len(sc.terms))[j]
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
                        necessary=(rw > k) if rw is not None else None,
                    )
                )
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
                    design_scores={e.id: float(self.c[pos, j]) for j, e in enumerate(self.kansei.elements)},
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
    def _terms(self, req, arm: ArmConfig, cand, dense, bm25, fused, text) -> list[Term]:
        if not arm.additive_rerank:
            if arm.candidate_fusion == "rrf":
                d = 1.0 / (arm.rrf_k + fusion.ranks_desc(dense))
                b = 1.0 / (arm.rrf_k + fusion.ranks_desc(bm25))
                return [Term("dense", "dense", d, 1.0, normalize=False), Term("bm25", "bm25", b, 1.0, normalize=False)]
            if arm.candidate_fusion == "convex":
                f = fusion.minmax if arm.convex_norm == "minmax" else fusion.zscore
                return [
                    Term("dense", "dense", f(dense), arm.convex_alpha, normalize=False),
                    Term("bm25", "bm25", f(bm25), 1 - arm.convex_alpha, normalize=False),
                ]
            single = dense if arm.candidate_fusion == "dense" else bm25
            return [Term(arm.candidate_fusion, arm.candidate_fusion, single, 1.0, normalize=False)]

        terms = [Term("dense", "dense", dense, arm.w_dense), Term("bm25", "bm25", bm25, arm.w_bm25)]
        if arm.use_design and len(self.kansei.elements):
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
                terms.append(Term(f"design:{el.id}", "design", self.c[cand, j], w, per_unit))
        if arm.use_compat and req.feedback.anchor_item_ids:
            anchors = self.catalog.positions(req.feedback.anchor_item_ids)
            cs = compat_scores(
                [self.catalog.attr(int(p), "category") for p in cand],
                [self.catalog.attr(a, "category") for a in anchors],
                self.cooc,
            )
            if cs is not None:
                terms.append(Term("compat", "compat", cs, arm.w_compat))
        if arm.use_trend and self.trend_keywords:
            tr = self.bm25.scores(" ".join(self.trend_keywords))[cand]
            terms.append(Term("trend", "trend", tr, arm.w_trend))
        if arm.use_penalty and req.feedback.rejected_item_ids:
            neg = self.catalog.positions(req.feedback.rejected_item_ids)
            if neg:
                sim = (self.image_emb[cand] @ self.image_emb[neg].T).max(axis=1)
                terms.append(Term("penalty:rejected_similarity", "penalty", sim, -arm.w_penalty))
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
