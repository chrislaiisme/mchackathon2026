"""ENGINE 02 service layer: one call that combines the evaluated recommender components.

rank(req):
  1. critique on a shown item (reference_item_id + critique) → composed retrieval
     (reference image ⊕ rewritten text, critique target as a never-relaxed required value;
     T8: 44k NDCG@10 0.347 → 0.610, docs/research/recsys-composed.md)
  2. Engine02 additive ranking with faithful reasons
  3. slate diversification (DPP θ=0.9 on the top-20 by default; near-duplicates 2.45% → 0.35%
     at no significant NDCG cost, docs/research/recsys-slate.md), promoted cards say so

complete_look(anchor_ids): complementary categories by NPMI, then items by the OutfitTransformer
complementary head when available (MRR 0.277 vs similarity 0.185 on Polyvore), else image similarity.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .composed import ComposedEngine02, Critique as ComposerCritique, TemplateRewriter
from .contracts import Engine02Request
from .diversify import DiversifiedResponse, DiversityConfig, deep_request, diversify_response


class ServiceResponse(DiversifiedResponse):
    composed: dict[str, Any] | None = None  # what the critique turned into (auditable)


class Engine02Service:
    def __init__(self, engine: ComposedEngine02, complete_the_look=None, rewriter=None):
        self.engine = engine
        self.ctl = complete_the_look
        self.composer = engine.composer(rewriter or TemplateRewriter("title"))

    # ------------------------------------------------------------------
    def _apply_critique(self, req: Engine02Request) -> tuple[Engine02Request, np.ndarray | None, dict | None]:
        fb = req.feedback
        if not (fb.reference_item_id and fb.critique):
            return req, None, None
        ref_pos = self.engine.catalog.pos(fb.reference_item_id)
        if ref_pos is None:
            return req, None, {"error": f"unknown reference_item_id {fb.reference_item_id!r}"}
        c = fb.critique
        base = req.retrieval_text or ""
        cq = self.composer.compose(
            ref_pos,
            ComposerCritique(attribute=c.attribute, to_value=c.to_value, from_value=c.from_value, direction=c.direction),
            base,
            "image_plus_text_filter",
            alpha=req.options.critique_alpha,
        )
        new = req.model_copy(deep=True)
        new.retrieval_text = cq.retrieval_text
        for attr, vals in cq.constraint_updates.items():
            new.constraints.required_values[attr] = list(vals)
        new.feedback.excluded_item_ids = list(dict.fromkeys(new.feedback.excluded_item_ids + cq.exclude_item_ids))
        info = {"reference_item_id": fb.reference_item_id, "target_text": cq.target_text,
                "required_values": cq.constraint_updates, "method": cq.method, **cq.params}
        return new, cq.query_embedding, info

    def rank(self, req: Engine02Request, arm: str | None = None) -> ServiceResponse:
        req2, q_override, composed = self._apply_critique(req)
        o = req.options
        cfg = DiversityConfig(method=o.diversify, param=o.diversify_param, depth=o.diversify_depth)
        self.engine._override = q_override
        try:
            deep = self.engine.run(deep_request(req2, cfg.depth), arm)
        finally:
            self.engine._override = None
        req2.options = req.options  # explanation settings of the caller for the final cards
        div = diversify_response(self.engine, req2, deep, cfg, k=o.top_k)
        return ServiceResponse(**div.model_dump(), composed=composed)

    # ------------------------------------------------------------------
    def complete_look(self, anchor_ids: list[str], n_categories: int = 2, k: int = 5,
                      filters: dict[str, list[str]] | None = None) -> dict:
        if self.ctl is None:
            raise RuntimeError("complete-the-look is not configured (needs category co-occurrence)")
        method = "ot_cir" if getattr(self.ctl, "ot", None) is not None else "similarity"
        slates = self.ctl.recommend(anchor_ids, n_categories=n_categories, k=k, method=method, filters=filters)
        items = self.engine.catalog.items
        return {
            "anchor_item_ids": anchor_ids,
            "method": method,
            "slates": [
                {
                    "category": s.category,
                    "category_score": s.category_score,
                    "items": [
                        {"item_id": it.item_id, "title": str(items.at[it.position, "title"]),
                         "image_path": str(items.at[it.position, "image_path"]), "score": it.score,
                         "contributions": it.contributions}
                        for it in s.items
                    ],
                }
                for s in slates
            ],
        }
