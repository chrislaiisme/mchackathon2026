"""Ablation arms. Every arm runs through the same pipeline; only these switches change."""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class ArmConfig:
    name: str
    candidate_fusion: str = "rrf"  # "bm25" | "dense" | "rrf" | "convex"
    convex_alpha: float = 0.5
    convex_norm: str = "minmax"
    rrf_k: int = 60
    rrf_depth: int = 200
    additive_rerank: bool = True  # False → final order = candidate fusion order
    use_design: bool = True
    use_compat: bool = True  # still only active when anchors exist
    use_trend: bool = True
    use_penalty: bool = True
    use_cross_reranker: bool = False
    use_mmr: bool = False
    mmr_lambda: float = 0.7
    use_rocchio: bool = True
    rocchio_a: float = 0.5
    rocchio_b: float = 0.25
    concept_image_weight: float = 0.0  # evidence says keep ≤ 0.2 (BMVC 2025, IP-CIR)
    counterfactual: bool = True
    w_dense: float = 1.0
    w_bm25: float = 0.5
    w_compat: float = 0.5
    w_trend: float = 0.2
    w_penalty: float = 0.5
    w_rerank: float = 1.0
    min_results: int = 5


FULL = ArmConfig(name="full")

ARMS: dict[str, ArmConfig] = {
    "bm25": ArmConfig(name="bm25", candidate_fusion="bm25", additive_rerank=False),
    "dense": ArmConfig(name="dense", candidate_fusion="dense", additive_rerank=False),
    "hybrid_rrf": ArmConfig(name="hybrid_rrf", candidate_fusion="rrf", additive_rerank=False),
    "hybrid_convex": ArmConfig(name="hybrid_convex", candidate_fusion="convex", additive_rerank=False),
    "full": FULL,
    "full_no_design": replace(FULL, name="full_no_design", use_design=False),
    "full_no_counterfactual": replace(FULL, name="full_no_counterfactual", counterfactual=False),
    "full_mmr": replace(FULL, name="full_mmr", use_mmr=True),
    "full_cross_reranker": replace(FULL, name="full_cross_reranker", use_cross_reranker=True),
    "full_concept_image": replace(FULL, name="full_concept_image", concept_image_weight=0.2),
    "full_no_rocchio": replace(FULL, name="full_no_rocchio", use_rocchio=False),
}
