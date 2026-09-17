# ENGINE02 — Retrieval & Ranking

**Owner: not yet assigned.** This is a scaffold summary pulled from [hackathon-brief.md](hackathon-brief.md) — the assigned owner should expand this into a real spec (concrete field names off the Polyvore dataset, reranker weight formula, etc.) rather than treating this file as final.

## Goal

Given the current `Intent` from ENGINE01, retrieve and rank matching products, and produce a grounded natural-language reason per result. Not GPT-driven at its core — this is hand-implemented hybrid search + reranking; GPT is only used at the very end to phrase the reason.

## Data

Polyvore Outfits Dataset ([huggingface.co/datasets/mvasil/polyvore-outfits](https://huggingface.co/datasets/mvasil/polyvore-outfits)) as the core product catalog.

## Approach (from the brief)

- **Dense side**: FashionCLIP embeddings for semantic style similarity (e.g. "簡約", "正式", "防水").
- **Sparse side**: attribute filtering / BM25 (`rank_bm25`) for exact conditions (color, price range, season, size).
- **Reranker**: combines the dense/sparse similarity score, a Polyvore-style outfit-compatibility score, and ENGINE03's learned preference weight, to produce the final order — and because each signal is traceable, every result can cite *why* it ranked where it did (the "可解釋" requirement).
- The generated concept image (from `backend/generation/`) is also embedded via FashionCLIP and folded into the dense-side score each round, so retrieval and generation reinforce each other rather than running as two unrelated systems.
- Vector storage: Chroma or FAISS, embedded in-process — no separate DB service needed for a two-day build.
- Reason generation: ranked item attributes → GPT chat completions → one natural-language sentence, grounded in the real retrieved attributes (not free-invented).

## Interface

In: `Intent` (from ENGINE01) + weight adjustments (from ENGINE03). Out: `RetrievalResult` (`products: ProductCard[]`, `concept_image`, `match_score`) — see [interface-contract.md](interface-contract.md).

## Offline validation

Ablation: same test queries run through keyword-only, embedding-only, and hybrid+rerank; compare Precision@5 / NDCG@5 across the three to demonstrate the hybrid approach's advantage. See [validation-plan.md](validation-plan.md).

## Dependencies

`OPENAI_API_KEY` (reason generation only — the retrieval/ranking math itself doesn't call GPT).
