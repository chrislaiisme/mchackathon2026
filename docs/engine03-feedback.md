# ENGINE03 — Preference Feedback Loop

**Owner: not yet assigned.** This is a scaffold summary pulled from [hackathon-brief.md](hackathon-brief.md) — the assigned owner should expand this into a real spec rather than treating this file as final.

## Goal

Turn a round's feedback into a structured correction that measurably improves the next round — this is the engine the competition's live evaluation is built around (judge gives a prompt → sees a result → gives feedback → gives a second prompt → checks whether the system actually got closer). "量化可驗證" (quantifiably verifiable) is explicitly called out in the brief as a scoring factor for this engine specifically.

## Input

Free-text feedback plus per-attribute scores (color / fit / pattern / collar), scored **separately** for the recommended product and the generated concept image — not one combined score. Finer-grained feedback lets ENGINE03 adjust more precisely and lets the frontend show exactly which attribute the user was unhappy with (reinforces "可解釋").

## Processing

GPT structured output (chat completions, no LangChain) turns the free-text + per-attribute scores into structured weight adjustments / intent corrections.

## Output

Updated `Intent` and a list of `WeightAdjustment`s that re-trigger ENGINE01/02/generation for the next round. The loop keeps running until the user is satisfied — not a fixed two rounds — but the live demo should show at least round 1 vs. round 2 side by side.

## Interface

In: `FeedbackInput`. Out: `FeedbackResult` (`updated_intent`, `weight_adjustments`) — see [interface-contract.md](interface-contract.md).

## Making the loop verifiable on stage

Define a "match score" (`RetrievalResult.match_score`): how well the current results match the current structured intent (e.g. fraction of the requested color/occasion/budget conditions actually met by the recommended list). Show it before feedback and again after ENGINE03 reprocesses — e.g. "符合度：62% → 89%" displayed directly on screen. This turns "the feedback loop works" from a claim into a number the judges watch change in real time.

## Dependencies

`OPENAI_API_KEY`.
