# Pinterest — Trend Signal Ingestion

**Owner: 品諭 (board curation, per the planning doc) — code ownership otherwise not yet assigned.** Placeholder folder created as part of the repo scaffold so this line can start immediately.

Pinterest API v5 Trial access can only read/search the team's own account (pins/boards), not the public site — the partner-level search endpoint needs approval that won't land in two weeks. The actual approach: manually curate a team board with the desired trend/target images, then read that board's pins via Trial access. This is still "integrating the Pinterest API," just with a hand-curated source instead of live keyword search. The resulting signal feeds ENGINE02's ranking weights (never shown to the end user as "Pinterest" by name) and supplies the hidden target images for the offline validation loop (see `validation/`).

Full spec: [../../docs/pinterest-and-generation.md](../../docs/pinterest-and-generation.md).

Depends on `PINTEREST_ACCESS_TOKEN` (`.env.example`). Reminder from the brief: raw Pinterest images are for internal similarity scoring only — never display them directly in the live demo or slides (copyright).
