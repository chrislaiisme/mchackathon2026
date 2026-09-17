# ENGINE03 — Preference Feedback Loop

**Owner: not yet assigned.** Placeholder folder created as part of the repo scaffold so this line can start immediately.

Takes free-text feedback plus per-attribute scores (color/fit/pattern/collar — recommended products and the generated concept image scored separately) and turns them into structured weight adjustments / intent corrections via GPT structured output (no LangChain). The result re-triggers ENGINE01/02/generation for the next round. This loop is what needs to be demonstrably quantified on stage — see the `match_score` field in `RetrievalResult` (before → after feedback, e.g. "62% → 89%").

Full spec: [../../docs/engine03-feedback.md](../../docs/engine03-feedback.md). Input/output JSON: [../../docs/interface-contract.md](../../docs/interface-contract.md) (`FeedbackInput` in, `FeedbackResult` out).

Depends on `OPENAI_API_KEY` (see root `CLAUDE.md` "P0 status").
