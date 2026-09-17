# Frontend

**Owner: not yet assigned.** This is a scaffold summary pulled from [hackathon-brief.md](hackathon-brief.md) — the assigned owner should expand this into a real spec (component breakdown, state management, exact wireframe) rather than treating this file as final.

## Stack

React + Vite. No Next.js/SSR — the surface area is an input box, result cards, an intent panel, and feedback controls, not a full app framework's worth of complexity. Tailwind or a component library is fine for speed on cards/layout.

## Screens / components (from the brief)

- **Input**: text box (voice input is an optional stretch — needs a recorder component + a backend speech-to-text step; drop it without affecting the rest of the flow if there's no time). Optional reference-image upload.
- **Intent panel**: renders the current structured `Intent`, with `inferred_fields` visibly distinguished from user-stated fields (e.g. an "system inferred" badge) — this *is* the explainability requirement made visible, don't just log it to console.
- **Clarifying questions**: multiple-choice options + a free-text fallback, reused every round, not just round 1.
- **Result cards**: recommended products (`ProductCard[]`, each with its GPT-written reason) side by side with the generated concept image (`ConceptImage`), plus the current `match_score`.
- **Feedback controls**: per-attribute scoring (color/fit/pattern/collar), scored separately for the recommended item vs. the concept image.
- **Round comparison**: round N vs. round N-1 shown side by side or otherwise clearly contrasted, with the `match_score` change highlighted (e.g. "62% → 89%") — this is the on-stage payoff of the whole feedback loop, make sure it's not buried.

## Talks to

FastAPI backend over REST (WebSocket only if a module actually needs streaming). See [interface-contract.md](interface-contract.md) for the exact JSON shapes (`IntentRequest`/`IntentResponse`, `RetrievalResult`, `FeedbackInput`).
