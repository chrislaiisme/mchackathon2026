# CLAUDE.md

Project instructions for AI coding agents (Claude Code, Codex, etc.) working in this repo. Read this first; it links out to `docs/` for full detail instead of duplicating it.

## What this is

**Consumer Intent Agent** — prototype for **MCHackathon 2026 x Makalot Industrial (聚陽實業)**, team **勢在必得**. Theme: *"一句話讀懂消費者" (understand the consumer from one sentence)*. Competition day: **2026-09-19**. Full background: [docs/hackathon-brief.md](docs/hackathon-brief.md).

Deliverables: (1) working interactive prototype, (2) this repo + English README, (3) a 2–3 min demo video, (4) live Q&A / on-the-spot adjustment.

Scoring (100%): problem understanding & fit 35% · technical approach & data use 35% · demo completeness & feasibility 20% · presentation & improvisation 10%. The judges explicitly said they weigh the **first two** items most — insight into consumer behavior and technical soundness matter more than production polish. Judges run a live loop: give a prompt → look at the result → give feedback → give a second prompt → check whether the system actually improved. That loop is what ENGINE 03 exists to make verifiable, not just claimed.

## System architecture

Two loops share the same ENGINE 01–03 code:

- **Live loop** (real user/judge, in the browser): [docs/system-architecture.svg](docs/system-architecture.svg). User sentence → ENGINE 01 (structured intent) → ENGINE 02 (retrieval) and the generation module run **in parallel**, both fed by the same intent → results shown side by side → user feedback → ENGINE 03 → next round. Runs until the user is satisfied; not fixed at 2 rounds.
- **Validation loop** (dev-time only, never shown in the live demo): [docs/validation-flow.svg](docs/validation-flow.svg). A simulated LLM user with a hidden target-image persona drives 2–4 rounds against the same ENGINE 01–03 code; FashionCLIP cosine similarity to the target image is the quantified convergence metric. Produces the numbers that back up "the feedback loop is verifiable" in the pitch.

Three engines, one generation module, one trend-signal ingestion:

| Module | Owns | Core tech | Folder |
|---|---|---|---|
| ENGINE01 | Intent understanding | GPT structured output, FastAPI | `backend/engine01_intent/` |
| ENGINE02 | Retrieval & ranking | FashionCLIP + BM25 hybrid search, reranker, Polyvore Outfits Dataset | `backend/engine02_retrieval/` |
| ENGINE03 | Feedback → weight/intent updates | GPT structured output | `backend/engine03_feedback/` |
| Generation | Concept image per round | OpenAI Responses API `image_generation` tool | `backend/generation/` |
| Pinterest | Trend signal into ENGINE02/03 | Curated board, Pinterest API v5 Trial access | `backend/pinterest/` |
| Frontend | UI | React + Vite | `frontend/` |
| Validation | Offline quantified metrics | Simulated user + FashionCLIP similarity | `validation/` |

No LangChain / LlamaIndex anywhere — every module calls the GPT API directly (chat completions structured output, or Responses API for image generation). This was a deliberate decision in the planning doc, not an oversight.

## Repo layout

```
index.html, privacy.html, styles.css, assets/, .nojekyll   # existing GitHub Pages site — DO NOT touch, see below
README.md              English, top-level (competition deliverable #2)
CLAUDE.md              this file
docs/                  ALL markdown docs + architecture diagrams live here
backend/
  shared/              cross-engine Pydantic schemas — the interface contract, code form
  engine01_intent/      \
  engine02_retrieval/    | one folder per engine/module, see table above
  engine03_feedback/    /
  generation/
  pinterest/
  requirements.txt      one shared requirements file for all of backend/
frontend/               React + Vite
validation/             simulated-user validation loop scripts
scripts/                dev helper scripts (e.g. dataset download)
```

**Do not restructure or remove the root-level `index.html` / `privacy.html` / `styles.css` / `assets/` / `.nojekyll`.** They're the Pinterest-app-review privacy policy site. GitHub Pages actually serves from the separate `gh-pages` branch (`chrislaiisme.github.io/mchackathon2026/`), so these files on `main` are currently just historical — but don't delete them without checking with the team first, and never push to `gh-pages` without confirming.

