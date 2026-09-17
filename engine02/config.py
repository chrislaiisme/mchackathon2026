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
    # which terms become reasons: "necessity" (PRD M7) | "contrastive" | "sufficient"
    reason_mode: str = "sufficient"
    # "candidates" (PRD: z-score inside top-50) | "pool" (stats from whole filtered pool)
    norm_scope: str = "pool"
    # design-element scores c(i,d): "descriptor" (PRD M4) | "random_words" | "antonym"
    concept_mode: str = "antonym"
    concept_dn: bool = True  # distribution normalisation of image embeddings
    concept_applicability: bool = True
    # concept_mode="hybrid": these elements come from VLM tags where available, the rest from
    # CLIP antonym scores (chosen by AUROC against blind visual labels, docs/engine02-design.md §3.3c)
    vlm_elements: tuple[str, ...] = ("matte_fabric", "glossy_fabric", "visible_logo", "minimal_design",
                                     "bold_pattern", "crisp_collar")
    w_dense: float = 1.0
    w_bm25: float = 0.5
    w_compat: float = 0.5
    w_trend: float = 0.2
    w_penalty: float = 0.5
    w_rerank: float = 1.0
    min_results: int = 5
    # scale the BM25 weight (and gate its RRF list) by query-token coverage of the catalog
    bm25_adaptive: bool = False
    bm25_min_coverage: float = 0.5


FULL = ArmConfig(name="full")

ARMS: dict[str, ArmConfig] = {
    "bm25": ArmConfig(name="bm25", candidate_fusion="bm25", additive_rerank=False),
    "dense": ArmConfig(name="dense", candidate_fusion="dense", additive_rerank=False),
    "hybrid_rrf": ArmConfig(name="hybrid_rrf", candidate_fusion="rrf", additive_rerank=False),
    "hybrid_convex": ArmConfig(name="hybrid_convex", candidate_fusion="convex", additive_rerank=False),
    "full": FULL,
    "hybrid_rrf_adaptive": ArmConfig(name="hybrid_rrf_adaptive", candidate_fusion="rrf", additive_rerank=False,
                                     bm25_adaptive=True),
    "full_adaptive_bm25": replace(FULL, name="full_adaptive_bm25", bm25_adaptive=True),
    "full_no_design": replace(FULL, name="full_no_design", use_design=False),
    "full_no_counterfactual": replace(FULL, name="full_no_counterfactual", counterfactual=False),
    "full_mmr": replace(FULL, name="full_mmr", use_mmr=True),
    "full_cross_reranker": replace(FULL, name="full_cross_reranker", use_cross_reranker=True),
    "full_concept_image": replace(FULL, name="full_concept_image", concept_image_weight=0.2),
    "full_no_rocchio": replace(FULL, name="full_no_rocchio", use_rocchio=False),
    # PRD-as-written baseline: descriptor concepts, candidate z-score, necessity reasons
    "prd_original": replace(FULL, name="prd_original", reason_mode="necessity", norm_scope="candidates",
                            concept_mode="descriptor", concept_dn=False, concept_applicability=False),
    "full_reason_necessity": replace(FULL, name="full_reason_necessity", reason_mode="necessity"),
    "full_reason_contrastive": replace(FULL, name="full_reason_contrastive", reason_mode="contrastive"),
    "full_norm_candidates": replace(FULL, name="full_norm_candidates", norm_scope="candidates"),
    "full_concept_descriptor": replace(FULL, name="full_concept_descriptor", concept_mode="descriptor"),
    "full_concept_random": replace(FULL, name="full_concept_random", concept_mode="random_words"),
    "full_concept_no_mask": replace(FULL, name="full_concept_no_mask", concept_applicability=False),
    # needs scripts/vlm_tag_attributes.py output (GPU recommended)
    "full_concept_vlm": replace(FULL, name="full_concept_vlm", concept_mode="vlm"),
    "full_concept_hybrid": replace(FULL, name="full_concept_hybrid", concept_mode="hybrid"),
}
