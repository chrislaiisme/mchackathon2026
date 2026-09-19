"""ENGINE 02 service layer: one call that combines the evaluated recommender components.

rank(req):
  0. preference learning from choice_history → Δβ over design elements (Bayesian pairwise logistic,
     posterior mean; T7: beats the PRD ±1 rule at 5k and 44k, docs/research/recsys-preference.md)
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
    learned_preferences: dict[str, Any] | None = None  # Δβ learned from choice_history



# how each complete-the-look term reads on a card, and what the number under it means
_SLATE_TERM_LABEL = {
    "complementary": "互補頭判定它和你選的那件搭得起來",
    "compatibility": "相容性判定它和你選的那件不衝突",
    "similarity": "和你選的那件在風格空間裡相近",
    "category": "這個品類和你選的那件經常一起出現",
}


def _slate_reason(contributions: dict, category: str, category_score: float,
                  price: float | None, currency: str = "") -> str:
    """One sentence, every clause backed by a number we actually computed."""
    parts = [f"{_SLATE_TERM_LABEL.get(k, k)}（{v:+.2f}）"
             for k, v in sorted(contributions.items(), key=lambda kv: -abs(kv[1]))]
    parts.append(f"{_SLATE_TERM_LABEL['category']}（NPMI {category_score:+.2f}）")
    if price is not None:
        parts.append(f"售價 {price:,.0f}{currency}")
    return "；".join(parts)


def _price_of(items, position: int) -> float | None:
    """The item's price, or None when this catalog has no prices — never a fabricated 0."""
    if "price" not in items.columns:
        return None
    import pandas as pd

    v = pd.to_numeric(items["price"].iat[position], errors="coerce")
    return None if pd.isna(v) else float(v)


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

    def _learn_preferences(self, req: Engine02Request, arm_name: str | None) -> tuple[Engine02Request, dict | None]:
        """T7 default: Bayesian pairwise logistic, posterior mean (docs/research/recsys-preference.md)."""
        fb = req.feedback
        if fb.design_weight_delta or not fb.choice_history:
            return req, None
        from .config import ARMS
        from .preference import BayesLogistic, ChoiceRound, DesignSpace

        arm = ARMS[arm_name or req.options.arm]
        cat = self.engine.catalog
        space = DesignSpace.from_kansei(self.engine.kansei)
        F = space.features(self.engine.design_matrix(arm))
        beta0 = space.prior_mean({n.need_id: n.prob for n in req.needs}, arm.need_scale)
        hist = [ChoiceRound(shown=cat.positions(r.shown_item_ids),
                            chosen=cat.pos(r.chosen_item_id) if r.chosen_item_id else None,
                            rejected=cat.positions(r.rejected_item_ids)) for r in fb.choice_history]
        # shrink_kappa=1: Δβ·n/(n+1) — halves the first-click over-reaction without utility loss (T7b)
        upd = BayesLogistic(rationality=0.5, prior_sd=1.0, shrink_kappa=1.0).update(hist, F, beta0)
        new = req.model_copy(deep=True)
        new.feedback.design_weight_delta = space.to_dict(upd.delta)
        return new, {"method": "bayes_pairwise_logistic", "shrink_kappa": 1.0, "rounds": len(hist),
                     "design_weight_delta": new.feedback.design_weight_delta}

    def rank(self, req: Engine02Request, arm: str | None = None) -> ServiceResponse:
        req, learned = self._learn_preferences(req, arm)
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
        # the substitute must be an item the user can actually see, and diversification decides the
        # final slate after the pipeline has ranked it — so re-point it here, not in the pipeline
        if div.constraint_report.substitutes:
            div.constraint_report.substitutes = self._repoint_substitutes(div)
        return ServiceResponse(**div.model_dump(), composed=composed, learned_preferences=learned)

    def _repoint_substitutes(self, resp) -> list[dict]:
        import numpy as np

        cat = self.engine.catalog
        img = np.asarray(self.engine.image_emb, dtype=np.float32)
        shown = [p for p in (cat.pos(it.item_id) for it in resp.items) if p is not None]
        out = []
        for s in resp.constraint_report.substitutes:
            src = cat.pos(str(s.get("excluded_item_id")))
            if src is None or not shown:
                continue
            sims = img[np.asarray(shown, dtype=int)] @ img[src]
            near = int(shown[int(np.argmax(sims))])
            out.append({**s, "substitute_item_id": str(cat.items.at[near, "item_id"]),
                        "substitute_title": str(cat.items.at[near, "title"]),
                        "similarity": round(float(np.max(sims)), 4)})
        return out

    # ------------------------------------------------------------------
    def complete_look_method(self) -> str:
        """Best method the loaded heads support: complementary (T5 winner) > compatibility > similarity."""
        heads = getattr(getattr(self.ctl, "ot", None), "heads", ())
        if "complementary" in heads:
            return "ot_cir"
        if "compatibility" in heads:
            return "ot_sim"
        return "similarity"

    def complete_look(self, anchor_ids: list[str], n_categories: int = 2, k: int = 5,
                      filters: dict[str, list[str]] | None = None,
                      budget: float | None = None) -> dict:
        if self.ctl is None:
            raise RuntimeError("complete-the-look is not configured (needs category co-occurrence)")
        unknown = [i for i in anchor_ids if self.engine.catalog.pos(i) is None]
        if unknown:  # otherwise the anchors are silently dropped and the caller gets empty slates
            raise ValueError(f"unknown anchor_item_ids: {unknown}")
        method = self.complete_look_method()
        slates = self.ctl.recommend(anchor_ids, n_categories=n_categories, k=k, method=method, filters=filters)
        items = self.engine.catalog.items

        # 「一套…預算 3,000 元」 is a budget for the WHOLE outfit. A per-item filter at 3,000
        # returns four garments costing 3,000 each, which is not what was asked.
        plan = None
        if budget is not None:
            import pandas as pd

            from .outfit_budget import plan_outfit

            price_col = (pd.to_numeric(items["price"], errors="coerce")
                         if "price" in items.columns else None)
            slots = {}
            for sl in slates:
                slots[sl.category] = [
                    (it.item_id, str(items.at[it.position, "title"]),
                     (float(price_col.iat[it.position])
                      if price_col is not None and pd.notna(price_col.iat[it.position]) else None),
                     float(it.score))
                    for it in sl.items
                ]
            # the anchors are already owned, so they do not spend the budget
            plan = plan_outfit(slots, budget).as_dict()

        return {
            "anchor_item_ids": anchor_ids,
            "method": method,
            "outfit_plan": plan,
            "slates": [
                {
                    "category": s.category,
                    "category_score": s.category_score,
                    "items": [
                        {"item_id": it.item_id, "title": str(items.at[it.position, "title"]),
                         "image_path": str(items.at[it.position, "image_path"]), "score": it.score,
                         "contributions": it.contributions,
                         "price": _price_of(items, it.position),
                         # the screen that is literally about 「為什麼這樣搭」 has to say it, and
                         # every clause below cites a number we computed (§3.4's rule, applied here)
                         "reason": _slate_reason(it.contributions, s.category, s.category_score,
                                                 _price_of(items, it.position))}
                        for it in s.items
                    ],
                }
                for s in slates
            ],
        }
