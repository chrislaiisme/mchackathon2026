# Common brief for ENGINE 02 recommender-system sub-agents (read fully before starting)

## Project
Hackathon (sponsor Makalot, garment OEM). ENGINE 02 = retrieval + ranking + faithful explanation for clothing.
Repo (local, Windows): `E:\mchackathon2026`, branch `engine02-research`. Read first:
`docs/engine02-design.md` (design + all results so far), `engine02/contracts.py`, `engine02/pipeline.py`,
`engine02/rerank.py`, `engine02/config.py`, `engine02/eval/tasks.py`, `engine02/eval/metrics.py`.

Key facts:
- `Engine02(catalog, encoder, kansei=None, cooccurrence=None, compat_model=None, cross_reranker=None).run(req, arm)`
  returns `Engine02Response`; each `RankedItem` has `contributions` (sum == score), `design_scores` c(i,d).
- Hard filter → BM25 + dense (image embeddings) → RRF → additive rerank S(i)=Σ terms; design term weight
  β_d = γ·(Σ_n p(n)K[n,d] + step·Δsteps_d); Rocchio on chosen/rejected image embeddings (no measurable effect so far).
- `engine.image_emb` (L2-normalised image embeddings), `engine.design_matrix(ARMS["full"])` (n_items × n_elements c(i,d)),
  `engine.kansei` (need_ids, element_ids, K), `engine.catalog.items` (pandas: item_id, title, category, subcategory,
  color, season, occasion, gender, outfit_ids, image_path).
- Catalogs: `data/catalog/kagl` (5k, has color/occasion/gender), `data/catalog/kagl_full` (44k, nycu only),
  `data/catalog/polyvore_big` (25k Polyvore with outfit_ids, nycu only), `data/catalog/kagl_polyvore` (merged, nycu only).
- Stats helpers: `engine02.eval.metrics` (ndcg_at_k, hit_at_k, recall_at_k, mrr, paired_permutation_test, bootstrap_ci).
- Encoders: `engine02.models.TorchEncoder("marqo-fashionSigLIP"|"fashion-clip", device)`; `engine02.encoders.HashEncoder` (model-free).

## Hard rules
1. **Do not edit any existing file.** Only create new files (your module, your eval script, your tests, your report).
   If the pipeline needs a hook, implement it as a wrapper/subclass or post-processing in your own file and
   describe the exact hook needed in your report. The coordinator integrates.
2. **Local machine has ~1 GB free RAM**: locally run only unit tests with `HashEncoder` (no torch models).
   Local python: `E:/mchackathon2026/.venv/Scripts/python.exe`. Run your tests with `-q tests/<your_test>.py` only.
3. **All real experiments run on the nycu server**, in YOUR OWN directory:
   - SSH: `ssh -o BatchMode=yes -p 2222 neil@140.113.26.164` (alias `nycu`). Parallel requests are allowed there, but
     batch many commands into one ssh call and use tmux for anything longer than ~1 minute.
   - **Never write to the home directory** (`~`). Everything goes under `/tmp/neil/agents/<your-name>/`.
   - Sync code: from local run `tar czf - --exclude=.venv --exclude=data --exclude=artifacts --exclude=reports --exclude=third_party --exclude=.git -C /e/mchackathon2026 . | ssh ... "mkdir -p /tmp/neil/agents/<name>/repo && tar xzf - -C /tmp/neil/agents/<name>/repo"`,
     then on the server `ln -sfn /tmp/neil/mchackathon2026/data /tmp/neil/agents/<name>/repo/data` and
     `ln -sfn /tmp/neil/mchackathon2026/third_party /tmp/neil/agents/<name>/repo/third_party`.
   - Python on server: `/tmp/neil/mchackathon2026/.venv/bin/python` (torch CUDA, open_clip, transformers, rank_bm25…).
   - Always export: `HF_HOME=/tmp/neil/mchackathon2026/.runtime/cache/hf XDG_CACHE_HOME=/tmp/neil/agents/<name>/cache TMPDIR=/tmp/neil/agents/<name>/tmp TOKENIZERS_PARALLELISM=false`
     (create those dirs). Models are already cached in HF_HOME — do not download new large models.
   - Embedding caches: Engine02 writes `<catalog>/index/*.npy`. Pass `cache_dir=/tmp/neil/agents/<name>/index_<catalog>` to
     `Engine02(...)` so you never overwrite the shared caches; you MAY read the shared ones by copying.
   - GPU: an RTX 4090 is shared with a running Qwen3-VL job (~17.5 GB VRAM, tmux session `e02`). **Do not touch tmux
     session `e02` or `/tmp/neil/mchackathon2026/.runtime/logs`.** Keep your VRAM under ~4 GB (encoders only).
   - Root disk has ~70 GB free; keep your outputs small (CSV/JSON).
4. Pull result files back to local `E:\mchackathon2026\reports\agents\<name>\` (scp). Raw results stay out of git.
5. Every claim needs numbers with paired statistics (paired permutation test and/or bootstrap CI) over queries/targets,
   seeds fixed, and an explicit statement of what the ground truth is and its caveats (simulated users are
   simulations; metadata labels are proxies). Negative/null results are valuable — report them honestly.
6. Verify library APIs via `npx ctx7@latest library <name> "<q>"` / `npx ctx7@latest docs <id> "<q>"` before using them.
   Cite papers only if you open them (WebSearch/WebFetch may be exhausted; OpenAlex/arXiv API via curl is fine).

## Deliverables (all agents)
- New module(s) under `engine02/` with docstrings citing the method's paper.
- `tests/test_<name>.py` passing locally with HashEncoder.
- `scripts/eval_<name>.py` that reproduces your experiment on nycu.
- `docs/research/recsys-<name>.md` in Traditional Chinese: method, setup, table of results with CIs/p-values,
  honest interpretation, recommended default, and the exact integration hook for the coordinator.
- Final message ≤250 words (Traditional Chinese) with the key numbers and the integration hook.
