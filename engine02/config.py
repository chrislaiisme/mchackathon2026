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
    # Repeat exposure within one session. "Shown earlier and not chosen" is NOT a taste signal —
    # it is "not seen" ∪ "seen and disliked" and those are not separable from one session's ~20
    # impressions (ExpoMF; Schnabel et al. 2016). It is also already read, properly, by the
    # preference learner's choice likelihood (`preference.py`, MNL/Bradley–Terry over the shown
    # set). So this is a **session-level freshness device**, phrased positively so the card can
    # say the true thing ("你還沒看過這件"), never an accusation about taste.
    use_freshness: bool = False
    w_freshness: float = 0.5
    freshness_decay: float = 0.5  # a round r rounds back counts decay**r for the score term
    # P(examined | rank) from eye tracking (Joachims, Granka, Pan, Hembrooke & Gay, SIGIR 2005,
    # 29 subjects), normalised to rank 1. Deliberately a lookup table, not a power law: attention
    # is flat over ranks 1–3 and falls off a cliff at 4–5, which r^-1 does not reproduce.
    exposure_weights: tuple[float, ...] = (1.0, 0.85, 0.71, 0.47, 0.37)
    # A round where the user chose nothing is an outside-option event: the weakest evidence, not
    # the strongest. Before this it counted every card at full weight.
    outside_option_kappa: float = 0.5
    # Position-weighted frequency cap: undecayed effective impressions ≥ this ⇒ drop from the
    # candidate pool for this round. Implemented, MEASURED, and off by default: it does buy a lot
    # of novelty (0.41 vs 0.24 at the last round) but it significantly damages what the user gets
    # (hidden utility 2.23 vs 2.58, p=0.0004) — it evicts items the user simply had not reached
    # yet. Set it only when a stakeholder asks for a hard "never repeat" guarantee. (§3.25)
    exposure_cap: float = 0.0
    z_clip: float | None = None  # clip normalised dense/bm25/trend/penalty terms to ±z_clip
    need_scale: float = 1.0  # γ: multiplies β_d (needs + feedback) — trade-off studied in T6
    w_dense: float = 1.0
    w_bm25: float = 0.5
    w_compat: float = 0.5
    w_trend: float = 0.2
    w_penalty: float = 0.5
    w_rerank: float = 1.0
    min_results: int = 5
    # When does the lexical side get switched off?
    #   "none"          never (the frozen `full` baseline)
    #   "coverage"      the old rule: scale w_bm25 by the share of query tokens in the catalog
    #                   vocabulary, off below bm25_min_coverage. Measured to almost never fire —
    #                   a paraphrase still has 85% coverage because words like "everyday" DO exist
    #   "docs_touched"  off when the query's terms touch less than bm25_min_docs_touched of the
    #                   catalog. The collapse is an idf pathology (one rare word owns the ranking),
    #                   so the signal has to be a count, not a score. Held-out test (§3.29):
    #                   fires on 94% of paraphrased and 2% of lexical queries, +0.157 NDCG@5 on the
    #                   former (p=0.0001) and −0.004 on the latter (p=1.00)
    bm25_gate: str = "none"
    bm25_adaptive: bool = False  # kept for the arms that measured the old rule
    bm25_min_coverage: float = 0.5
    bm25_min_docs_touched: float = 0.12  # threshold chosen on a dev half, reported on the other


FULL = ArmConfig(name="full")
# serving default: full + z-clip ±3. 44k: lexical NDCG@5 −0.006 (p=0.65), paraphrased +0.101 (p<0.001);
# 5k: −0.018 (p=0.036) / +0.098. Keeps single keyword matches from drowning the other reasons.
DEFAULT_ARM = "full_zclip3"

ARMS: dict[str, ArmConfig] = {
    "bm25": ArmConfig(name="bm25", candidate_fusion="bm25", additive_rerank=False),
    "dense": ArmConfig(name="dense", candidate_fusion="dense", additive_rerank=False),
    "hybrid_rrf": ArmConfig(name="hybrid_rrf", candidate_fusion="rrf", additive_rerank=False),
    "hybrid_convex": ArmConfig(name="hybrid_convex", candidate_fusion="convex", additive_rerank=False),
    "full": FULL,
    "hybrid_rrf_adaptive": ArmConfig(name="hybrid_rrf_adaptive", candidate_fusion="rrf", additive_rerank=False,
                                     bm25_adaptive=True, bm25_gate="coverage"),
    "full_adaptive_bm25": replace(FULL, name="full_adaptive_bm25", bm25_adaptive=True,
                                  bm25_gate="coverage"),
    "full_zclip3_nogate": replace(FULL, name="full_zclip3_nogate", z_clip=3.0,
                                  concept_image_weight=0.2, use_freshness=True),
    # serving default: ±3 z-clip on every normalised term, concept-image fusion at the measured
    # weight (a no-op unless ENGINE 01 sends feedback.concept_image_embedding), and the session
    # freshness device (§3.23/§3.25). `full` stays frozen as the reproducibility baseline for
    # §3.1–3.13; `full_zclip3_nofresh` is the control for rerunning the round-2 experiments.
    "full_zclip3": replace(FULL, name="full_zclip3", z_clip=3.0, concept_image_weight=0.2,
                           use_freshness=True, bm25_gate="docs_touched"),
    "full_zclip3_nofresh": replace(FULL, name="full_zclip3_nofresh", z_clip=3.0,
                                   concept_image_weight=0.2),
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
