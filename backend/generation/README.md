# Generation — Concept Image

**Owner: not yet assigned (proposed to be combined with `pinterest/`, see docs/pinterest-and-generation.md).** Placeholder folder created as part of the repo scaffold so this line can start immediately.

Produces one original concept image per round from the current `Intent`, using OpenAI's Responses API `image_generation` tool (`action: "auto"`, chained across rounds via `previous_response_id` so the model can see the prior image plus this round's feedback instead of starting over). Prompts must stay abstract (color/cut/occasion/material) and avoid naming real brands or designers. How many rounds run is driven entirely by user feedback in the live demo (not the model deciding to stop); the offline validation loop instead fixes 2–4 rounds per target image, using FashionCLIP similarity as the quantified stopping signal.

Full spec: [../../docs/pinterest-and-generation.md](../../docs/pinterest-and-generation.md). Output JSON: `ConceptImage` inside `RetrievalResult` in [../../docs/interface-contract.md](../../docs/interface-contract.md).

Depends on `OPENAI_API_KEY` (see root `CLAUDE.md` "P0 action item"). Sample code is in [../../docs/hackathon-brief.md](../../docs/hackathon-brief.md) under "評分怎麼具體變成下一次生成的修正".
