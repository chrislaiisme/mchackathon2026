# Consumer Intent Agent

> This file stays in English per the competition's deliverable requirement ("GitHub source + English README"). For the Chinese version, see [README_TW.md](README_TW.md) — keep both in sync when either changes.

A prototype built by team **勢在必得** for **MCHackathon 2026 x Makalot Industrial (聚陽實業)**, on the theme *"Understand the consumer from one sentence."*

Consumer Intent Agent turns a shopper's one-sentence apparel request into a structured, explainable intent, retrieves matching products with a hybrid search + reranker pipeline, generates an original concept image alongside the retrieved products, and improves both across rounds based on user feedback — with the improvement shown as a quantified, verifiable score, not just a claim.

## System overview

The system is two engines plus a generation module, wired together behind a FastAPI backend and a React frontend:

- **ENGINE 01 — Intent Understanding**: one sentence → structured JSON intent (item, color, occasion, budget, style keywords), using GPT structured outputs. Ambiguous fields are inferred and labeled as system-inferred (never silently guessed); unclear intent triggers clarifying multiple-choice questions.
- **ENGINE 02 — Retrieval & Ranking** (implemented, `engine02/` + `backend/engine02_retrieval/`): hybrid search (dense embeddings + a from-scratch BM25) over a KAGL apparel catalog, reranked by an additive score where every term's contribution is reported and sums to the final score — that decomposition is the explanation, not a separately-generated one. See [docs/engine02-design.md](docs/engine02-design.md) (full design + experiments) and [docs/engine02-pipeline.md](docs/engine02-pipeline.md) (how to run it).
- **ENGINE 03 — Preference Feedback Loop** (**implemented and wired end-to-end**, `backend/engine03_feedback/`): a rule-based (no LLM) mapping from per-attribute feedback and favorite/dislike/outfit-level signals to weight adjustments. ENGINE01's `POST /feedback` calls it via `engine03_client.py`, distinguishing `source: "catalog"` (real ENGINE02 items) from `source: "generated"` (Design-for-Me concept images, which carry design attributes instead of a catalog id). The frontend submits this automatically each round from a unified `preferenceService` (favorites/dislikes/ratings/outfit likes), no separate "submit feedback" button. See [docs/engine03-feedback.md](docs/engine03-feedback.md) and [docs/status.md](docs/status.md).
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
  engine02_retrieval/  ENGINE02's older HTTP seam. As of 2026-09-20 this has drifted from
                       mcp_servers/catalog/ (see below) — mcp_servers/catalog/ is the one
                       actually running the demo; engine02_retrieval only remains as an
                       import fallback in two scripts/tests. See docs/repo-cleanup-audit.md.
  engine03_feedback/   Preference feedback loop — implemented and wired (see above)
  pinterest/           Pinterest trend signal ingestion
engine02/            ENGINE02's implementation package (kept at repo root on purpose,
                     see CLAUDE.md "Repo 結構" — its own data-path resolution and
                     40+ scripts assume this location)
