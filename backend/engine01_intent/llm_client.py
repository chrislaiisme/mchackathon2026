"""Structured-output client for ENGINE01, backed by the OpenAI Codex CLI.

Shells out to `codex exec --output-schema`, which rides the caller's
ChatGPT Plus/Pro subscription (via `codex login`, already set up on a
dev machine) instead of a separate, billed platform.openai.com API key --
so this has zero marginal cost per call. See CLAUDE.md "ENGINE01 runtime:
codex exec" for the trade-off that came with choosing this deliberately:
each call takes roughly 8-17 seconds and burns ~14,000-20,000 tokens of the
team's *shared* Codex usage allowance (the same pool used for AI-assisted
coding during the hackathon), versus ~1-3 seconds and ~1,500 tokens for a
direct OpenAI API call. Verified working end-to-end (including the nested
clarifying-questions schema) while building this module.

Prerequisite on any machine running this: `codex` CLI installed and
authenticated once via `codex login` (no OPENAI_API_KEY needed).
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from backend.engine01_intent.prompts import INTENT_SYSTEM_PROMPT
from backend.shared.schemas import ClarifyingQuestion, Intent

_CODEX_BIN = os.environ.get("CODEX_BIN", "codex")
_CODEX_MODEL = os.environ.get("CODEX_MODEL")  # optional override, e.g. a faster model
_CODEX_REASONING_EFFORT = os.environ.get("CODEX_REASONING_EFFORT", "low")
_CODEX_TIMEOUT_SECONDS = int(os.environ.get("CODEX_TIMEOUT_SECONDS", "90"))


class IntentExtraction(BaseModel):
    intent: Intent
    clarifying_questions: list[ClarifyingQuestion] = Field(default_factory=list)


def _to_strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """OpenAI's structured-output strict mode requires every object node to
    set additionalProperties: false and list every property as required
    (nullable types cover the "actually optional" fields) -- Pydantic's
    model_json_schema() doesn't add either by default, at any nesting level
    (including $defs), so this walks the whole tree and fixes it up."""

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"].keys())
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(schema)
    return schema


_SCHEMA_PATH = Path(tempfile.gettempdir()) / "engine01_intent_extraction.schema.json"
_SCHEMA_PATH.write_text(
    json.dumps(_to_strict_schema(IntentExtraction.model_json_schema())),
    encoding="utf-8",
)


def extract_intent(message: str, current_intent: Intent) -> IntentExtraction:
    """Merge `message` into `current_intent` via `codex exec`, and return the
    updated intent plus any clarifying questions."""
    prompt = (
        f"{INTENT_SYSTEM_PROMPT}\n\n"
        f"目前累積的結構化意圖（JSON）：\n{current_intent.model_dump_json()}\n\n"
        f"使用者這一輪新說的話：\n{message}"
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        output_path = Path(tmp_dir) / "output.json"
        cmd = [
            _CODEX_BIN,
            "exec",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--ephemeral",
            "--disable",
            "plugins",
            "--disable",
            "skill_search",
            "-c",
            f'model_reasoning_effort="{_CODEX_REASONING_EFFORT}"',
            "--output-schema",
            str(_SCHEMA_PATH),
            "--output-last-message",
            str(output_path),
        ]
        if _CODEX_MODEL:
            cmd += ["-m", _CODEX_MODEL]
        cmd.append(prompt)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=_CODEX_TIMEOUT_SECONDS,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"'{_CODEX_BIN}' was not found on PATH. Install the Codex CLI and run "
                "`codex login` once (see backend/engine01_intent/README.md)."
            ) from exc

        if result.returncode != 0:
            raise RuntimeError(
                f"codex exec failed (exit {result.returncode}): {result.stderr.strip()[-2000:]}"
            )

        raw = output_path.read_text(encoding="utf-8").strip()

    return IntentExtraction.model_validate_json(raw)
