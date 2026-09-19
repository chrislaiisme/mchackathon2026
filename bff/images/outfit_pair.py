"""按下「AI 幫我搭」之後的流程控制。

**這裡不判斷怎麼搭。** 判斷規則整條都在 `agent/skills/outfit-pairer/SKILL.md`，
執行細節在 `agent/scripts/pair_outfit.py`；這裡只負責用子行程呼叫那支腳本，
把 stdout 最後一行當 JSON 讀回來——跟 `bff/images/concept.py` 呼叫
`generate_grid.py` 同一套模式，理由也一樣：腳本要能跟著 Hermes distribution
單獨發佈，不能被 BFF import。

腳本自己已經有一層退場：codex 失敗、逾時、回傳不合法、或挑了清單外的 id，
一律退回 `tops[0]`／`bottoms[0]`，退出碼仍是 0（見 pair_outfit.py 開頭註解）。
這裡的例外只在腳本本身**跑不起來**時才會丟出來：找不到腳本、逾時到連腳本自己
的退場都來不及印出來、或 stdout 最後一行不是合法 JSON。呼叫端（`bff/main.py`
的 `/outfit-pair`）接住這個例外之後要自己墊第二層退場，因為這顆按鈕的契約是
「永遠 200，退場也要給一組能用的答案」。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("PROJECT_ROOT", Path(__file__).resolve().parents[2]))
PAIR_OUTFIT = ROOT / "agent" / "scripts" / "pair_outfit.py"
# 腳本自己也有 --timeout（預設看 PAIR_OUTFIT_TIMEOUT，45 秒）。這裡改用同一個環境
# 變數名（OUTFIT_PAIR_TIMEOUT）當唯一入口，明確傳給腳本的 --timeout，避免兩層各自
# 設一個逾時、又不一致。
TIMEOUT = float(os.environ.get("OUTFIT_PAIR_TIMEOUT", "60"))
# subprocess.run 的外層逾時要比傳給腳本的 --timeout 寬鬆一些：留這段緩衝，
# 讓腳本自己先判斷逾時、印出退場那行 JSON 再正常退出，而不是被外層直接砍掉、
# 連 JSON 都拿不到——那樣就只能落到 BFF 這層更貧乏的退場。
_SUBPROCESS_BUFFER = 10.0


class OutfitPairUnavailable(RuntimeError):
    """腳本這次沒能給出可用的配對結果（找不到腳本、逾時、或 stdout 不是合法 JSON）。
    呼叫端要能照常回應一組退場結果，不是讓整個請求失敗。"""


def pair_outfit(intent: dict[str, Any], tops: list[dict[str, Any]],
                bottoms: list[dict[str, Any]], *, dry_run: bool = False) -> dict[str, Any]:
    """對外入口：寫暫存輸入檔、呼叫 pair_outfit.py、回傳它 stdout 最後一行的 JSON。

    回傳形狀是 `{top_id, bottom_id, reason, source}`；`source` 可能是腳本自己判斷
    出來的 `"llm"`，也可能是腳本內建退場給的 `"fallback"`——兩種都算「腳本跑成功」，
    id 合不合法交給呼叫端驗證（這裡不重複驗證一次，單一職責）。
    """
    if not PAIR_OUTFIT.is_file():
        raise OutfitPairUnavailable(f"找不到 {PAIR_OUTFIT}")

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
        json.dump({"intent": intent, "tops": tops, "bottoms": bottoms}, fh, ensure_ascii=False)
        input_path = fh.name

    try:
        args = [sys.executable, str(PAIR_OUTFIT), "--input", input_path, "--timeout", str(TIMEOUT)]
        if dry_run:
            args.append("--dry-run")
        try:
            proc = subprocess.run(args, capture_output=True, text=True,
                                  timeout=TIMEOUT + _SUBPROCESS_BUFFER, cwd=str(ROOT))
        except subprocess.TimeoutExpired as exc:
            raise OutfitPairUnavailable(
                f"pair_outfit.py 超過 {TIMEOUT + _SUBPROCESS_BUFFER:.0f} 秒沒回來") from exc
    finally:
        Path(input_path).unlink(missing_ok=True)

    if proc.returncode != 0:
        # 腳本正常情況一律退出碼 0；非零代表輸入本身不合法（例如 tops/bottoms
        # 濾掉沒有 id 的項目後變成空的）。這裡傳進去的清單已經是 bff/main.py
        # 用 pydantic 驗過的，理論上不會走到——真的發生就當腳本跑不起來處理。
        raise OutfitPairUnavailable(
            f"pair_outfit.py 失敗（exit {proc.returncode}）：{(proc.stderr or proc.stdout).strip()[-300:]}")

    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError) as exc:
        raise OutfitPairUnavailable("pair_outfit.py 的 stdout 最後一行不是合法 JSON") from exc