## P0 action item — before any GPT/image-generation code can run

**The team currently only has ChatGPT Plus/Pro subscriptions. Nobody has a platform.openai.com API key yet.** Every module that calls structured output or the `image_generation` tool (ENGINE01, ENGINE02's reason generation, ENGINE03, generation) needs `OPENAI_API_KEY` set. Someone on the team needs to:

1. Create an account at platform.openai.com and generate an API key.
2. Add a small prepaid balance — the whole hackathon is estimated at well under US$2 of usage, so US$5–10 is generous headroom.
3. Share the key with the team out of band (password manager / encrypted channel) — never in a commit, chat log in plaintext if avoidable, or issue.
4. Everyone copies `.env.example` to `.env` locally and fills in `OPENAI_API_KEY`. `.env` is gitignored.

**Fallback if nobody wants to add billing:** the planning doc validated Hermes Agent riding ChatGPT Plus/Pro's Codex-auth usage pool for **batch image generation only** (`docs/hackathon-brief.md`, "量化驗證" section) — explicitly documented upstream as best-effort, not a supported path. It has not been validated for ENGINE01's text structured-output extraction, which is called every conversation turn and is latency-sensitive. Don't default to it for ENGINE01 unless the API key route is genuinely a dead end.

## Interface contract

`backend/shared/schemas.py` is the code-level source of truth for the JSON that flows between engines (structured intent, feedback delta, product card, etc.) — defined so all lines can build in parallel without waiting on each other. See [docs/interface-contract.md](docs/interface-contract.md) for the written spec. Anyone changing a field name/type there should flag it to the other engine owners before merging, since ENGINE02/03/frontend all depend on it.

## Git workflow

- `main` is the shared branch; everyone else's work up to now is the GitHub Pages site content — treat it as-is.
- One branch per line, proposed convention (not yet confirmed by the whole team): `engine01-intent`, `engine02-retrieval`, `engine03-feedback`, `frontend`, `pinterest-generation`.
- `git worktree` is an optional local technique (check out multiple branches into sibling folders on one machine) mentioned in the planning doc — useful if you want to run multiple agents on different branches at once, not required for normal single-branch work.
- Pushing to the shared remote or opening a PR always gets confirmed with the user first — it's visible to the other four teammates.

## Owner map

- ENGINE01 (intent understanding): this working directory's owner.
- Pinterest board curation: 品諭 (per planning doc).
- ENGINE02, ENGINE03, frontend, generation module: not yet assigned in the docs — fill in as confirmed.

## Environment notes

- This repo lives under OneDrive (`...\OneDrive\桌面\Hackathon`). OneDrive's sync client can lock files mid-write or delay a freshly-written file's availability (observed directly while scaffolding this repo: right after `pip install`, importing the openai SDK's `jiter` dependency threw a `DLL load failed` error once, then imported fine on the very next attempt — classic file-not-fully-hydrated-yet symptom). If `pip install` / `npm install` / `git` operations act flaky right after writing a lot of files (e.g. `frontend/node_modules`), retry once before assuming it's a real bug. If it keeps happening, exclude this folder from OneDrive sync rather than moving the repo.
- Backend: Python 3.11+, one shared `backend/requirements.txt` — don't create a separate venv/requirements per engine, the two-day hackathon timeline doesn't leave room for reconciling five environments.
- Frontend: React + Vite, no Next.js/SSR — the UI is an input box, result cards, an intent panel, and feedback controls, not a full app framework's worth of complexity.

## Where to look for more detail

- Full competition brief, scoring, and design-rationale history: [docs/hackathon-brief.md](docs/hackathon-brief.md)
- PRD skeleton: [docs/prd.md](docs/prd.md)
- Per-module specs: `docs/engine01-intent.md`, `docs/engine02-retrieval.md`, `docs/engine03-feedback.md`, `docs/frontend.md`, `docs/pinterest-and-generation.md`
- Quantified validation design: [docs/validation-plan.md](docs/validation-plan.md)
