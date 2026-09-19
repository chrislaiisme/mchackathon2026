"""Structured-output client for ENGINE01, backed by the OpenAI Codex CLI.

Shells out to `codex exec --output-schema`, which rides the caller's
ChatGPT Plus/Pro subscription (via `codex login`, already set up on a
dev machine) instead of a separate, billed platform.openai.com API key --
so this has zero marginal cost per call. See CLAUDE.md "ENGINE01 執行方式：
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
from typing import Any, Optional

from pydantic import BaseModel, Field

from backend.engine01_intent.prompts import INTENT_SYSTEM_PROMPT
from backend.shared.schemas import ClarifyingQuestion, Intent

# 這幾個都可以用環境變數覆蓋，預設值對大多數情況已經夠用：
# CODEX_BIN：codex 執行檔路徑或名稱（一般裝好就在 PATH 裡，用預設值 "codex" 即可）。
# CODEX_MODEL：不指定就用 codex 自己設定的預設模型。
# CODEX_REASONING_EFFORT：推理強度，"low" 換取比較快的回應速度。
# CODEX_TIMEOUT_SECONDS：單次呼叫的逾時上限，正常一次要等 8-17 秒，留 90 秒當緩衝。
_CODEX_BIN = os.environ.get("CODEX_BIN", "codex")
_CODEX_MODEL = os.environ.get("CODEX_MODEL")  # optional override, e.g. a faster model
_CODEX_REASONING_EFFORT = os.environ.get("CODEX_REASONING_EFFORT", "low")
_CODEX_TIMEOUT_SECONDS = int(os.environ.get("CODEX_TIMEOUT_SECONDS", "90"))


class IntentExtraction(BaseModel):
    # codex exec 每次呼叫要回傳的完整結構：更新後的意圖 + 這輪要問的澄清問題。
    intent: Intent
    clarifying_questions: list[ClarifyingQuestion] = Field(default_factory=list)


def _to_strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """OpenAI's structured-output strict mode requires every object node to
    set additionalProperties: false and list every property as required
    (nullable types cover the "actually optional" fields) -- Pydantic's
    model_json_schema() doesn't add either by default, at any nesting level
    (including $defs), so this walks the whole tree and fixes it up."""

    # 遞迴走訪整個 JSON schema（包含巢狀的 $defs），把每個「物件」節點
    # 補上 OpenAI strict mode 要求的兩件事：不允許額外欄位、所有欄位都列進 required。
    # 沒補這步的話，丟給 codex exec 會直接被 OpenAI 那邊拒絕，回傳 400 錯誤。
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


# 把處理過的 schema 寫成一個暫存檔案，因為 `codex exec --output-schema` 要吃的是
# 檔案路徑，不能直接傳 JSON 字串。這份 schema 在整個程式執行期間都不會變，
# 所以在模組載入時算好、寫一次檔案就好，不用每次呼叫都重算重寫。
_SCHEMA_PATH = Path(tempfile.gettempdir()) / "engine01_intent_extraction.schema.json"
_SCHEMA_PATH.write_text(
    json.dumps(_to_strict_schema(IntentExtraction.model_json_schema())),
    encoding="utf-8",
)


def extract_intent(message: str, current_intent: Intent) -> IntentExtraction:
    """Merge `message` into `current_intent` via `codex exec`, and return the
    updated intent plus any clarifying questions."""
    # 把 system prompt、目前累積的意圖、這一輪新句子全部串成一個 prompt 字串，
    # 因為 `codex exec` 是單次呼叫，沒有像 chat API 那樣的多輪 messages 陣列可以用。
    prompt = (
        f"{INTENT_SYSTEM_PROMPT}\n\n"
        f"目前累積的結構化意圖（JSON）：\n{current_intent.model_dump_json()}\n\n"
        f"使用者這一輪新說的話：\n{message}"
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        output_path = Path(tmp_dir) / "output.json"
        # 組出實際要執行的指令列。各個 flag 的用意：
        # --skip-git-repo-check：不管呼叫時的工作目錄是不是 git repo 都能跑。
        # --sandbox read-only：這裡只需要文字生成，不給它碰檔案系統的權限。
        # --ephemeral：不要把這次呼叫存成一個持久的 session（我們自己管狀態）。
        # --disable plugins / skill_search：關掉用不到的功能，減少每次呼叫多餘的
        #   context（token），這兩個關掉後實測有明顯省下 token 用量。
        # --output-schema：指定上面產生的 strict-mode schema 檔案路徑。
        # --output-last-message：把最終回覆寫進這個檔案，方便我們讀取乾淨的 JSON
        #   （不用去 parse 終端機那些額外的顯示文字）。
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
            # 實際呼叫 codex exec 子行程，等它跑完（正常要等 8-17 秒）。
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=_CODEX_TIMEOUT_SECONDS,
            )
        except FileNotFoundError as exc:
            # 找不到 codex 這個執行檔，通常代表還沒安裝或不在 PATH 裡。
            raise RuntimeError(
                f"'{_CODEX_BIN}' was not found on PATH. Install the Codex CLI and run "
                "`codex login` once (see backend/engine01_intent/README.md)."
            ) from exc

        if result.returncode != 0:
            # 指令本身執行失敗（例如還沒 codex login、額度用完等），
            # 只取 stderr 最後 2000 字元，避免把一大串錯誤訊息整個丟出來。
            raise RuntimeError(
                f"codex exec failed (exit {result.returncode}): {result.stderr.strip()[-2000:]}"
            )

        # 成功的話，結果已經寫進 output_path 這個檔案，讀出來就是乾淨的 JSON 字串。
        raw = output_path.read_text(encoding="utf-8").strip()

    # 用 Pydantic 驗證＋解析成物件，格式不符 schema 的話這裡會直接丟例外。
    return IntentExtraction.model_validate_json(raw)


def generate_freeform_text(prompt: str, timeout_seconds: Optional[float] = None) -> Optional[str]:
    """呼叫 `codex exec` 拿一段純文字回覆，**不帶** `--output-schema`（不需要
    結構化輸出的場景用這支，例如「幫你搭」找不到 ENGINE02 相容性資料時的
    備援理由，見 style_me.py）。跟 `extract_intent()` 共用同一套零成本機制
    （吃 `codex login` 的訂閱額度，不用 `OPENAI_API_KEY`），但因為只是拿一句
    話當備援用，逾時抓得比 `extract_intent()` 短，失敗直接回傳 `None`，
    不像 `extract_intent()` 那樣丟例外——呼叫端本來就有更陽春的備援文案可以
    退，不值得為了這句話讓整支 API 掛掉。
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        output_path = Path(tmp_dir) / "output.txt"
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
                timeout=timeout_seconds or _CODEX_TIMEOUT_SECONDS,
            )
            if result.returncode != 0:
                return None
            text = output_path.read_text(encoding="utf-8").strip()
            return text or None
        except (OSError, subprocess.SubprocessError):
            return None
