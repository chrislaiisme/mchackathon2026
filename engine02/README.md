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
uv pip install torch torchvision open_clip_torch "transformers>=5.17" sentence-transformers accelerate \
    qwen-vl-utils rank_bm25 datasets pillow numpy pandas scipy pydantic fastapi uvicorn pytest openai

# data (public HF datasets; see docs/research/catalog-options.md for licences)
python scripts/prepare_catalog.py --source Marqo/KAGL --limit 5000 --shuffle-buffer 256 --seed 0 --out data/catalog/kagl
python scripts/prepare_catalog.py --source Marqo/polyvore --limit 3000 --out data/catalog/polyvore --full-cooccurrence

pytest -q tests                                   # 20 tests, model-free

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
| POST | `/concept-image/nearest` | items closest to a generated concept image (display only) |
| GET | `/needs/supply` | Sup(n): share of the catalog expressing each hidden need |
| GET | `/trends` | display-only trend badges (`ENGINE02_TRENDS=1`); never part of the score |
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
| Hybrid retrieval needs ENGINE 01 to normalise values to catalog vocabulary | NDCG@5 lexical: hybrid 0.80–0.87 vs dense 0.53–0.61; paraphrased: hybrid 0.09–0.21 vs dense 0.43–0.46 (5k and 44k) |
| Antonym-pair concept scores beat the PRD descriptor scores | AUROC casual 0.66–0.72 → 0.98, dark tone 0.84–0.86 → 0.98; random-word control 0.33–0.70 |
| VLM tags fix material/sheen | glossy AUROC CLIP 0.71 → Qwen3-VL-8B 0.90 (LLM-annotated labels) |
| Minimal-sufficient reasons cover every card | 100% coverage and sufficiency vs 80–90% coverage for the PRD necessity rule |
| Critique feedback helps; Rocchio does not (yet) | success@4 rounds 1% → 39–42% (p<0.001); Rocchio vs critique-only p≈0.5 at both 5k and 44k |
| Image reranker not worth it by default | Qwen3-VL-Reranker-2B: −0.043 NDCG@5 on lexical queries (p=0.001), +~1 s/query on RTX 4090 |
| Trend keywords must stay out of the score | 28 configurations, all worse: −0.16 to −0.38 NDCG@5 (p≈1e-4) → badges only |
| A concept image helps when the user cannot describe what they want | w=0.2: NDCG@5 0.078 → 0.278 on 44k (p≈1e-4) with a null random-image control (−0.004, p=0.71) |

Limitations: public catalogs have no prices; KAGL lacks blazers/knitwear (Polyvore apparel merged as a
workaround); simulated users are rule-based; visual labels were produced by an LLM annotator, not humans
(`scripts/eval_human_agreement.py` + `data/labels/human_tasks.csv` are ready for a human pass, with
Cohen's kappa against the LLM annotator); on filled catalogs never evaluate against an attribute the
model itself filled — `concept_labels()` drops those rows by default.
