# Frontend

**Owner: not yet assigned.** Placeholder folder created as part of the repo scaffold so this line can start immediately.

React + Vite (no Next.js/SSR — the UI is an input box, product/concept-image result cards, an intent panel showing user-stated vs. system-inferred fields, feedback controls with per-attribute scoring, and a round-over-round comparison view). Tailwind or a component library is fine for speed.

Talks to the FastAPI backend over REST (or WebSocket if a module needs streaming). Consumes `IntentResponse`, `RetrievalResult`, and posts `FeedbackInput` — see [../docs/interface-contract.md](../docs/interface-contract.md) for exact shapes and [../docs/frontend.md](../docs/frontend.md) for the screen-level spec.

## Scaffold (once someone starts this line)

```bash
cd frontend
npm create vite@latest . -- --template react
npm install
npm run dev
```
