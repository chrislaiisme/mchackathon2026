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

## P0 status — GPT access for each module

**The team currently only has ChatGPT Plus/Pro subscriptions. Nobody has a platform.openai.com API key yet.** This still matters for ENGINE02 (reason generation), ENGINE03, and the generation module (`image_generation` tool via the Responses API), which do need `OPENAI_API_KEY`. If/when the team decides to get one: create an account at platform.openai.com, generate a key, add a small prepaid balance (whole-hackathon usage is estimated well under US$2, so US$5–10 is generous headroom), and share it out of band — never in a commit or plaintext chat log. Copy `.env.example` to `.env` locally and fill it in; `.env` is gitignored.

**ENGINE01 specifically no longer needs this.** It runs on `codex exec` instead — see below. Don't assume the same is true for the other engines until someone actually wires them up; that decision is theirs to make.

## ENGINE01 runtime: `codex exec`, not an API key

Deliberate choice, made after actually testing both paths: the team wants to avoid spending money, so ENGINE01 shells out to the OpenAI Codex CLI (`codex exec --output-schema`), which rides the developer's ChatGPT Plus/Pro subscription (`codex login`, already authenticated on this dev machine) instead of a billed API key. Zero marginal cost per call, confirmed by testing.

The trade-off, also confirmed by testing, not assumed:

| | `codex exec` (this project's choice) | Direct OpenAI API key |
|---|---|---|
| Cost | $0 | ~$0.001/call |
| Latency | ~8–17 sec/call | ~1–3 sec |
| Tokens per call | ~14,000–20,000 | ~1,500 |

The token cost lands on the team's **shared** Codex usage allowance — the same pool used for AI-assisted coding (Claude Code/Codex) during the two on-site days. ENGINE01 calling this every conversational turn adds up; keep an eye on it, especially close to demo time. If it ever becomes a real problem (quota exhaustion, or 8–17s per turn is too slow for the live demo), the fix is swapping the implementation inside `extract_intent()` in `backend/engine01_intent/llm_client.py` back to a direct OpenAI API call — the function signature and everything calling it stays the same.

Prerequisite on any machine running ENGINE01: `codex` CLI installed and authenticated once via `codex login` (no `OPENAI_API_KEY` involved). No separate Hermes Agent install needed — `codex exec --output-schema` already does native JSON-schema-constrained structured output, which was the thing Hermes's own one-shot mode didn't yet have when checked (open feature request upstream).

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
