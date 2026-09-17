# ENGINE01 — Intent Understanding

One sentence → structured intent JSON (item type, color, occasion, budget, style keywords, ...), with system-inferred fields labeled separately from what the user actually said, plus clarifying multiple-choice questions when the intent is still too sparse to search on.

Full spec and design rationale: [../../docs/engine01-intent.md](../../docs/engine01-intent.md). Cross-engine JSON contract: [../../docs/interface-contract.md](../../docs/interface-contract.md).

## Run locally

From the repo root:

```bash
pip install -r backend/requirements.txt
cp .env.example .env   # fill in OPENAI_API_KEY -- see CLAUDE.md "P0 action item"
uvicorn backend.engine01_intent.main:app --reload
```

Try it:

```bash
curl -X POST http://127.0.0.1:8000/intent \
  -H "Content-Type: application/json" \
  -d "{\"message\": \"我想要件簡約風格的黑色外套\"}"
```

## Files

- `main.py` — FastAPI app, `POST /intent`.
- `llm_client.py` — OpenAI structured-output call (`extract_intent`).
- `session_store.py` — in-memory per-session state (no DB).
- `prompts.py` — the system prompt driving extraction / inference / clarifying questions.
- `tests/test_cases.json` + `tests/test_accuracy.py` — offline slot-filling accuracy check (starter set of 10 sentences; expand to 30-50 before quoting the number in the deck).

## Offline accuracy check

```bash
python -m backend.engine01_intent.tests.test_accuracy
```

Requires `OPENAI_API_KEY` to be set (makes one real API call per test sentence).
