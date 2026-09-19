"""按下「生成新單品」之後的流程控制。

使用者對 ENGINE 02 撈到的東西不滿意時，一次生六件新單品讓他挑。

**這裡不生圖，也不寫 prompt。** 兩件事都在 `agent/scripts/` 那條線：

    generate_grid.py --mode concepts   寫 prompt、呼叫 Hermes、產出一張六宮格與 manifest
    slice_grid.py                      把六宮格切成六張單品圖，把 bbox 與路徑寫回 manifest

為什麼是六宮格而不是六次生圖：走 Hermes 的 openai-codex provider 一次要 26–48 秒，
六件逐一生成要三四分鐘，現場撐不住；擠在一張圖裡實測 48.4 秒，攤下來每件 8.1 秒。

為什麼用子行程而不是直接 import：Hermes 的 plugin 住在它自己的虛擬環境，prompt 組裝要
import 專案的 engine02（在專案 venv），兩邊依賴沒有交集。介面是 stdout 的 JSON，
跟 ENGINE 01 shell out 給 codex exec 同一套模式。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional

ROOT = Path(os.environ.get("PROJECT_ROOT", Path(__file__).resolve().parents[2]))
GENERATED_ROOT = ROOT / "data" / "generated"
GENERATE_GRID = ROOT / "agent" / "scripts" / "generate_grid.py"
SLICE_GRID = ROOT / "agent" / "scripts" / "slice_grid.py"
TIMEOUT = float(os.environ.get("CONCEPT_IMAGE_TIMEOUT", "300"))
# 版面沒切成的重試次數。切圖的版面檢查沒過時，腳本自己的建議就是「這張不要用，重生一張」。
MAX_ATTEMPTS = int(os.environ.get("CONCEPT_IMAGE_ATTEMPTS", "2"))


class ConceptImageUnavailable(RuntimeError):
    """生圖那條線還沒到位，或這次執行失敗。呼叫端要能照常回應，不是整輪掛掉。"""


def _run(script: Path, args: list[str]) -> dict[str, Any]:
    if not script.is_file():
        raise ConceptImageUnavailable(f"找不到 {script.relative_to(ROOT) if script.is_relative_to(ROOT) else script}")
    # encoding="utf-8" 要明講：text=True 不指定編碼時吃 locale.getpreferredencoding()，
    # Windows 中文地區設定預設是 cp950，但這兩支腳本的輸出（prompt、manifest 裡的
    # varied_label_zh 等）常常帶中文——2026-09-19 在 generate_grid.py 內部呼叫
    # hermes_image.py 那一層就踩過一次這個坑（UnicodeDecodeError 把整次生圖搞掛），
    # 這裡是同一種 subprocess 呼叫模式，先一起補上，不要等它也真的炸過一次才修。
    proc = subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=TIMEOUT, cwd=str(ROOT))
    if proc.returncode != 0:
        raise ConceptImageUnavailable(f"{script.name} 失敗：{(proc.stderr or proc.stdout)[-300:]}")
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1]) if proc.stdout.strip() else {}
    except (ValueError, IndexError):
        return {}


def generate_concepts(session_id: str, round_no: int, intent: dict[str, Any],
                      cells: int = 6, model: Optional[str] = None,
                      dry_run: bool = False) -> dict[str, Any]:
    """對外入口：版面沒切成就重生一張，最多 MAX_ATTEMPTS 次。"""
    last: Optional[ConceptImageUnavailable] = None
    for attempt in range(1, (1 if dry_run else MAX_ATTEMPTS) + 1):
        try:
            return _generate_once(session_id, round_no, intent, cells, model, dry_run, attempt)
        except ConceptImageUnavailable as exc:
            last = exc
            if "版面" not in str(exc):   # 只有版面問題值得重生，其餘照實往上拋
                raise
    raise ConceptImageUnavailable(f"重生 {MAX_ATTEMPTS} 次版面都沒切成：{last}")


def _generate_once(session_id: str, round_no: int, intent: dict[str, Any],
                   cells: int, model: Optional[str], dry_run: bool,
                   attempt: int = 1) -> dict[str, Any]:
    """生一張六宮格並切成六件單品，回傳給前端的形狀。

    `intent` 吃 ENGINE 01 的 `Intent`；第 2 輪起可以改吃 ENGINE 03 的 `updated_intent`，
    型別相同，所以使用者按下按鈕時拿到的是「已經吸收過這輪回饋」的六件。
    """
    out_dir = GENERATED_ROOT / session_id / (f"r{round_no}" if attempt == 1 else f"r{round_no}-retry{attempt}")
    out_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
        json.dump(intent, fh, ensure_ascii=False)
        intent_path = fh.name

    try:
        args = ["--intent", intent_path, "--mode", "concepts", "--session", session_id,
                "--round", str(round_no), "--cells", str(cells), "--out", str(out_dir)]
        if model:
            args += ["--model", model]
        if dry_run:
            args.append("--dry-run")
        _run(GENERATE_GRID, args)
    finally:
        Path(intent_path).unlink(missing_ok=True)

    manifest_path = out_dir / "manifest.json"
    if not manifest_path.is_file():
        raise ConceptImageUnavailable("generate_grid.py 沒有寫出 manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    if dry_run:
        return {"dry_run": True, "prompt_used": manifest.get("prompt", ""),
                "cells": _cells_payload(manifest, sliced=False), "manifest": str(manifest_path)}

    # 切圖；切完 manifest 的每一格會多出 image 與 bbox。
    _run(SLICE_GRID, ["--manifest", str(manifest_path)])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    return {
        "grid_image": _served(manifest.get("grid_image")),
        "prompt_used": manifest.get("prompt", ""),
        "locked": manifest.get("locked_zh") or manifest.get("locked") or {},
        "unresolved": manifest.get("unresolved") or [],
        "cells": _cells_payload(manifest, sliced=True),
        "manifest": str(manifest_path.relative_to(ROOT)),
    }


def _cells_payload(manifest: dict[str, Any], *, sliced: bool) -> list[dict[str, Any]]:
    out = []
    for cell in manifest.get("cells") or []:
        item = {
            "index": cell.get("index"),
            "keywords": cell.get("keywords") or {},
            # 這格相對其他格改了什麼，中文原字，前端可以直接顯示在卡片上。
            "varied_label": cell.get("varied_label_zh") or cell.get("varied_attribute"),
            "prompt_fragment": cell.get("prompt_fragment"),
        }
        if sliced:
            item["image_url"] = _served(cell.get("image"))
            item["check"] = cell.get("check") or {}
        out.append(item)
    return out


def _served(path: Optional[str]) -> Optional[str]:
    """manifest 裡是相對 repo 根目錄的路徑；轉成 BFF 的 /generated/<...> 供前端取用。"""
    if not path:
        return None
    p = Path(path)
    try:
        rel = p.relative_to("data/generated") if not p.is_absolute() else p.relative_to(GENERATED_ROOT)
    except ValueError:
        rel = Path(p.name)
    return f"/generated/{rel.as_posix()}"
