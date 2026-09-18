# Consumer Intent Agent

> This file stays in English per the competition's deliverable requirement ("GitHub source + English README"). For the Chinese version, see [README_TW.md](README_TW.md) — keep both in sync when either changes.

A prototype built by team **勢在必得** for **MCHackathon 2026 x Makalot Industrial (聚陽實業)**, on the theme *"Understand the consumer from one sentence."*

Consumer Intent Agent turns a shopper's one-sentence apparel request into a structured, explainable intent, retrieves matching products with a hybrid search + reranker pipeline, generates an original concept image alongside the retrieved products, and improves both across rounds based on user feedback — with the improvement shown as a quantified, verifiable score, not just a claim.

## System overview

The system is two engines plus a generation module, wired together behind a FastAPI backend and a React frontend:

- **ENGINE 01 — Intent Understanding**: one sentence → structured JSON intent (item, color, occasion, budget, style keywords), using GPT structured outputs. Ambiguous fields are inferred and labeled as system-inferred (never silently guessed); unclear intent triggers clarifying multiple-choice questions.
- **ENGINE 02 — Retrieval & Ranking**: hybrid search (FashionCLIP dense embeddings + BM25/attribute sparse filtering) over the [Polyvore Outfits Dataset](https://huggingface.co/datasets/mvasil/polyvore-outfits), reranked with outfit-compatibility and learned preference weights. GPT turns the ranked result into a natural-language reason, grounded in the retrieved item's real attributes.
- **ENGINE 03 — Preference Feedback Loop**: turns free-text and per-attribute feedback (color/fit/pattern/collar, scored separately for recommended vs. generated items) into structured weight/intent adjustments that re-trigger the next round.
- **Generation module**: OpenAI Responses API `image_generation` tool produces an original concept image per round alongside the retrieval results; the image is embedded back into ENGINE 02's dense score so retrieval and generation reinforce each other.
- **Pinterest trend signal**: a team-curated Pinterest board (Trial API access) feeds recent-trend signal into ENGINE 02's ranking weights.

Two separate loops share the same ENGINE 01–03 code: the **live loop** (real user/judge interacting in the browser) and an **offline validation loop** (a simulated LLM user with a hidden target image, used only during development to produce quantified accuracy numbers — never shown in the live demo). See [docs/system-architecture.svg](docs/system-architecture.svg) and [docs/validation-flow.svg](docs/validation-flow.svg).

Full background, scoring criteria, and design rationale: [docs/hackathon-brief.md](docs/hackathon-brief.md). Project instructions for AI coding agents: [CLAUDE.md](CLAUDE.md).

## Repository layout

```
agent/              Hermes profile distribution: identity, skills, config (one-command install)
bff/                Runtime that embeds the Hermes Agent
  engine01_intent/   Intent understanding
  shared/            Cross-engine Pydantic schemas (the interface contract)
  images/            Choice-image generation and checks, concept images
  feedback/          Preference feedback loop
  activity_log/      Which skills and tools each round used
mcp_servers/
  catalog/           Product retrieval: hybrid search + reranker
  trends/            Pinterest trend signal ingestion
web/                Front end
evals/              Simulated-user offline validation loop and its charts
contracts/          Agreed data formats and shared sample data
docs/               All project markdown docs and architecture diagrams
scripts/            Dev setup / data-download helpers
data/               Datasets and Pinterest images (never committed)
```

The project is built and shipped as a Hermes Agent application. If you have an open branch, [docs/migration-to-hermes-app.md](docs/migration-to-hermes-app.md) lists where each of your files moves.

## Getting started

Requirements: Python 3.11+, Node.js 18+.

ENGINE01 runs on the OpenAI Codex CLI riding your ChatGPT Plus/Pro subscription (no API key) — run `codex login` once. Other modules (ENGINE02/03, generation) may need `OPENAI_API_KEY` depending on how their owners implement them — see [CLAUDE.md](CLAUDE.md).

```bash
cp .env.example .env   # fill in OPENAI_API_KEY only if a module you're running needs it
codex login             # one-time, needed for ENGINE01

# backend
pip install -r requirements.txt
uvicorn bff.engine01_intent.main:app --reload

# frontend
cd web && npm install && npm run dev
```

Each module under `bff/` and `mcp_servers/` has its own `README.md` with module-specific run/test instructions.

## Deliverables checklist (per competition brief)

1. Working, interactively demoable prototype.
2. This GitHub repo + English README (reproducibility).
3. 2–3 minute demo video (MP4).
4. Live Q&A and on-the-spot adjustment — no model weights required after the event.

## License

Non-commercial hackathon prototype. Not for production use.
