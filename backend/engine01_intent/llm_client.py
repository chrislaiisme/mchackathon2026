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
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field, ValidationError

from backend.engine01_intent.prompts import INTENT_SYSTEM_PROMPT
from backend.shared.schemas import ClarifyingQuestion, Intent

# 這幾個都可以用環境變數覆蓋，預設值對大多數情況已經夠用：
# CODEX_BIN：codex 執行檔路徑或名稱（一般裝好就在 PATH 裡，用預設值 "codex" 即可）。
# CODEX_MODEL：不指定就用 codex 自己設定的預設模型。
# CODEX_REASONING_EFFORT：推理強度，"low" 換取比較快的回應速度。
# CODEX_TIMEOUT_SECONDS：單次呼叫的逾時上限，正常一次要等 8-17 秒，留 90 秒當緩衝。
_CODEX_BIN = os.environ.get("CODEX_BIN", "codex")


def _codex_bin() -> str:
    """The Codex executable as a path subprocess can actually start.

    npm installs `codex` on Windows as `codex.CMD`, and `subprocess.run(["codex", ...])` does not
    apply PATHEXT, so it raises FileNotFoundError even though `codex --version` works in the shell
    (2026-09-20: this turned every /intent into a 500 on the Windows demo machine). shutil.which
    does apply PATHEXT, so resolve first and fall back to the configured name unchanged.
    """
    return shutil.which(_CODEX_BIN) or _CODEX_BIN
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
            _codex_bin(),
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
        # The prompt goes through stdin, never as an argv element: on Windows `codex` is a .CMD shim,
        # so a long multi-line prompt passed as an argument is mangled by cmd.exe and the model
        # receives nothing (2026-09-20: every /intent came back with an empty intent and a generic
        # "ENGINE01 已就緒" note). `codex exec -` reads the prompt from stdin, which is safe.
        cmd.append("-")

        try:
            # 實際呼叫 codex exec 子行程，等它跑完（正常要等 8-17 秒）。
            result = subprocess.run(
                cmd,
                input=prompt,
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


class _ReasonRewriteItem(BaseModel):
    # product_id 要求模型原樣抄一遍（不是靠陣列順序對應），因為 LLM 偶爾會
    # 漏掉或調換順序，用 id 對應才不會把改寫後的理由貼到錯的商品卡上。
    product_id: str
    reason: str


class _ReasonRewriteBatch(BaseModel):
    items: list[_ReasonRewriteItem] = Field(default_factory=list)


_REASON_REWRITE_PROMPT = """你是「一句話讀懂消費者」系統的推薦理由改寫員。

任務：下面每一件商品原本的推薦理由是系統樣板句，可能夾雜內部分數或內部備註
（例如「整體風格和你描述的相近（+1.44）」「為了有足夠結果，放寬了 season 條件」），
使用者看了會覺得莫名其妙。把每一句改寫成一句話（20 字以內），像真人造型師會說的、
使用者看得懂的自然中文——不要出現任何數字分數、百分比、或「放寬條件」「relaxed」
這類系統內部用語。改寫要忠於原本理由的實際內容（原本講顏色符合，改寫後也要講顏色，
不要無中生有加進原本沒有的資訊）。

2026-09-20 補充：下面會附上這位使用者的風格輪廓（onboarding 填的長期偏好、這輪
明確講的顏色／場合／季節／風格關鍵字）——**這不是給你判斷語氣用而已，是要你在
改寫時具體點出來**，讓使用者覺得這句話真的是在跟「他」講話，不是隨便一句通用的
造型師台詞。例如原本樣板句只講「風格相近」，如果使用者這輪講了要「約會」穿、
偏好「簡約」，改寫時就該講成類似「簡約好看，約會穿剛好」，而不是空泛的
「風格貼近你的喜好」——但一樣要忠於原本樣板句實際比對到的內容，不要無中生有
說這件商品符合一個使用者其實沒講、樣板句也沒提到的屬性。

規則：
1. 每件商品的 product_id 要在輸出裡原樣抄一次，不要改動、不要漏掉任何一件。
2. 只輸出結構化資料，不要輸出額外的說明文字。
"""

_REASON_SCHEMA_PATH = Path(tempfile.gettempdir()) / "engine01_reason_rewrite.schema.json"
_REASON_SCHEMA_PATH.write_text(
    json.dumps(_to_strict_schema(_ReasonRewriteBatch.model_json_schema())),
    encoding="utf-8",
)


def rewrite_recommendation_reasons(
    items: list[tuple[str, str]], context: str, profile_context: Optional[str] = None
) -> Optional[dict[str, str]]:
    """把一輪要顯示的 (product_id, 原始樣板理由) 清單，一次 `codex exec` 呼叫全部
    改寫成自然語句，回傳 {product_id: 改寫後理由}。**這是顯示優化，不是關鍵路徑**——
    任何失敗（codex 沒裝好、逾時、輸出格式不對）都回傳 None，呼叫端要保留原本的
    樣板句繼續運作，不能讓 `/recommend` 因為這個失敗掛掉。刻意一次批次送所有理由、
    只呼叫一次 `codex exec`，不是逐張卡片各呼叫一次——一輪最多十幾張卡，逐張呼叫
    會變成十幾次 8-17 秒的等待，demo 現場等不起，也會把團隊共用的 Codex 額度燒很兇
    （見 CLAUDE.md「ENGINE01 執行方式」）。

    `profile_context`（2026-09-20 新增）：這位使用者的長期風格偏好（onboarding
    填的）＋這輪結構化 Intent 的具體欄位（顏色／場合／季節／風格關鍵字），讓改寫
    出來的句子能點名使用者自己的偏好，不是只靠 `context`（原始對話文字）籠統
    判斷語氣——真人測試回饋原本的改寫「有點模板化，沒體現出使用者的特別性」，
    根因是這個函式從來沒有把 Intent／UserProfile 的結構化欄位餵給 LLM，只給了
    已經被壓扁成一句樣板句的 `reason` 跟原始對話字串。省略時維持舊行為。
    """
    if not items:
        return {}

    payload = "\n".join(f"- product_id={pid}：{reason}" for pid, reason in items)
    profile_section = f"\n\n這位使用者的風格輪廓：\n{profile_context}" if profile_context else ""
    prompt = (
        f"{_REASON_REWRITE_PROMPT}\n\n"
        f"使用者這輪在找的東西（給你判斷語氣用，不用逐字複述進理由裡）：\n{context}"
        f"{profile_section}\n\n"
        f"要改寫的理由：\n{payload}"
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        output_path = Path(tmp_dir) / "output.json"
        cmd = [
            _codex_bin(),
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
            str(_REASON_SCHEMA_PATH),
            "--output-last-message",
            str(output_path),
        ]
        if _CODEX_MODEL:
            cmd += ["-m", _CODEX_MODEL]
        # The prompt goes through stdin, never as an argv element: on Windows `codex` is a .CMD shim,
        # so a long multi-line prompt passed as an argument is mangled by cmd.exe and the model
        # receives nothing (2026-09-20: every /intent came back with an empty intent and a generic
        # "ENGINE01 已就緒" note). `codex exec -` reads the prompt from stdin, which is safe.
        cmd.append("-")

        try:
            result = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=_CODEX_TIMEOUT_SECONDS,
            )
            if result.returncode != 0:
                return None
            raw = output_path.read_text(encoding="utf-8").strip()
        except (OSError, subprocess.SubprocessError):
            return None

    try:
        batch = _ReasonRewriteBatch.model_validate_json(raw)
    except (ValueError, ValidationError):
        return None

    return {item.product_id: item.reason for item in batch.items}


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
            _codex_bin(),
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
        # The prompt goes through stdin, never as an argv element: on Windows `codex` is a .CMD shim,
        # so a long multi-line prompt passed as an argument is mangled by cmd.exe and the model
        # receives nothing (2026-09-20: every /intent came back with an empty intent and a generic
        # "ENGINE01 已就緒" note). `codex exec -` reads the prompt from stdin, which is safe.
        cmd.append("-")

        try:
            result = subprocess.run(
                cmd,
                input=prompt,
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
