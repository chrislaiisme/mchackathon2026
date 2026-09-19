"""一次生一張六宮格，把 ENGINE01 的 `Intent` 變成六件可比較的單品圖。

為什麼要擠在一張圖裡：走 Hermes 的 openai-codex provider，一次生圖要 26–48 秒，
一件一件生的話一輪六件就是三、四分鐘，現場 demo 撐不住，離線驗證迴圈那 60–200 次
生圖也會把團隊共用的 Codex 額度啃掉一大塊。2026-09-19 實測：六宮格 48.4 秒，
攤下來每件 8.1 秒，是單張逐一生成的 3.2 倍效率（數字見 evals/choice_images/README.md）。

兩種模式：
  variants  選項圖（FR-004）。吃 ENGINE01 的一題 ClarifyingQuestion，把選項畫出來。
            六格只差一個屬性，其餘逐字相同——這是單變因，也是 ENGINE03 能把
            「我選第 3 格」翻成欄位層級調整的前提。
  concepts  概念圖（FR-007）。吃整份 Intent，在使用者沒指定的屬性軸上發散六種可能。

用法（--dry-run 只印 prompt 不生圖，開發時務必先用它，別燒額度）：

  python agent/scripts/generate_grid.py --intent intent.json --mode concepts --dry-run
  python agent/scripts/generate_grid.py --intent intent.json --mode variants \
      --question question.json --session s1 --round 2
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from grid_common import (  # noqa: E402
    ROOT, SOURCE_AXIS, SOURCE_INTENT, Cell, Manifest, _article, axis_values_en,
    baseline_sentence, build_prompt, cell_sources, english_item_type, english_value,
    free_axes, house_style_hash, locked_from_intent)

# 版面對照表：格數 → (欄, 列)。**不留空格**——空白格子生圖模型會自己填東西進去，
# 切出來就是一張莫名其妙的卡片。所以格數湊不到就調整版面或砍選項，不留白。
LAYOUTS: dict[int, tuple[int, int]] = {2: (2, 1), 3: (3, 1), 4: (2, 2), 6: (3, 2)}

# 每個屬性軸怎麼講成一句英文。直接寫 "a midi length" 比 "length: midi" 自然得多，
# 生圖模型對自然語句的遵循度明顯比較好。
AXIS_PHRASE = {
    "length": "{a} {v} length", "fit": "{a} {v} fit", "sleeve_length": "{v} sleeves",
    # sleeveless 不能寫成 "sleeveless sleeves"，_REDUNDANT_NOUNS 會把它改成 "a sleeveless"
    # collar 是 Intent 的欄位名，neckline 是 taxonomy 的軸名，兩個都會走到這裡
    "neckline": "{a} {v} neckline", "collar": "{a} {v} neckline",
    "colors": "{v} colour", "material": "{v} fabric", "pattern": "{a} {v} pattern",
}


# 屬性值裡常常已經含了軸的名詞，再套模板就會疊字。
_REDUNDANT_NOUNS = {"pattern": ("print", "pattern"), "collar": ("neck", "collar"),
                    "sleeve_length": ("sleeve",),
                    "neckline": ("neck", "collar"), "material": ("fabric", "knit", "denim"),
                    "colors": ("colour", "color")}


def _phrase(axis: str, value: str) -> str:
    tpl = AXIS_PHRASE.get(axis, "{a} {v} " + axis.replace("_", " "))
    # 值本身已經帶了那個名詞就不要再加一次（"a floral print pattern"、"a v neck neckline"）。
    # 袖長是特例：sleeveless 是形容詞不是名詞片語，"a sleeveless" 會掛在半空中，要單獨用。
    if any(w in value for w in _REDUNDANT_NOUNS.get(axis, ())):
        tpl = "{v}" if axis == "sleeve_length" else "{a} {v}"
    return tpl.format(a=_article(value), v=value)


def _layout_for(n: int) -> tuple[int, int]:
    if n not in LAYOUTS:
        raise SystemExit(f"沒有 {n} 格的版面可用，可用的是 {sorted(LAYOUTS)}")
    return LAYOUTS[n]


def _cells_variants(question: dict[str, Any], locked: dict[str, str], locked_zh: dict[str, Any],
                    current: Optional[str] = None, current_zh: Any = None
                    ) -> tuple[list[Cell], int, int, str]:
    """選項圖：一題 ClarifyingQuestion → 六格。

    ClarifyingQuestion 的 field 就是變因、options 就是每格、option.id 原樣帶進 manifest，
    使用者點了哪格就直接填進 FeedbackInput.selected_option_id（schemas.py 既有欄位），
    整條回饋迴圈不用為了生圖改任何契約。
    """
    field_name = question.get("field") or ""
    options = question.get("options") or []
    if not field_name or not options:
        raise SystemExit("question.json 要有 field 與 options")

    # 先把每個選項翻成英文。翻不出來就代表這個屬性我們沒有可靠的視覺詞彙，
    # 硬生只會生出一張看不出差別的圖——這種題目該退回文字選項，不是硬出圖。
    drawable: list[tuple[str, str, str]] = []   # (option_id, 中文 label, 英文值)
    undrawable: list[str] = []
    for opt in options:
        label = str(opt.get("label") or "")
        word = english_value(field_name, label)
        (drawable.append((str(opt.get("id") or ""), label, word)) if word
         else undrawable.append(label))
    # 兩個選項翻成同一個英文值，畫出來就是兩格一模一樣——使用者點哪格都對不回原本的選項，
    # 而且白白浪費一格。這通常代表 ENGINE01 這題出得不好（「合身」跟「緊身」對使用者是
    # 兩個選項，對視覺是同一件事），所以報錯讓出題端修，不要默默生。
    seen: dict[str, str] = {}
    collisions: list[str] = []
    for _oid, label, word in drawable:
        if word in seen:
            collisions.append(f"「{seen[word]}」與「{label}」都是 {word}")
        seen[word] = label
    if collisions:
        raise SystemExit(f"選項的視覺詞彙撞號：{'；'.join(collisions)}。"
                         f"同一張圖裡會出現兩格一模一樣，請 ENGINE01 換一組選項。")
    if undrawable:
        raise SystemExit(
            f"這些選項翻不成視覺詞彙，畫不出來：{undrawable}。"
            f"依 bff/images/README.md 的規則，這題應該退回文字選項，或先把詞加進 "
            f"grid_common.py 的對照表再重跑。")

    # 基準格放不放得下，由格數決定：選項數 +1 剛好湊成一個版面就放，否則不放。
    # 放基準格的好處是使用者有個「原本長這樣」可以對照，但它不是必需品。
    n_opts = len(drawable)
    with_baseline = (n_opts + 1) in LAYOUTS
    if not with_baseline and n_opts not in LAYOUTS:
        raise SystemExit(f"{n_opts} 個選項湊不出版面（可用格數 {sorted(LAYOUTS)}），"
                         f"請 ENGINE01 出題時把選項數控制在 2、3、5（含基準格）或 4、6（不含）。")
    n_cells = n_opts + 1 if with_baseline else n_opts
    cols, rows = _layout_for(n_cells)

    cells: list[Cell] = []
    if with_baseline:
        # 基準格要顯示**意圖裡目前的值**，不是「這個屬性沒指定」。變因欄位被排除在鎖死
        # 條件之外（否則會在 prompt 裡講兩次），所以基準句裡沒有它——這格必須自己把它講
        # 回來，不然模型會自己亂挑一個值，使用者就沒有「現在這樣 vs 其他選擇」可以比。
        # 意圖裡本來就沒值（第一輪還沒問過）時才真的留白。
        fragment = ("the baseline garment, unchanged." if not current else
                    f"the current choice: {_phrase(field_name, current)}.")
        kw = {**locked, **({field_name: current} if current else {})}
        cells.append(Cell(index=1, keywords=kw,
                          keyword_sources=cell_sources(kw, locked_zh, field_name, current_zh,
                                                       SOURCE_INTENT),
                          prompt_fragment=fragment, varied_attribute=None,
                          varied_label_zh="目前的選擇" if current else None))
    for i, (opt_id, label_zh, word) in enumerate(drawable, start=len(cells) + 1):
        kw = {**locked, field_name: word}
        cells.append(Cell(
            index=i, keywords=kw,
            keyword_sources=cell_sources(kw, locked_zh, field_name, label_zh),
            prompt_fragment=f"identical to the baseline, EXCEPT {_phrase(field_name, word)}.",
            option_id=opt_id, varied_attribute=field_name, varied_label_zh=label_zh))
    return cells, cols, rows, field_name


def _load_palette(path: Optional[str]) -> list[str]:
    """Pinterest 圖版抽出來的趨勢色。沒給就回空的，顏色軸不啟用。"""
    if not path:
        return []
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [c["name"] for c in data.get("colors", [])]


def _cells_concepts(node_id: Optional[str], locked: dict[str, str], locked_zh: dict[str, Any],
                    n_cells: int, palette: Optional[list[str]] = None,
                    forced_axes: Optional[list[str]] = None) -> tuple[list[Cell], int, int]:
    """概念圖：在使用者沒講的屬性軸上發散。

    軸從 taxonomy 拿（裙子 → bottoms 的 length/fit），已經被使用者指定的軸要排除——
    那些是硬條件，發散它等於無視使用者講的話。
    """
    cols, rows = _layout_for(n_cells)
    axes = [a for a in free_axes(node_id) if a not in locked]
    # 使用者沒指定顏色時，顏色是最值得發散的一軸——同一件衣服換個顏色，觀感差很多。
    # 值不從 taxonomy 來（它沒有顏色軸），而是從 Pinterest 圖版抽出來的趨勢色盤，
    # 這才是 Pinterest 在這條線上的實際用途（見 pinterest_palette.py）。
    if palette and "colors" not in locked:
        axes = ["colors"] + axes
    if forced_axes:
        axes = [a for a in forced_axes if a not in locked]
    if not axes:
        raise SystemExit("沒有可發散的屬性軸（使用者把每個軸都指定了），"
                         "這種情況該走 variants 模式或直接檢索，不需要概念圖。")

    # 把 n 格拆成兩軸的交叉（6 = 3 × 2）。只有一軸可用就退化成單軸取 n 個值。
    combos: list[dict[str, str]] = []
    if len(axes) >= 2 and n_cells >= 4:
        a1, a2 = axes[0], axes[1]
        values = lambda ax: (palette or []) if ax == "colors" else axis_values_en(ax)
        v1, v2 = values(a1), values(a2)
        n1 = next((k for k in (3, 2) if n_cells % k == 0 and len(v1) >= k), None)
        if n1 and len(v2) >= n_cells // n1:
            n2 = n_cells // n1
            # 取值時頭尾都取到，讓六格的差異夠大（全擠在 mini/above-the-knee 這種
            # 相鄰值上，切出來六張看起來會像同一件）。
            pick1 = [v1[round(i * (len(v1) - 1) / (n1 - 1))] for i in range(n1)]
            pick2 = [v2[round(i * (len(v2) - 1) / (n2 - 1))] for i in range(n2)]
            combos = [{a1: x, a2: y} for y in pick2 for x in pick1]
    if not combos:
        a1 = axes[0]
        v1 = (palette or []) if a1 == "colors" else axis_values_en(a1)
        if len(v1) < n_cells:
            raise SystemExit(f"軸 {a1} 只有 {len(v1)} 個值，湊不滿 {n_cells} 格")
        combos = [{a1: v1[round(i * (len(v1) - 1) / (n_cells - 1))]} for i in range(n_cells)]

    cells = []
    for i, combo in enumerate(combos, start=1):
        said = " and ".join(_phrase(ax, val) for ax, val in combo.items())
        kw = {**locked, **combo}
        varied = ",".join(combo)
        cells.append(Cell(index=i, keywords=kw,
                          keyword_sources=cell_sources(kw, locked_zh, varied, None, SOURCE_AXIS),
                          prompt_fragment=f"identical to the baseline, EXCEPT {said}.",
                          varied_attribute=varied))
    return cells, cols, rows


def _hermes_python() -> Path:
    """Hermes 自己的直譯器。不寫死絕對路徑，讓別台機器也能跑。"""
    env = os.environ.get("HERMES_PYTHON")
    if env:
        return Path(env)
    return Path.home() / ".hermes" / "hermes-agent" / "venv" / "bin" / "python"


def _generate(prompt_path: Path, model: str, aspect: str) -> dict[str, Any]:
    """跨行程呼叫 hermes_image.py（理由見那支檔案的 docstring）。"""
    py = _hermes_python()
    if not py.exists():
        raise SystemExit(f"找不到 Hermes 的直譯器：{py}\n"
                         f"裝好 Hermes Agent，或用 HERMES_PYTHON 指定路徑。")
    cmd = [str(py), str(Path(__file__).with_name("hermes_image.py")),
           "--prompt-file", str(prompt_path), "--model", model, "--aspect", aspect]
    # 生圖 26–48 秒是常態，逾時要留足；卡住通常是 OAuth 過期，不是慢。
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    line = (proc.stdout or "").strip().splitlines()
    if not line:
        raise SystemExit(f"hermes_image.py 沒有輸出：\n{proc.stderr[-800:]}")
    return json.loads(line[-1])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--intent", required=True, help="ENGINE01 的 Intent JSON（或 ENGINE03 的 updated_intent）")
    ap.add_argument("--mode", choices=("variants", "concepts"), default="concepts")
    ap.add_argument("--question", help="variants 模式用：一題 ClarifyingQuestion 的 JSON")
    ap.add_argument("--session", default="local")
    ap.add_argument("--round", type=int, default=1)
    ap.add_argument("--cells", type=int, default=6, help="concepts 模式的格數")
    ap.add_argument("--palette", help="Pinterest 趨勢色盤 JSON（pinterest_palette.py 產生）")
    ap.add_argument("--axis", action="append", default=[],
                    help="concepts 模式指定要發散哪幾個軸，可給多個；不給就自動挑")
    ap.add_argument("--model", default="gpt-image-2-low")
    ap.add_argument("--aspect", default="portrait")
    ap.add_argument("--source-engine", default="engine01")
    ap.add_argument("--out", help="輸出資料夾，預設 data/generated/<session>/r<round>")
    ap.add_argument("--dry-run", action="store_true", help="只組 prompt 與 manifest，不生圖")
    args = ap.parse_args()

    intent = json.loads(Path(args.intent).read_text(encoding="utf-8"))
    item_en, node_id = english_item_type(intent.get("item_type") or "")
    if not item_en:
        raise SystemExit(f"item_type「{intent.get('item_type')}」對不到分類體系，無法生圖。"
                         f"先讓 ENGINE01 問清楚品項，或把同義詞補進 engine02 的 taxonomy。")

    question = json.loads(Path(args.question).read_text(encoding="utf-8")) if args.question else None
    if args.mode == "variants" and not question:
        raise SystemExit("variants 模式要 --question")

    # 變因欄位不能同時是鎖死條件，否則同一個屬性會在 prompt 裡講兩次、互相打架。
    varied_field = (question or {}).get("field") if args.mode == "variants" else None
    locked, locked_zh, unresolved = locked_from_intent(
        intent, exclude={varied_field} if varied_field else set())

    if args.mode == "variants":
        # 意圖裡對這個欄位已經有值的話（第 2 輪起很常見），基準格就用它
        raw_current = intent.get(varied_field)
        if isinstance(raw_current, list):
            raw_current = raw_current[0] if raw_current else None
        current = english_value(varied_field, str(raw_current)) if raw_current else None
        cells, cols, rows, varied_field = _cells_variants(question, locked, locked_zh,
                                                          current, raw_current)
    else:
        cells, cols, rows = _cells_concepts(node_id, locked, locked_zh, args.cells,
                                            _load_palette(args.palette), args.axis or None)

    prompt = build_prompt(item_en=item_en, locked=locked, cells=cells,
                          cols=cols, rows=rows, mode=args.mode)

    out_dir = Path(args.out) if args.out else ROOT / "data" / "generated" / args.session / f"r{args.round}"
    out_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = out_dir / "prompt.txt"
    prompt_path.write_text(prompt, encoding="utf-8")

    manifest = Manifest(
        session_id=args.session, round=args.round, mode=args.mode, cols=cols, rows=rows,
        locked=locked, locked_zh=locked_zh, unresolved=unresolved, varied_field=varied_field,
        house_style_hash=house_style_hash(), prompt=prompt, cells=cells,
        source={"engine": args.source_engine, "item_type": intent.get("item_type"),
                "node_id": node_id, "item_en": item_en},
        generation={"model": args.model, "aspect_requested": args.aspect})

    if args.dry_run:
        manifest.save(out_dir / "manifest.json")
        print(prompt)
        print(f"\n[dry-run] {cols}x{rows} = {len(cells)} 格；未解析的字：{unresolved or '無'}")
        print(f"[dry-run] 寫出 {out_dir/'manifest.json'}（沒有生圖，沒有花額度）")
        return 0

    result = _generate(prompt_path, args.model, args.aspect)
    if not result.get("success"):
        manifest.generation |= {"ok": False, "error": result.get("error")}
        manifest.save(out_dir / "manifest.json")
        raise SystemExit(f"生圖失敗：{result.get('error')}")

    # provider 會把圖存進它自己的快取，複製一份進專案，免得快取被清就沒了。
    src = Path(result["image"])
    dst = out_dir / "grid.png"
    shutil.copy2(src, dst)
    manifest.grid_image = str(dst.relative_to(ROOT)) if dst.is_relative_to(ROOT) else str(dst)
    w, h = (result.get("pixel_size") or "x").split("x")[:2]
    manifest.canvas = [int(w), int(h)] if w.isdigit() and h.isdigit() else None
    manifest.generation |= {"ok": True, "seconds": result.get("seconds"),
                            "model": result.get("model"), "quality": result.get("quality"),
                            "size_requested": result.get("requested_size"),
                            "size_returned": result.get("pixel_size"),
                            "provider": result.get("provider"), "cache_path": str(src)}
    manifest.save(out_dir / "manifest.json")
    print(json.dumps({"grid": str(dst), "seconds": result.get("seconds"),
                      "canvas": manifest.canvas, "cells": len(cells),
                      "per_cell_seconds": round((result.get("seconds") or 0) / len(cells), 1),
                      "manifest": str(out_dir / "manifest.json")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
