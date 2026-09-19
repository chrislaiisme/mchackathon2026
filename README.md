# Consumer Intent Agent

> This file stays in English per the competition's deliverable requirement ("GitHub source + English README"). For the Chinese version, see [README_TW.md](README_TW.md) — keep both in sync when either changes.

A prototype built by team **勢在必得** for **MCHackathon 2026 x Makalot Industrial (聚陽實業)**, on the theme *"Understand the consumer from one sentence."*

Consumer Intent Agent turns a shopper's one-sentence apparel request into a structured, explainable intent, retrieves matching products with a hybrid search + reranker pipeline, generates an original concept image alongside the retrieved products, and improves both across rounds based on user feedback — with the improvement shown as a quantified, verifiable score, not just a claim.

## System overview

The system is two engines plus a generation module, wired together behind a FastAPI backend and a React frontend:

- **ENGINE 01 — Intent Understanding**: one sentence → structured JSON intent (item, color, occasion, budget, style keywords), using GPT structured outputs. Ambiguous fields are inferred and labeled as system-inferred (never silently guessed); unclear intent triggers clarifying multiple-choice questions.
- **ENGINE 02 — Retrieval & Ranking** (implemented, `engine02/` + `backend/engine02_retrieval/`): hybrid search (dense embeddings + a from-scratch BM25) over a KAGL apparel catalog, reranked by an additive score where every term's contribution is reported and sums to the final score — that decomposition is the explanation, not a separately-generated one. See [docs/engine02-design.md](docs/engine02-design.md) (full design + experiments) and [docs/engine02-pipeline.md](docs/engine02-pipeline.md) (how to run it).
- **ENGINE 03 — Preference Feedback Loop**: turns free-text and per-attribute feedback (color/fit/pattern/collar, scored separately for recommended vs. generated items) into structured weight/intent adjustments that re-trigger the next round.
- **Generation module**: OpenAI Responses API `image_generation` tool produces an original concept image per round alongside the retrieval results; the image is embedded back into ENGINE 02's dense score so retrieval and generation reinforce each other.
- **Pinterest trend signal**: a team-curated Pinterest board (Trial API access) feeds recent-trend signal into ENGINE 02's ranking weights.

Two separate loops share the same ENGINE 01–03 code: the **live loop** (real user/judge interacting in the browser) and an **offline validation loop** (a simulated LLM user with a hidden target image, used only during development to produce quantified accuracy numbers — never shown in the live demo). See [docs/system-architecture.svg](docs/system-architecture.svg) and [docs/validation-flow.svg](docs/validation-flow.svg).

Full background, scoring criteria, and design rationale: [docs/hackathon-brief.md](docs/hackathon-brief.md). Project instructions for AI coding agents: [CLAUDE.md](CLAUDE.md).

## Repository layout

```
docs/               All project markdown docs and architecture diagrams
backend/
  shared/            Cross-engine Pydantic schemas (the interface contract)
  engine01_intent/   Intent understanding (FastAPI service)
  engine02_retrieval/  ENGINE02's HTTP seam (Intent in, RetrievalResult out; full API mounted at /engine02/*)
  engine03_feedback/   Preference feedback loop
  generation/          Concept image generation
  pinterest/           Pinterest trend signal ingestion
engine02/            ENGINE02's implementation package (kept at repo root on purpose,
                     see CLAUDE.md "Repo 結構" — its own data-path resolution and
                     40+ scripts assume this location)
frontend/            React + Vite UI
validation/          Simulated-user offline validation loop
scripts/             Dev setup / data-download helpers, plus ENGINE02's evaluation scripts
```

## Getting started

Requirements: Python 3.11+, Node.js 18+.

ENGINE01 runs on the OpenAI Codex CLI riding your ChatGPT Plus/Pro subscription (no API key) — run `codex login` once. Other modules (ENGINE03, generation) may need `OPENAI_API_KEY` depending on how their owners implement them — see [CLAUDE.md](CLAUDE.md).

```bash
cp .env.example .env   # fill in OPENAI_API_KEY only if a module you're running needs it
codex login             # one-time, needed for ENGINE01

# ENGINE01
pip install -r backend/requirements.txt
uvicorn backend.engine01_intent.main:app --reload

# frontend
cd frontend && npm install && npm run dev
```

**ENGINE02 has its own environment** (`pyproject.toml` at the repo root, installed with `uv` — see [backend/engine02_retrieval/README.md](backend/engine02_retrieval/README.md) for the exact commands and why it doesn't share `backend/requirements.txt`) and runs as a separate service on its own port.

Each module under `backend/` has its own `README.md` with module-specific run/test instructions.

## Deliverables checklist (per competition brief)

1. Working, interactively demoable prototype.
2. This GitHub repo + English README (reproducibility).
3. 2–3 minute demo video (MP4).
4. Live Q&A and on-the-spot adjustment — no model weights required after the event.

## License

Non-commercial hackathon prototype. Not for production use.
