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
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
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
                      dry_run: bool = False, slot: Optional[str] = None) -> dict[str, Any]:
    """對外入口：版面沒切成就重生一張，最多 MAX_ATTEMPTS 次。"""
    last: Optional[ConceptImageUnavailable] = None
    for attempt in range(1, (1 if dry_run else MAX_ATTEMPTS) + 1):
        try:
            return _generate_once(session_id, round_no, intent, cells, model, dry_run, attempt, slot)
        except ConceptImageUnavailable as exc:
            last = exc
            if "版面" not in str(exc):   # 只有版面問題值得重生，其餘照實往上拋
                raise
    raise ConceptImageUnavailable(f"重生 {MAX_ATTEMPTS} 次版面都沒切成：{last}")


def _generate_once(session_id: str, round_no: int, intent: dict[str, Any],
                   cells: int, model: Optional[str], dry_run: bool,
                   attempt: int = 1, slot: Optional[str] = None) -> dict[str, Any]:
    """生一張六宮格並切成六件單品，回傳給前端的形狀。

    `intent` 吃 ENGINE 01 的 `Intent`；第 2 輪起可以改吃 ENGINE 03 的 `updated_intent`，
    型別相同，所以使用者按下按鈕時拿到的是「已經吸收過這輪回饋」的六件。
    """
    # slot 要進路徑：TOP 跟 BOTTOM 是同一個 session／同一輪同時生的，
    # 不分開就會寫到同一個 r{round} 底下互相覆蓋。
    name = f"r{round_no}" if attempt == 1 else f"r{round_no}-retry{attempt}"
    if slot:
        name = f"{name}-{slot}"
    out_dir = GENERATED_ROOT / session_id / name
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
    forced = False
    try:
        _run(SLICE_GRID, ["--manifest", str(manifest_path)])
    except ConceptImageUnavailable as exc:
        # 版面檢查要求切線落在等分點附近。模型常把六格畫得乾淨、但上下列不等高——
        # 這時切線位置偏掉，格數卻是對的。錯誤訊息會把偵測到與要求的格數都印出來，
        # 兩者相同就表示 gutter 找對了，只是不等分，照切的結果是好的。
        if _counts_match(str(exc)):
            _run(SLICE_GRID, ["--manifest", str(manifest_path), "--force"])
            forced = True
        else:
            raise
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    return {
        "grid_image": _served(manifest.get("grid_image")),
        "prompt_used": manifest.get("prompt", ""),
        "locked": manifest.get("locked_zh") or manifest.get("locked") or {},
        "unresolved": manifest.get("unresolved") or [],
        "cells": _cells_payload(manifest, sliced=True),
        "manifest": str(manifest_path.relative_to(ROOT)),
        # 版面不等分但格數正確時會是 True；六格仍然可用，只是不是等分版面。
        "layout_forced": forced,
    }


# --- TOP / BOTTOM 兩件一起生 -------------------------------------------------

# ENGINE 01 的 intent 只講一個 item_type。使用者按 Design for Me 要的是「上身跟
# 下身都給我幾件 AI 的選擇」，所以另外那一格用一個通用品項補上——這兩個詞在
# engine02 的分類體系裡分別對到 tops / bottoms 這兩個最上層節點。
SLOT_FALLBACK_ITEM_TYPE = {"top": "上衣", "bottom": "褲子"}


