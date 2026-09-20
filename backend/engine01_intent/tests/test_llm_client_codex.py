"""How ENGINE01 invokes the Codex CLI. Both things here were live bugs on the Windows demo
machine on 2026-09-20, and neither failed loudly:

1. `subprocess.run(["codex", ...])` raised FileNotFoundError, because npm installs `codex` as
   `codex.CMD` and CreateProcess does not apply PATHEXT -- every POST /intent answered 500 while
   `codex --version` worked fine in the same shell;
2. the prompt was passed as an argv element. Through the .CMD shim a long multi-line prompt is
   mangled, so the model received no user message and returned an empty intent with a generic
   「ENGINE01 已就緒」 note -- a silent failure: HTTP 200, and ENGINE02 then recommended shorts for
   「深藍色襯衫」. Sent on stdin (`codex exec -`), the same prompt extracts
   襯衫 / 深藍色 / 面試 / 不要太正式 correctly.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from backend.engine01_intent import llm_client
from backend.shared.schemas import Intent


def _fake_run(seen: dict, payload: dict):
    def run(cmd, **kw):
        seen["cmd"], seen["input"] = list(cmd), kw.get("input")
        out = Path(cmd[cmd.index("--output-last-message") + 1])
        out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, "", "")
    return run


def test_the_prompt_goes_on_stdin_not_in_argv(monkeypatch):
    seen: dict = {}
    monkeypatch.setattr(subprocess, "run", _fake_run(seen, {"intent": Intent().model_dump(),
                                                            "clarifying_questions": []}))
    llm_client.extract_intent("我想找面試穿的深藍色襯衫，不要太正式", Intent())
    assert seen["cmd"][-1] == "-", seen["cmd"]
    assert "我想找面試穿的深藍色襯衫" in (seen["input"] or "")
    assert not any("襯衫" in str(a) for a in seen["cmd"]), "the prompt must not be an argv element"


def test_the_executable_is_resolved_so_a_cmd_shim_can_start(monkeypatch):
    monkeypatch.setattr(llm_client.shutil, "which", lambda name: r"C:\npm\codex.CMD")
    assert llm_client._codex_bin() == r"C:\npm\codex.CMD"
    monkeypatch.setattr(llm_client.shutil, "which", lambda name: None)
    assert llm_client._codex_bin() == llm_client._CODEX_BIN      # unchanged when not on PATH


def test_reason_rewrite_and_freeform_also_use_stdin(monkeypatch):
    seen: dict = {}
    monkeypatch.setattr(subprocess, "run", _fake_run(seen, {"items": [{"product_id": "a", "reason": "好看"}]}))
    assert llm_client.rewrite_recommendation_reasons([("a", "整體風格相近（+3.00）")], "面試") == {"a": "好看"}
    assert seen["cmd"][-1] == "-" and "整體風格相近" in seen["input"]
