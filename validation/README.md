# Validation — Offline Simulated-User Loop

**Owner: not yet assigned (proposed to be combined with `backend/generation/`, see docs/pinterest-and-generation.md).** Placeholder folder created as part of the repo scaffold so this line can start immediately.

Dev-time only, never shown in the live demo. Picks a hidden target image from the curated Pinterest set, has GPT-4o describe it as a hidden persona, runs a simulated LLM user through 2–4 rounds against the *same* ENGINE01–03 code as the live demo, and scores each round's output (recommended + generated images) against the target via FashionCLIP cosine similarity. Repeated over 30–50 target images and averaged into a similarity-over-rounds convergence chart — the quantified backing for "the feedback loop works," for the deck/README, per the competition's "量化可驗證" scoring criterion.

Full spec: [../docs/validation-plan.md](../docs/validation-plan.md).

**Image-generation budget note:** this loop needs 60–200 image-generation calls (30-50 targets × 2-4 rounds × 2 branches). Per the planning doc, run this on day 1 of the hackathon, not day 2 — don't let it eat into the quota needed for the live demo.
