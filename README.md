# Consumer Intent Agent

> Working title. Built for the 2026 Meichu Hackathon × Makalot Industrial challenge: *understand the consumer from one sentence*.

A Hermes Agent application that turns a consumer's one-sentence apparel request into structured needs, asks image-based choice questions to uncover preferences the consumer did not say out loud, recommends existing products, generates concept images, and gets more accurate with every round of feedback.

**Status:** repository skeleton only. Application code is written during the event.

## Repository layout

| Path | What it holds | Workstream |
|---|---|---|
| `agent/` | Hermes Profile Distribution: identity, skills, config | Line 4 (packaging), skills by Lines 1–4 |
| `agent/skills/` | One skill per job: intent, need probing, recommendation reasons, concept images, feedback | Lines 1–4 |
| `mcp_servers/` | Tool services the agent calls: product catalog search, trend signals | Line 2 |
| `bff/` | Runtime that embeds Hermes Agent: flow control, choice-image checks, preferences, activity log | Lines 3–4 |
| `web/` | Web front end used in the demo | Line 5 |
| `evals/` | Quantitative validation and the charts it produces | Lines 1–3 |
| `contracts/` | Agreed data formats between modules, plus shared sample data | Line 4 leads, all lines agree |
| `docs/` | Project docs and architecture diagrams, including the migration map at `docs/migration-to-hermes-app.md` | Line 4 |
| `scripts/` | Dev setup and data-processing helpers | Each owning line |
| `data/` | Local-only data that is never committed | Lines 1, 2, 3, 5 |
| `index.html`, `privacy.html`, `styles.css`, `assets/`, `.nojekyll` | Pinterest developer application site, served by GitHub Pages. Already in the repo before this skeleton — leave it in place; the Pinterest app review depends on those URLs staying live. | Line 2 |

## Requirements

- Hermes Agent v0.21.2 or later
- TODO: remaining runtime requirements (Line 4)

## Install

TODO (Line 4). Planned flow:

1. Install Hermes Agent.
2. Install the agent profile: `hermes profile install ./agent --alias`
3. Copy the generated `.env.EXAMPLE` to `.env` in the profile and fill in your own keys.
4. Start the tool services, the runtime, and the web front end.

## Run

TODO (Lines 4 and 5)

## Validation

TODO (Lines 1–3). Charts are written to `evals/results/`. All validation uses automated simulated users, not real user testing.

## Security

See [SECURITY.md](SECURITY.md).
