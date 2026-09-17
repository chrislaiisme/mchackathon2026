# Quantified Validation

The brief explicitly scores whether the feedback loop is "量化可驗證" (quantifiably verifiable), so "feels more accurate" isn't enough — this doc lays out the three layers of actual numbers, per [hackathon-brief.md](hackathon-brief.md) "量化驗證" section.

## 1. Offline (computed before the event, goes in the deck/README)

- **ENGINE01 slot-filling accuracy**: hand-label 30–50 consumer-sentence test cases with the expected structured intent, run them, report % of slots filled correctly. Starter implementation: [`backend/engine01_intent/tests/`](../backend/engine01_intent/tests/) (currently a 10-sentence seed set — expand before quoting the number).
- **ENGINE02 ablation**: same test queries run through keyword-only search, embedding-only search, and hybrid+rerank; compare Precision@5 / NDCG@5 across the three, chart it. Owner: ENGINE02.

## 2. Live / on-stage (shown during the actual demo)

A "match score" — how well the current results satisfy the current structured intent (e.g. fraction of requested color/occasion/budget conditions actually met). Shown once before feedback, once after ENGINE03 reprocesses it — e.g. "符合度：62% → 89%" on screen. This is the field `RetrievalResult.match_score` in [interface-contract.md](interface-contract.md). Owner: ENGINE02/03 + frontend, jointly.

## 3. Development-time simulated-user loop (never shown live)

Validates both the retrieval branch and the generation branch against real target images, using FashionCLIP similarity as the score, per [validation-flow.svg](validation-flow.svg):

1. Pick a hidden target image from the team's curated Pinterest board.
2. GPT-4o describes it in a few keywords — this description is the simulated user's hidden persona (never revealed to the system under test).
3. A simulated LLM user opens with one deliberately vague sentence (can't leak the hidden keywords), runs 2–4 rounds against the *same* ENGINE01–03 code as the live demo, adjusting its feedback each round based on the gap to its hidden target.
4. Each round, score the system's output (both the recommended product image and the generated concept image) against the target via FashionCLIP cosine similarity.
5. Repeat across 30–50 target images, average, and plot similarity-over-rounds — this convergence chart is the headline quantified result for the deck.

**Two things to keep honest**: this is an automated simulation, not a real-user study — label it that way in the deck. And Pinterest source images used as hidden targets are for internal scoring only, never shown in the demo or slides.

**Image-generation budget**: 30–50 targets × 2–4 rounds × 2 branches (recommended + generated) ≈ 60–200 image-generation calls. Run this on day 1 of the two on-site days, not day 2, so it doesn't eat into the quota needed for the live demo. See root `CLAUDE.md` "P0 action item" for the underlying API-key/budget dependency this whole loop needs.

Owner: combined with the generation/Pinterest line, per the team's 5-people-for-6-lines split. Code: [`validation/`](../validation/).
