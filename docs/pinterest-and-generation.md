# Pinterest Trend Signal & Concept Image Generation

**Owner: Pinterest board curation is 品諭 (per the planning doc); code ownership for both modules otherwise not yet assigned.** This is a scaffold summary pulled from [hackathon-brief.md](hackathon-brief.md) — the assigned owner should expand this into a real spec rather than treating this file as final. These two are combined into one line per the team's 5-people-for-6-lines split (Pinterest work is front-loaded before the event; on-site effort shifts to the generation loop).

## Pinterest trend signal

Pinterest API v5 Trial access only reads/searches the connected account's own pins/boards — it cannot keyword-search the public site (that needs a partner/beta endpoint with an unpredictable approval timeline, not viable in two weeks). The actual approach: the team manually curates a board with target/trend images, and the app reads that board via Trial access. This still counts as integrating the Pinterest API; the "search" step is just done by a human up front instead of live.

This is a supplementary signal into ENGINE02's ranking weights (and ENGINE03's preference model) — a "recent trend" boost, not a replacement for the Polyvore product catalog. The user-facing product never names "Pinterest" directly. Raw Pinterest images are for internal similarity computation only — never displayed in the live demo or slides (copyright).

## Concept image generation

OpenAI Responses API, `image_generation` tool, `action: "auto"`. Each round's `Intent` becomes an abstract prompt (color/cut/occasion/material — avoid naming real brands/designers, this is being demoed in front of the sponsoring company). Multi-round continuity uses `previous_response_id` so the model sees the prior image plus this round's feedback instead of regenerating from scratch. Sample code is in [hackathon-brief.md](hackathon-brief.md) under "評分怎麼具體變成下一次生成的修正".

How many rounds run in the **live** demo is entirely driven by user feedback (never the model deciding to stop on its own). The **offline validation loop** instead fixes 2–4 rounds per target image and uses FashionCLIP similarity as a hard-coded stopping signal — see [validation-plan.md](validation-plan.md).

The generated image is also converted to a FashionCLIP embedding and folded into ENGINE02's dense-side score every round, so the generation branch and the retrieval branch reinforce each other instead of running as two disconnected features.

## Dependencies

`OPENAI_API_KEY` (generation), `PINTEREST_ACCESS_TOKEN` (Pinterest reads) — both in `.env.example`.