frontend/            Next.js 16 + React 19 UI ("IntentWeave" — the original plan was
                     React + Vite; the team's actual build used a different stack)
mcp_servers/catalog/ ENGINE02's actual live HTTP entrypoint (`mcp_servers.catalog.main:app`,
                     mounts engine02/'s FastAPI app under /engine02/*) — this is what
                     scripts/start-demo.ps1 / dev_services.py actually launch
bff/images/, agent/scripts/  Concept-image ("Design for Me") generation pipeline: ENGINE01
                     imports bff/images/concept.py directly, which shells out to
                     agent/scripts/generate_grid.py + slice_grid.py (Hermes Agent, WSL2
                     bridge on Windows). Despite living next to the mostly-unused
                     agent/bff/mcp_servers/web/contracts/evals/ parallel "Hermes app"
                     stack (see CLAUDE.md), these specific files ARE part of today's demo.
validation/          Planned offline validation loop — currently just a README, no code yet
scripts/             Dev setup / data-download helpers, ENGINE02's evaluation scripts, and
                     dev_services.py — the cross-platform service launcher (see below)
```

A full audit of what's genuinely unused vs. redundant vs. just misdocumented is in [docs/repo-cleanup-audit.md](docs/repo-cleanup-audit.md).

## Getting started

Requirements: Python 3.11+, Node.js 18+.

ENGINE01 runs on the OpenAI Codex CLI riding your ChatGPT Plus/Pro subscription (no API key) — run `codex login` once. Other modules (ENGINE03, generation) may need `OPENAI_API_KEY` depending on how their owners implement them — see [CLAUDE.md](CLAUDE.md).

```bash
cp .env.example .env   # fill in OPENAI_API_KEY only if a module you're running needs it
codex login             # one-time, needed for ENGINE01

# ENGINE01
pip install -r backend/requirements.txt
```

**ENGINE02 has its own environment** (`pyproject.toml` at the repo root, installed with `uv` — see [backend/engine02_retrieval/README.md](backend/engine02_retrieval/README.md) for the exact commands and why it doesn't share `backend/requirements.txt`) and runs as a separate service on its own port.

Each module under `backend/` has its own `README.md` with module-specific run/test instructions.

### Running the services (2026-09-19, verified working set)

For Windows demo machines, the quickest option is to start the complete stack with one command:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-demo.ps1
```

It starts ENGINE01/02/03, Whisper, Virtual You, and the frontend in the background, reuses ports that are already listening, and writes logs under `data/runtime/logs/`. Use `-WhatIf` to inspect what it would start without changing anything.

The launcher checks these endpoints before returning:

| Service | Port | Purpose |
| --- | ---: | --- |
| ENGINE02 | 8002 | catalog ranking and background, fact-checked recommendation-copy rewrite |
| ENGINE01 | 8000 | login, intent orchestration, feedback, and the browser-safe ENGINE02 rewrite proxy |
| ENGINE03 | 8003 | feedback loop |
| Whisper | 9000 | voice transcription |
| Virtual You | 8081 | person extraction and Try On |
| Frontend | 3000 | Next.js app |

`start-demo.ps1` enables `ENGINE02_REWRITER=codex` by default. Run `codex login` beforehand. The ranking response remains fast: ENGINE01 first shows ENGINE02's template reason, then asks ENGINE02 to fact-check and replace only the card copy in the background. For an offline demo that must skip this optional refinement, explicitly run `powershell -ExecutionPolicy Bypass -File .\scripts\start-demo.ps1 -Engine02Rewriter none`.

The default Codex reasoning setting is `low`, the fastest setting supported by the current default model (`gpt-5.6-luna`). To select an available account model explicitly, pass it only when starting ENGINE02, for example: `powershell -ExecutionPolicy Bypass -File .\scripts\start-demo.ps1 -Engine02CodexModel gpt-5.6-terra -Engine02CodexEffort low`. The launcher deliberately does not inherit old `ENGINE02_CODEX_MODEL` or `ENGINE02_CODEX_EFFORT` values from the terminal, because an unsupported combination makes the optional rewrite fall back to templates.

### Restarting after code or configuration changes

The launcher intentionally reuses an occupied port, so it does **not** reload an already-running process. Stop the affected process in the terminal where it is running (or identify its PID with `Get-NetTCPConnection -State Listen -LocalPort <port>` and use `Stop-Process -Id <pid>`), then run the launcher again. Changes made in this repository require ENGINE01, ENGINE02, and the frontend to be restarted; the other services do not need a restart for an intent/recommendation-only change.

### Resetting one demo account to a first-visit state

This app stores the server-side profile at `data/users/<Google-sub>.json`, browser state under `intentweave.*` local-storage keys, and active conversation state in ENGINE01 memory. It does **not** store or delete the Google account itself.

1. With ENGINE01 stopped, delete one app profile by its login email (the script refuses ambiguous targets and asks PowerShell for confirmation):

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\reset-demo-user.ps1 -Email judge@example.com
   ```

2. In the browser used for the demo, open DevTools → Console at `http://127.0.0.1:3000` and run:

   ```js
   Object.keys(localStorage).filter((key) => key.startsWith("intentweave.")).forEach((key) => localStorage.removeItem(key)); location.reload();
   ```

   Alternatively use DevTools → Application → Storage → **Clear site data** for the local frontend origin.

3. Start ENGINE01 again (or run `start-demo.ps1`) and sign in. The next visit is a new application registration/onboarding. To make Google show another account chooser, sign out of the Google account in that browser or use an incognito window; do not delete the person's actual Google account.

Every service below is a separate long-running terminal. ENGINE02 must be up before ENGINE01 (ENGINE01 calls it directly); the rest can start in any order.

```powershell
# Terminal 1 — ENGINE02 (port 8002, real catalog)
$env:ENGINE02_DEMO="1"; $env:ENGINE02_PUBLIC_BASE="http://localhost:8002/engine02"
.venv-engine02\Scripts\python.exe -m uvicorn mcp_servers.catalog.main:app --port 8002

# Terminal 2 — ENGINE01 (port 8000)
.venv\Scripts\python.exe -m uvicorn backend.engine01_intent.main:app --port 8000

# Terminal 3 — frontend (port 3000)
cd frontend
npm run dev

# Terminal 4 — voice input (optional; only needed for the mic button)
.venv\Scripts\python.exe -m uvicorn backend.whisper_transcription.main:app --host 127.0.0.1 --port 9000

# Terminal 5 — virtual try-on (optional; only needed for the "Try On" feature)
$env:VIRTUAL_TRY_ON_PROVIDER="codex"
.venv\Scripts\python.exe -m uvicorn backend.virtual_you.main:app --host 127.0.0.1 --port 8081
```

Notes:
- `ENGINE02_PUBLIC_BASE` must include the `/engine02` path segment — `mcp_servers.catalog.main:app` mounts the whole API under that prefix, and product-card image URLs built without it 404.
- The frontend needs matching entries in `frontend/.env.local` (not committed — copy from `frontend/.env.example` if present): `NEXT_PUBLIC_API_BASE_URL` for ENGINE01, and `PERSON_EXTRACTION_SERVICE_URL` / `VIRTUAL_TRY_ON_SERVICE_URL` for the virtual-try-on service (Terminal 5) — without those two, Try On returns a clear configuration error instead of echoing the original photo back as a mock success.
- The virtual-try-on service's first `/extract` call downloads a ~973MB background-removal model (`rembg`'s `birefnet-portrait`) to a local cache; the whisper service's first `/transcribe` call downloads the Whisper `small` model. Warm both up well before a live demo, not during one.
- ENGINE02's catalog is loaded into memory once at startup, not re-read per request — if its underlying catalog data changes, restart Terminal 1 to pick it up. ENGINE01 doesn't cache anything from ENGINE02 and needs no changes when that happens.

