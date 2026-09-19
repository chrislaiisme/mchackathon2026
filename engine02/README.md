# ENGINE 02 — Retrieval, Ranking and Faithful Explanation

ENGINE 02 turns a structured intent (from ENGINE 01) and the feedback ledger (from ENGINE 03)
into ranked clothing items whose **score decomposition is the explanation**. Every reason shown on a
card is a term that provably keeps the item in the top-k, and an LLM may only re-word verified facts.

Full design, interface contract and experiment report (Traditional Chinese): [`docs/engine02-design.md`](../docs/engine02-design.md).

## Pipeline

```
Engine02Request (hard constraints, need probabilities p(n), feedback ledger)
 1. hard-constraint filter with a reported relaxation ladder (category/gender/exclusions never relaxed)
 2. candidates: fashion image embeddings (Marqo-FashionSigLIP) + BM25, fused by RRF / normalised convex sum
 3. additive rerank:  S(i) = w·z(dense) + w·z(bm25) + Σ_d β_d·c(i,d) [+ compat if anchor] [+ trend] − penalty
        β_d = Σ_n p(n)·K[n,d] + step·Δ_d     (Kansei table K: needs × visible design elements)
        c(i,d): CLIP antonym-pair scores, or VLM (Qwen3-VL-8B) tags for validated elements
 4. reasons = minimal sufficient set of terms (they alone keep the item above rank k+1)
 5. template sentence → optional LLM paraphrase accepted only if every label/number is in the facts
Engine02Response (cards with contributions summing to the score, c(i,d) for ENGINE 03, rule-based metrics)
```

## Quick start

```bash
uv venv --python 3.12 .venv
uv pip install -e ".[dev]"     # serving path + tests; torch is imported lazily, so this alone runs the API
uv pip install -e ".[models]"  # the encoders (install the torch build that matches the machine first)

# data (public HF datasets; see docs/research/catalog-options.md for licences)
python scripts/prepare_catalog.py --source Marqo/KAGL --limit 5000 --shuffle-buffer 256 --seed 0 --out data/catalog/kagl
python scripts/prepare_catalog.py --source Marqo/polyvore --limit 3000 --out data/catalog/polyvore --full-cooccurrence

pytest -q tests                                   # 249 tests, model-free
python scripts/integration_check.py --catalog data/catalog/kagl --encoder hash   # can an LLM drive it?

# API (hash encoder = no model download; use marqo-fashionSigLIP for real ranking)
ENGINE02_ENCODER=marqo-fashionSigLIP uvicorn engine02.api:app --port 8002
curl -X POST localhost:8002/rank -H "content-type: application/json" -d @docs/contract/example_round1_request.json
```

