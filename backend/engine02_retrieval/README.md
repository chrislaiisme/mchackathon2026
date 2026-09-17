# ENGINE02 — Retrieval & Ranking

**Owner: not yet assigned.** Placeholder folder created as part of the repo scaffold so this line can start immediately.

Hybrid search (FashionCLIP dense embeddings + BM25/attribute sparse filtering) over the [Polyvore Outfits Dataset](https://huggingface.co/datasets/mvasil/polyvore-outfits), reranked by combining style-similarity score, Polyvore-style outfit-compatibility score, and ENGINE03's learned preference weights. GPT (chat completions, no LangChain) turns the final ranking into a natural-language reason grounded in the item's real attributes. The generated concept image from the `generation` module is also embedded and folded into the dense-side score every round, so retrieval and generation improve each other.

Full spec: [../../docs/engine02-retrieval.md](../../docs/engine02-retrieval.md). Input/output JSON: [../../docs/interface-contract.md](../../docs/interface-contract.md) (`Intent` in, `RetrievalResult` out — see `ProductCard`).

Depends on `OPENAI_API_KEY` for the reason-generation step (see root `CLAUDE.md` "P0 status").
