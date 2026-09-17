# ENGINE01 — Intent Understanding

One sentence → structured intent JSON (item type, color, occasion, budget, style keywords, ...), with system-inferred fields labeled separately from what the user actually said, plus clarifying multiple-choice questions when the intent is still too sparse to search on.

Full spec and design rationale: [../../docs/engine01-intent.md](../../docs/engine01-intent.md). Cross-engine JSON contract: [../../docs/interface-contract.md](../../docs/interface-contract.md).

## Runtime: `codex exec`, not an OpenAI API key

This module calls the model via the OpenAI Codex CLI (`codex exec --output-schema`) instead of the `openai` Python SDK, so it costs nothing beyond your existing ChatGPT Plus/Pro subscription. See root [CLAUDE.md](../../CLAUDE.md) "ENGINE01 runtime: codex exec" for why and the measured trade-off (~8-17s per call, ~14-20K tokens of the team's shared Codex quota per call).

**One-time setup**, before this will work at all:

```bash
codex login
```

(No `OPENAI_API_KEY` needed for this module. Other engines may still need one — see CLAUDE.md.)

## Run locally

From the repo root:

```bash
pip install -r backend/requirements.txt
uvicorn backend.engine01_intent.main:app --reload
```

Try it (the first call will take several seconds — see the latency note above):

```bash
curl -X POST http://127.0.0.1:8000/intent \
  -H "Content-Type: application/json" \
  -d "{\"message\": \"我想要件簡約風格的黑色外套\"}"
```

## Files

- `main.py` — FastAPI app, `POST /intent`.
- `llm_client.py` — `codex exec` structured-output call (`extract_intent`).
- `session_store.py` — in-memory per-session state (no DB).
- `prompts.py` — the system prompt driving extraction / inference / clarifying questions.
- `tests/test_cases.json` + `tests/test_accuracy.py` — offline slot-filling accuracy check (starter set of 10 sentences; expand to 30-50 before quoting the number in the deck). Runs 10 real `codex exec` calls (~2-3 min, some shared-quota usage) -- don't run this repeatedly without reason.

## Offline accuracy check

```bash
python -m backend.engine01_intent.tests.test_accuracy
```

Requires `codex login` to have been run once (see above).