Optional: put `OPENAI_API_KEY=...` in `.env` to enable the fact-checked LLM paraphrase of reasons.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/rank` | `Engine02Request` → `Engine02Response` |
| POST | `/rank/plain` | the additive pipeline alone, for ablations |
| POST | `/view` | rank + the §7 panels (said/unsaid, needs, Div@k, provenance, round diff) |
| POST | `/complete-look` | complete the look: categories by NPMI, items by the OutfitTransformer complementary head |
| POST | `/facets` | the SAME ranking read along one design axis ("plain ↔ bold pattern"); a panel, never a reranker |
| GET | `/profile/questions` | three forced choices between real garments, asked before the first query |
| POST | `/profile` | those choices → `Engine02Request.profile`, a prior real feedback outvotes after kappa0 rounds |
| POST | `/visual-search` | search with an uploaded photo (base64) and profile its design elements |
| POST | `/concept-image/nearest` | items closest to a generated concept image (display only) |
| GET | `/gap/elements`, `/gap/cells` | design-element and (category, colour) demand vs catalog supply |
| GET | `/needs/supply` | Sup(n): share of the catalog expressing each hidden need |
| GET | `/trends` | display-only trend badges (`ENGINE02_TRENDS=1`); never part of the score |
| GET | `/context` | external context fetched EARLIER by `scripts/fetch_context.py`; the serving path never touches the network |
| GET | `/vocabulary` | catalog values ENGINE 01 must normalise slot values to |
| GET | `/kansei` | need ids and design-element ids |
| GET | `/items/{id}`, `/images/{id}` | item metadata / image |
| GET | `/arms`, `/health` | ablation arms, service status (including which OutfitTransformer heads loaded) |

JSON Schemas and real two-round examples: [`docs/contract/`](../docs/contract/).
The fixed operation set ENGINE 03 sends back (with its ledger) is specified in
[`engine02/handshake.py`](handshake.py); the view model behind `/view` is in
[`engine02/panels.py`](panels.py); offline replay for the demo is in [`engine02/replay.py`](replay.py).

## Reproducing the experiments

```bash
python scripts/verify_models.py --models all --device auto          # every candidate model loads and runs
python scripts/run_ablation.py --encoder marqo-fashionSigLIP --device auto [--reranker Qwen3-VL-Reranker-2B]
python scripts/vlm_tag_attributes.py --catalog data/catalog/kagl --model Qwen/Qwen3-VL-8B-Instruct   # GPU
python scripts/eval_visual_labels.py --encoder marqo-fashionSigLIP
python scripts/reproduce.py --check-claims        # re-derives the numbers quoted in the design doc
```

All ground truth in T1–T5 comes from catalog metadata or blind visual labels, never from the ranking score.

## Key results (KAGL; details and CIs in the design doc)

| Finding | Evidence |
|---|---|
| The lexical side switches itself off when the query barely touches the catalog | paraphrased queries 0.111 → 0.308 NDCG@5 (p<1e-5) with no cost on lexical ones (−0.002, p=0.50); the old coverage gate never fired because rare words like "everyday" ARE in the vocabulary |
| Hybrid retrieval needs ENGINE 01 to normalise values to catalog vocabulary | NDCG@5 lexical: hybrid 0.80–0.87 vs dense 0.53–0.61; paraphrased: hybrid 0.09–0.21 vs dense 0.43–0.46 (5k and 44k) |
| Antonym-pair concept scores beat the PRD descriptor scores | AUROC casual 0.66–0.72 → 0.98, dark tone 0.84–0.86 → 0.98; random-word control 0.33–0.70 |
| VLM tags fix material/sheen | glossy AUROC CLIP 0.71 → Qwen3-VL-8B 0.90 (LLM-annotated labels) |
| Minimal-sufficient reasons cover every card | 100% coverage and sufficiency vs 80–90% coverage for the PRD necessity rule |
| Critique feedback helps; Rocchio does not (yet) | success@4 rounds 1% → 39–42% (p<0.001); Rocchio vs critique-only p≈0.5 at both 5k and 44k |
| Image reranker not worth it by default | Qwen3-VL-Reranker-2B: −0.043 NDCG@5 on lexical queries (p=0.001), +~1 s/query on RTX 4090. Three more rerankers were measured and rejected (§3.28) |
| Grounding the query in catalog words makes it worse | −0.095 lexical / −0.085 paraphrase: grounding raises the share of documents touched, which stops the BM25 gate firing, so the weaker fix blocks the stronger one (§3.30) |
| Weather is not a ranking term here | cold Open-Meteo call from Taipei p50 1.57 s vs a 12.8 ms /rank, and this catalog cannot validate it (756 "Winter" items include 294 watches; sweaters are 0% Winter). Shipped as a side-car the caller may attach, never as a score (§3.34) |
| Trend keywords must stay out of the score | 28 configurations, all worse: −0.16 to −0.38 NDCG@5 (p≈1e-4) → badges only |
| A concept image helps when the user cannot describe what they want | w=0.2: NDCG@5 0.078 → 0.278 on 44k (p≈1e-4) with a null random-image control (−0.004, p=0.71) |
| A live round feels instant | /rank p50 12.8 ms (17.8k) / 15.7 ms (44k), /complete-look 33 ms: 23x and 17x faster, every step proved ranking-neutral (scripts/check_parity.py) |
| Round 2 was replaying round 1 | without the not-yet-seen (freshness) term the 4th round's novelty is 0.007; with it, 0.237 (p<1e-4) and the best item in the slate improves (p=0.008). The wording is positive on purpose: "you have not seen this one yet", not "you did not pick it" |
| A stated exclusion is enforced in the same round | "不要黑色" left in the query text: violation@5 0.214 → 0.000 (p=5e-5) and NDCG@5 +0.045 (p=0.0007) — obeying costs nothing. A colour word is family-level, so Navy Blue goes too |
| A critique is three statements, not one vector | naming them (want / keep / avoid) adds +0.064 NDCG@10 (p=5e-5) on 600 triplets; the same terms WITHOUT the hard filter are −0.116, so they add to it rather than replace it |
| Named facets cost the ranking nothing | the slate is bit-identical after asking for facets (pinned by a test); 2.7 ms on 50 candidates |
| A pre-query profile survives its own control, but barely | round-1 MRR 0.0143 → 0.0239 (p=0.0003) and it beats its shuffled twin (p=0.0076) — yet 0.0072 of that 0.0096 is reproduced by shuffling, so only about a quarter is the content of the answers |
| The gap panel responds to a real gap, not to catalog size | removing the items that express an element lifts it (MRR 0.381 → 0.509, p<1e-4); removing the same number of random items does not (p=1.00). Rerun at 44k with the real encoder, `reports/server/gap_kagl_marqo/` |
| Attribute filling is worth less than we first wrote | one query set sent to both catalogs: relaxation 31% → 11%, satisfaction 0.782 → 0.958. The cleanest cell is that Polyvore items in the top 5 go 0.00 → 2.12, because before filling those categories could never survive a four-slot filter (§3.17, corrected 2026-09-18) |

Limitations: public catalogs have no prices; KAGL lacks blazers/knitwear (Polyvore apparel merged as a
workaround); simulated users are rule-based; visual labels were produced by an LLM annotator, not humans
(`scripts/eval_human_agreement.py` + `data/labels/human_tasks.csv` are ready for a human pass; the
headline number there is **Krippendorff's alpha over all three answers**, not Cohen's kappa on the 1/0
subset — kappa silently drops every na-vs-decided pair, which are exactly the hard cases, and reports a
higher number for it); on filled catalogs never evaluate against an attribute the model itself filled —
`concept_labels()` drops those rows by default.