def slot_of(item_type: Optional[str]) -> Optional[str]:
    """「牛仔褲」→ "bottom"。翻不出來回 None。

    走 agent/scripts 的 english_item_type（背後是 engine02 的分類體系），不要自己
    另外寫一張同義詞表——那樣會跟檢索那條線講不同的話。
    """
    if not item_type:
        return None
    scripts = str(ROOT / "agent" / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    try:
        from grid_common import english_item_type  # type: ignore[import-not-found]
        _, node_id = english_item_type(item_type)
    except Exception:
        return None
    if not node_id:
        return None
    return {"tops": "top", "bottoms": "bottom", "dresses": "dress"}.get(node_id.split(".")[0])


def plan_slots(intent: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """要生哪幾個 slot、各自用什麼 intent。

    使用者說的那一類保持原樣（連同顏色、材質、版型一起帶著），另一類換成通用品項。
    洋裝是自成一格的品項，不需要再配一件下身，所以只生它自己。
    """
    own = slot_of(intent.get("item_type"))

    if own == "dress":
        # 洋裝在前端跟上衣共用同一個輪播（topOrDressCandidates）。
        return {"top": intent}

    plan: dict[str, dict[str, Any]] = {}
    for slot in ("top", "bottom"):
        plan[slot] = intent if slot == own else _companion_intent(intent, SLOT_FALLBACK_ITEM_TYPE[slot])
    return plan


# 使用者說「深色的寬鬆牛仔褲」時，深色／牛仔布／寬鬆講的是那件褲子，不是要配的上衣。
# 這些欄位只跟被點名的那件單品有關，換到另一格就要丟掉，否則會生出「深色牛仔布上衣」。
_GARMENT_SPECIFIC_FIELDS = ("colors", "material", "fit", "pattern", "collar", "length", "notes")


def _companion_intent(intent: dict[str, Any], item_type: str) -> dict[str, Any]:
    """另一格要用的 intent：換品項，保留場合／季節／風格這種整套共用的脈絡。"""
    companion = {k: v for k, v in intent.items() if k not in _GARMENT_SPECIFIC_FIELDS}
    companion["item_type"] = item_type
    companion["inferred_fields"] = list(intent.get("inferred_fields") or [])
    return companion


def generate_concept_pair(session_id: str, round_no: int, intent: dict[str, Any],
                          cells: int = 6, model: Optional[str] = None,
                          dry_run: bool = False) -> dict[str, Any]:
    """TOP 與 BOTTOM 各一張六格拼圖，兩張同時發出去。

    一張要 26–48 秒，串著跑就是兩分鐘，現場撐不住；兩張並行大約等於一張的時間。
    用執行緒而不是 async 是因為底下是 subprocess.run，等的時候本來就放掉 GIL。

    其中一邊失敗不讓整個請求掛掉——另一邊的六件仍然可用，失敗的那格回 error。
    """
    plan = plan_slots(intent)

    with ThreadPoolExecutor(max_workers=len(plan)) as pool:
        futures = {
            slot: pool.submit(generate_concepts, session_id, round_no, slot_intent,
                              cells, model, dry_run, slot)
            for slot, slot_intent in plan.items()
        }
        out: dict[str, Any] = {}
        for slot, future in futures.items():
            try:
                out[slot] = future.result()
            except ConceptImageUnavailable as exc:
                out[slot] = {"error": str(exc)[:300]}
            except Exception as exc:
                out[slot] = {"error": f"{type(exc).__name__}: {exc}"[:300]}

    if all("error" in slot_out for slot_out in out.values()):
        raise ConceptImageUnavailable("；".join(str(v.get("error")) for v in out.values()))
    return out


def _counts_match(message: str) -> bool:
    """錯誤訊息裡「偵測到 N 欄 × M 列，要求的是 N 欄 × M 列」兩組數字是否相同。"""
    found = re.findall(r"(\d+)\s*欄\s*×\s*(\d+)\s*列", message)
    return len(found) >= 2 and found[0] == found[1]


def _varied_label(cell: dict[str, Any]) -> Optional[str]:
    """這一格被改掉的那些屬性的「值」，優先用生圖端給的中文標籤。

    varied_attribute 可能是一個軸（"length"），也可能是逗號接起來的好幾個軸
    （上衣是 "sleeve_length,neckline"）。要印的是值不是軸名——印軸名的話六張卡
    會長得一模一樣，使用者看不出差在哪。
    """
    label = cell.get("varied_label_zh")
    if label:
        return label

    attribute = cell.get("varied_attribute")
    if not attribute:
        return None

    explicit = cell.get("varied_value")
    if explicit:
        return str(explicit)

    keywords = cell.get("keywords") or {}
    values = [str(keywords[axis]) for axis in
              (a.strip() for a in str(attribute).split(",")) if axis and keywords.get(axis)]
    return " · ".join(values) if values else str(attribute)


def _cells_payload(manifest: dict[str, Any], *, sliced: bool) -> list[dict[str, Any]]:
    out = []
    for cell in manifest.get("cells") or []:
        keywords = cell.get("keywords") or {}
        varied_fields = [
            field.strip()
            for field in str(cell.get("varied_attribute") or "").split(",")
            if field.strip()
        ]
        item = {
            "index": cell.get("index"),
            "keywords": keywords,
            # Only attributes varied by this generated option become preference evidence. Locked
            # intent attributes are not re-counted merely because the user liked the image.
            "design_attributes": {
                field: str(keywords[field]) for field in varied_fields if field in keywords
            },
            # 這格相對其他格改了什麼，前端直接顯示在卡片上。六格差在同一個屬性
            # （varied_attribute，可能是逗號接起來的好幾個軸），所以只印屬性名的話
            # 六張卡會長得一模一樣；要印的是「這格的值」——在 keywords 裡，key 就是屬性名。
            "varied_label": _varied_label(cell),
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
