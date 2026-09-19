# Security

- API keys and login credentials (`.env`, `auth.json`) are never committed. Each person uses their own.
- The Hermes profile installer strips credentials, memories, sessions and logs even if they are accidentally included; do not rely on that — keep them out of the repo.
- Local services bind to `127.0.0.1` only.
- Images saved from Pinterest (trend references and validation targets) stay in `data/` on local machines. They are used internally for similarity scoring and are never published or shown in the demo.
- Generated images must not imitate real brands or designers.
- Report a security problem to the team lead directly instead of opening a public issue.
