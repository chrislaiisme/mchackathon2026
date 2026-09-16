"""LLM backends for the explanation paraphrase. Returns None when nothing is configured,
in which case ENGINE 02 uses template sentences (fully functional, just less fluent).

OpenAI: Responses API (`client.responses.create(model, instructions, input).output_text`),
key from OPENAI_API_KEY (environment or a `.env` file at the repo root).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[1]


def load_dotenv(path: Path = REPO_ROOT / ".env") -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def openai_llm(model: str | None = None, temperature: float = 0.0) -> Callable[[str], str] | None:
    load_dotenv()
    if not os.environ.get("OPENAI_API_KEY"):
        return None
    from openai import OpenAI

    client = OpenAI()
    model = model or os.environ.get("ENGINE02_LLM_MODEL", "gpt-4o-mini")

    def call(prompt: str) -> str:
        resp = client.responses.create(model=model, input=prompt, temperature=temperature)
        return resp.output_text

    return call


def get_llm(backend: str = "auto") -> Callable[[str], str] | None:
    """auto = OpenAI if a key exists, else templates. The local model is opt-in only
    (it is slow on CPU and should not be loaded silently during a live demo)."""
    if backend in ("auto", "openai"):
        return openai_llm()
    if backend == "local":
        try:
            from .local_llm import local_llm  # added after model verification

            return local_llm()
        except Exception:
            return None
    return None
