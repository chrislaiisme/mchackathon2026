# ENGINE01 — Intent Understanding

Owner: this line's owner (see root `CLAUDE.md` "Owner map"). Code: [`backend/engine01_intent/`](../backend/engine01_intent/).

## Goal

Turn one sentence (text, optionally with an accompanying reference image) into a structured, explainable intent — the input every other engine builds on. Per the brief, the bar is "抽得準＋接得住模糊" (extract accurately *and* handle vagueness gracefully), not literally echoing back the user's words.

## Input

- User's sentence, text or voice (voice needs a speech-to-text step first, e.g. Whisper API — optional, falls back to text-only if there's no time).
- Optional reference image. If absent, the system can fall back to a similar image pulled from the team's curated Pinterest board (handled by `backend/pinterest/`, not this module) as auxiliary context.
- The session's current accumulated `Intent` (from `session_store.py`) — every call is a merge, not a fresh extraction from scratch.

## Output

- Updated `Intent` (see [interface-contract.md](interface-contract.md)) — every field the model changed or inferred, with `inferred_fields` marking anything GPT filled in rather than the user stating outright. This split is the concrete mechanism behind the "可解釋" requirement: nothing in the intent panel is presented as the user's own words unless it actually was.
- `clarifying_questions` — 1–3 multiple-choice questions (each with a free-text fallback option) whenever the intent is still too sparse to search well. Same shape every round, not just the first.

## Context inference

Fields the user didn't mention (weather, season, occasion implied by context, etc.) are filled in by GPT's own reasonable guess and explicitly tagged in `inferred_fields`, kept visually distinct from user-stated fields on the frontend. This directly answers the brief's "AI 像黑盒子" complaint — every inferred field should be traceable to "the system guessed this, here's why," not silently blended into the user's own statement.

## Implementation

- FastAPI service, `POST /intent` (see [`backend/engine01_intent/main.py`](../backend/engine01_intent/main.py)).
- Structured output via `codex exec --output-schema` (OpenAI Codex CLI, shelled out to as a subprocess), riding the developer's ChatGPT Plus/Pro subscription instead of a billed `OPENAI_API_KEY` — a deliberate cost decision, not the original plan. See root [CLAUDE.md](../CLAUDE.md) "ENGINE01 runtime: codex exec" for the measured latency/quota trade-off (~8-17s and ~14-20K shared-quota tokens per call) that came with it, and what to do if it becomes a problem before demo day. The JSON schema handed to Codex is generated straight from the `IntentExtraction` Pydantic model (`intent` + `clarifying_questions`), post-processed to satisfy OpenAI's strict-mode requirements (`additionalProperties: false` and all fields listed as required, at every nesting level) since Pydantic doesn't emit that by default — see `_to_strict_schema()` in `llm_client.py`.
- Multi-turn state: a plain in-memory `dict[session_id, SessionState]` (see `session_store.py`) holding the cumulative `Intent`. Each call sends the current intent + the new sentence and asks the model to return the full updated intent — simpler than introducing a conversation-state framework for a two-day build.

## Offline validation (this engine's quantified number)

`backend/engine01_intent/tests/` — a hand-labeled test set of sentences with expected structured intent, scored by "fraction of expected slots filled correctly" (`test_accuracy.py`). Ships with a 10-sentence starter set; expand to 30–50 before quoting the resulting accuracy % in the deck or README, per [validation-plan.md](validation-plan.md).

## Dependencies

- `codex` CLI installed and authenticated once via `codex login` — no `OPENAI_API_KEY` needed for this module. See root `CLAUDE.md` "ENGINE01 runtime: codex exec."
- `backend/shared/schemas.py` — the `Intent`, `ClarifyingQuestion`, `IntentRequest`, `IntentResponse` models this module both produces and consumes.