### One-command start/stop/restart on any OS

The manual per-terminal commands above, and `start-demo.ps1`/`reset-demo-user.ps1` further above, are Windows/PowerShell-only. The team isn't all on Windows, so **`scripts/dev_services.py`** is a cross-platform equivalent (pure Python standard library, no extra dependencies needed) with the same port list and health checks, plus per-service stop/restart that the PowerShell script doesn't have:

```bash
python scripts/dev_services.py start                    # start all 6 services
python scripts/dev_services.py start engine01 engine02   # start just these two
python scripts/dev_services.py status                    # is each service up and healthy?
python scripts/dev_services.py stop frontend              # stop one service
python scripts/dev_services.py restart engine01 --env CORS_ALLOWED_ORIGINS=https://example.com,http://localhost:3000
                                                           # restart with an env var override
                                                           # (used by the remote-demo flow below)
```

Service names: `engine02`, `engine01`, `engine03`, `whisper`, `virtual-you`, `frontend`. Both launchers are kept side by side — use whichever fits your OS.

Notes:
- If a service's port is already listening, `start` detects it and skips launching a duplicate — it's treated as reused, not an error.
- Each service's stdout/stderr goes to `data/runtime/logs/<service>-<port>.stdout.log` / `.stderr.log` — check there first if a service seems stuck after `start`.
- `restart`'s `--env` override only affects that one restart's process environment; it doesn't edit `.env` or persist anywhere.

### Demo it remotely (Cloudflare Quick Tunnel)

Want a judge to open the demo on their own device instead of gathering around your laptop? See **[docs/remote-demo-tunnel.md](docs/remote-demo-tunnel.md)** — it covers installing `cloudflared`, why you must tunnel **both** the frontend and ENGINE01 (tunneling only the frontend does not work, since `NEXT_PUBLIC_API_BASE_URL` is baked into the browser bundle at startup), and the easy-to-miss step of adding the tunnel's URL to Google OAuth's allowed origins before a remote visitor can log in.

## Deliverables checklist (per competition brief)

1. Working, interactively demoable prototype.
2. This GitHub repo + English README (reproducibility).
3. 2–3 minute demo video (MP4).
4. Live Q&A and on-the-spot adjustment — no model weights required after the event.

## License

Non-commercial hackathon prototype. Not for production use.
