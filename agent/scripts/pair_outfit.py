"""「AI 幫我搭」——從生好的六件上衣與六件下身裡挑出最搭的一組，並給一句理由。

規則寫在 `agent/skills/outfit-pairer/SKILL.md`，這支只負責執行：讀輸入、組 prompt、
呼叫文字模型、驗證回傳、印出 JSON。判斷標準不要寫在這裡（見 `_rules_text()`）。

文字模型走 `codex exec`，跟 ENGINE01 同一套（吃 `codex login` 的 ChatGPT 訂閱額度，
**不需要** `OPENAI_API_KEY`）。`backend/engine01_intent/llm_client.py` 是那套做法的原型，
這裡照抄它的 flag 組合與 `--output-schema` 用法，但**不 import 它**——`agent/` 要能跟著
Hermes distribution 單獨發佈，一旦 import backend 就綁死在這個 repo 裡了。

退場路徑是這支腳本的重點：codex 失敗、逾時、回傳不合法、或挑了清單裡沒有的 id，
一律退回 `tops[0]` 與 `bottoms[0]`，理由用 keywords 拼一句，`source` 標成 `fallback`，
**退出碼仍然是 0**。現場 demo 不能因為 codex 慢了十秒就整條流程壞掉；呼叫端看 `source`
就知道這組是挑出來的還是退場來的。

用法（--dry-run 只組 prompt 不呼叫模型，開發時先用它）：

  python agent/scripts/pair_outfit.py --input pair_input.json --dry-run
  python agent/scripts/pair_outfit.py --input pair_input.json --timeout 60

input.json 的形狀：{"intent": {...}, "tops": [{id,label,keywords,origin}], "bottoms": [...]}
`origin` 是 "catalog"（商品庫現貨）或 "generated"（AI 生成概念），省略當 generated。
stdout 最後一行（契約，不要改）：
  {"top_id": "top-ai-3", "bottom_id": "bottom-ai-6", "reason": "…", "source": "llm"}
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

# 規則的唯一來源是 SKILL.md。標記之間那段逐字讀進 prompt，改規則只要改 skill。
SKILL_MD = Path(__file__).resolve().parents[1] / "skills" / "outfit-pairer" / "SKILL.md"
RULES_START = "<!-- prompt:rules:start -->"
RULES_END = "<!-- prompt:rules:end -->"

# 只有在 SKILL.md 讀不到時才用這份。為什麼不乾脆內嵌全部：規則是設計上的判斷，
# 會被線 1 反覆改，寫兩份一定會有一份過期——所以正常情況讀檔。
# 但 distribution 裝到別台機器、或有人把標記刪掉時，腳本不能整個不能跑，
# 所以留這份**刻意有損**的摘要當地板：判斷會變粗，但流程還活著。
_RULES_FALLBACK = """一、輪廓平衡：寬鬆的上衣配直筒或錐形的下身，合身短版上衣才配寬鬆闊腿，不要兩件都寬。
二、長度關係：短版上衣配高腰；長版上衣配闊褲會吃掉腿，要收窄或露腳踝；兩件的下擺不要停在同一個高度。
三、材質與場合：重量級距要接近，場合與季節一致，通勤與正式場合不要刷破與大面積漂白。
四、貼合 intent：使用者親口講過的顏色、風格、場合、材質要看得見；主角級的設計細節只留一件。
理由要指名兩件各自的具體屬性與它們的關係，40 字以內，不要寫「很好看」「很百搭」。"""

# 這幾個跟 ENGINE01 用同一組環境變數名，一台機器設一次兩邊都吃得到。
_CODEX_BIN = os.environ.get("CODEX_BIN", "codex")
_CODEX_MODEL = os.environ.get("CODEX_MODEL")
_CODEX_REASONING_EFFORT = os.environ.get("CODEX_REASONING_EFFORT", "low")
# 配對的 prompt 比 ENGINE01 的意圖抽取短得多，正常十幾秒內回得來。逾時抓 45 秒是
# 「等到願意等的上限」，不是「模型的正常耗時」——超過就走退場，使用者不會盯著轉圈。
_DEFAULT_TIMEOUT = float(os.environ.get("PAIR_OUTFIT_TIMEOUT", "45"))

# codex exec 的 strict 模式要求每個物件節點都寫死 additionalProperties 與 required
# （理由見 llm_client.py 的 _to_strict_schema）。這份 schema 只有一層，所以直接寫好，
# 不用為了三個欄位把 pydantic 拉進來——agent/ 的腳本只靠標準函式庫。
_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "top_id": {"type": "string"},
        "bottom_id": {"type": "string"},
        "reason": {"type": "string"},
    },
    "required": ["top_id", "bottom_id", "reason"],
    "additionalProperties": False,
}


def _rules_text() -> str:
    try:
        text = SKILL_MD.read_text(encoding="utf-8")
        body = text.split(RULES_START, 1)[1].split(RULES_END, 1)[0].strip()
        if body:
            return body
    except (OSError, IndexError):
        pass
    print(f"[warn] 讀不到 {SKILL_MD} 的規則段落，改用內嵌摘要（判斷會變粗）", file=sys.stderr)
    return _RULES_FALLBACK


def _values(item: dict[str, Any]) -> list[str]:
    """把 keywords 攤成一串中文值。

    manifest 寫出來的是 `{欄位: 中文值}`，但前端的 FashionRecommendation 把它壓成
    `attributes` 字串陣列——兩種都可能被餵進來，這裡一起吃掉，省得呼叫端先轉一次。
    """
    kw = item.get("keywords")
    if isinstance(kw, dict):
        return [str(v).strip() for v in kw.values() if str(v).strip()]
    if isinstance(kw, list):
        return [str(v).strip() for v in kw if str(v).strip()]
    if isinstance(kw, str) and kw.strip():
        return [kw.strip()]
    return []


def _pairs(item: dict[str, Any]) -> str:
    """給模型看的屬性串。有欄位名就連欄位名一起給——「fit=寬鬆」比單獨一個「寬鬆」
    好判斷，模型才分得出這個詞講的是版型還是材質。"""
    kw = item.get("keywords")
    if isinstance(kw, dict):
        return "; ".join(f"{k}={v}" for k, v in kw.items() if str(v).strip())
    return "; ".join(_values(item))


# 候選可能混著兩種來源，講給模型聽要用它看得懂的話，不要丟英文 enum。
_ORIGIN_ZH = {"catalog": "商品庫現貨", "generated": "AI 生成概念"}


def _describe(item: dict[str, Any]) -> str:
    label = str(item.get("label") or "").strip()
    origin = _ORIGIN_ZH.get(str(item.get("origin") or "generated"), "AI 生成概念")
    head = f"{item['id']}｜{origin}｜{label or '（無標籤）'}"
    pairs = _pairs(item)
    return f"- {head}｜{pairs}" if pairs else f"- {head}"


def _build_prompt(intent: dict[str, Any], tops: list[dict[str, Any]],
                  bottoms: list[dict[str, Any]]) -> str:
    top_ids = ", ".join(t["id"] for t in tops)
    bottom_ids = ", ".join(b["id"] for b in bottoms)
    # intent 的中文值原樣帶進去，不翻成英文——服裝詞彙翻過去就只剩泛泛的形容詞
    # （同 concept-image-director 的理由）。
    return (
        "你是 outfit-pairer。從下面兩份清單裡挑出最搭的一組上衣與下身，"
        "並用一句繁體中文說明為什麼。只挑一組，不要挑清單以外的東西。\n\n"
        "# 判斷依據\n"
        f"{_rules_text()}\n\n"
        "# 整體脈絡：使用者這次的結構化意圖\n"
        "（中文值照原文讀，不要翻成英文；inferred_fields 列到的欄位是系統推論的，"
        "不是使用者親口講的）\n"
        f"{json.dumps(intent, ensure_ascii=False)}\n\n"
        "# 上衣候選\n"
        f"{chr(10).join(_describe(t) for t in tops)}\n\n"
        "# 下身候選\n"
        f"{chr(10).join(_describe(b) for b in bottoms)}\n\n"
        "# 輸出\n"
        "只回一個 JSON 物件，三個欄位：top_id、bottom_id、reason。\n"
        f"top_id 只能是這幾個其中一個，逐字照抄：{top_ids}\n"
        f"bottom_id 只能是這幾個其中一個，逐字照抄：{bottom_ids}\n"
        "reason 是一句繁體中文，40 字以內，要同時指名上衣與下身各自的具體屬性"
        "以及它們之間的關係。不要寫「很好看」「很百搭」這種換成任何一組都成立的句子，"
        "不要點名品牌，不要用「我」「使用者」。"
    )


def _extract_json(raw: str) -> Optional[dict[str, Any]]:
    """從模型輸出裡挖出那個 JSON 物件。

    帶了 --output-schema 的時候回來的本來就是乾淨 JSON，但模型偶爾會多包一層
    ```json 圍欄。為了這種小事走退場太可惜（退場會讓使用者看到拼出來的理由），
    所以這裡容忍一層圍欄；再歪就是真的不合法，交給退場。
    """
    raw = raw.strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        match = re.search(r"\{.*\}", raw, re.S)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except ValueError:
            return None
    return data if isinstance(data, dict) else None


def _call_codex(prompt: str, timeout: float) -> Optional[dict[str, Any]]:
    """呼叫 codex exec 拿結構化回傳。任何一種失敗都回 None，由呼叫端走退場。

    flag 組合跟 ENGINE01 一致：--skip-git-repo-check 讓它不管在哪個目錄都能跑、
    --sandbox read-only 不給它碰檔案系統、--ephemeral 不留 session（狀態我們自己管）、
    --disable plugins/skill_search 砍掉用不到的 context（實測省 token）、
    --output-last-message 把最終回覆寫進檔案，不用去 parse 終端機的顯示文字。
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        schema_path = Path(tmp_dir) / "pair_outfit.schema.json"
        schema_path.write_text(json.dumps(_SCHEMA), encoding="utf-8")
        output_path = Path(tmp_dir) / "output.json"
        cmd = [
            _CODEX_BIN, "exec",
            "--skip-git-repo-check",
            "--sandbox", "read-only",
            "--ephemeral",
            "--disable", "plugins",
            "--disable", "skill_search",
            "-c", f'model_reasoning_effort="{_CODEX_REASONING_EFFORT}"',
            "--output-schema", str(schema_path),
            "--output-last-message", str(output_path),
        ]
        if _CODEX_MODEL:
            cmd += ["-m", _CODEX_MODEL]
        cmd.append(prompt)

        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=timeout)
        except subprocess.TimeoutExpired:
            print(f"[warn] codex exec 超過 {timeout} 秒沒回來，走退場", file=sys.stderr)
            return None
        except (OSError, subprocess.SubprocessError) as exc:
            # 最常見的是找不到 codex（沒裝或不在 PATH）。這裡不丟例外：
            # 沒裝 codex 的機器照樣要能跑完整條流程，只是每次都走退場。
            print(f"[warn] 叫不動 {_CODEX_BIN}：{exc}，走退場", file=sys.stderr)
            return None

        if proc.returncode != 0:
            print(f"[warn] codex exec 失敗（exit {proc.returncode}）："
                  f"{(proc.stderr or '').strip()[-500:]}，走退場", file=sys.stderr)
            return None
        try:
            raw = output_path.read_text(encoding="utf-8")
        except OSError:
            print("[warn] codex exec 沒有寫出回覆檔，走退場", file=sys.stderr)
            return None
    return _extract_json(raw)


def _validated(data: Optional[dict[str, Any]], tops: list[dict[str, Any]],
               bottoms: list[dict[str, Any]]) -> Optional[dict[str, str]]:
    """模型回傳過不過得了關。過不了就回 None——挑了清單裡沒有的 id，前端在
    FashionRecommendation 裡找不到那件衣服，畫面上就是一組空卡片，比退場還糟。"""
    if not data:
        return None
    top_id, bottom_id = str(data.get("top_id") or ""), str(data.get("bottom_id") or "")
    reason = str(data.get("reason") or "").strip()
    if top_id not in {t["id"] for t in tops}:
        print(f"[warn] 模型挑的 top_id「{top_id}」不在清單裡，走退場", file=sys.stderr)
        return None
    if bottom_id not in {b["id"] for b in bottoms}:
        print(f"[warn] 模型挑的 bottom_id「{bottom_id}」不在清單裡，走退場", file=sys.stderr)
        return None
    if not reason:
        print("[warn] 模型沒有給理由，走退場", file=sys.stderr)
        return None
    return {"top_id": top_id, "bottom_id": bottom_id, "reason": reason, "source": "llm"}


# 拼退場理由時，描述詞的取用順序。輪廓與長度是搭配上最有資訊量的，顏色材質次之；
# item_type 留到最後當名詞，中文才讀得順（「落肩箱型厚磅棉上衣」而不是「上衣落肩箱型」）。
_DESC_KEYS = ("fit", "silhouette", "material", "length", "colors", "pattern", "design_detail")


def _join_desc(parts: list[str]) -> str:
    """把描述詞接起來。中文之間不加空格（「落肩箱型厚磅棉」），但兩邊都是英數時要加，
    否則 oversized + denim 會黏成 oversizeddenim——候選混進商品庫的英文標籤之後就會踩到。"""
    out = ""
    for part in parts:
        if out and out[-1].isascii() and out[-1].isalnum() and part[:1].isascii() and part[:1].isalnum():
            out += " "
        out += part
    return out


def _short(item: dict[str, Any], limit: int = 2) -> str:
    """拼退場理由用的短描述。只取兩個描述詞——退場的句子本來就只是陳述這兩件是什麼，
    把六個屬性全串上去會變成一串念不動的關鍵字。"""
    kw = item.get("keywords")
    if isinstance(kw, dict):
        picked: list[str] = []
        for key in _DESC_KEYS:
            val = str(kw.get(key) or "").strip()
            # 「桶褲」已經講完的事不要用「寬鬆桶褲型」再講一次
            if val and not any(val in p or p in val for p in picked):
                picked.append(val)
            if len(picked) == limit:
                break
        noun = str(kw.get("item_type") or "").strip()
        if noun and not any(noun in p for p in picked):
            picked.append(noun)
        if picked:
            return _join_desc(picked)
    vals = _values(item)[:limit + 1]
    return _join_desc(vals) if vals else str(item.get("label") or item["id"])


def _fallback(tops: list[dict[str, Any]], bottoms: list[dict[str, Any]]) -> dict[str, str]:
    """退場：第一件配第一件。

    理由只用 keywords 拼，不編造判斷——兩邊真的有共同的屬性值（同一個場合、同一個
    季節、同一種材質）就講出來，那是看得到的事實；沒有就只陳述兩件是什麼，
    不要硬掰「所以很搭」。呼叫端看 source=fallback 就知道這句不是挑出來的。
    """
    top, bottom = tops[0], bottoms[0]
    shared = [v for v in _values(top) if v in set(_values(bottom))]
    tail = f"，都落在{shared[0]}上。" if shared else "，兩件的屬性沒有互相衝突。"
    return {"top_id": top["id"], "bottom_id": bottom["id"],
            "reason": f"{_short(top)}配{_short(bottom)}{tail}", "source": "fallback"}


def _candidates(raw: Any, name: str) -> list[dict[str, Any]]:
    items = [x for x in raw if isinstance(x, dict) and str(x.get("id") or "").strip()] \
        if isinstance(raw, list) else []
    for x in items:
        x["id"] = str(x["id"]).strip()
    if not items:
        # 這個不能退場：一邊空的時候根本挑不出一組，硬回一個假 id 只會讓前端顯示壞掉。
        raise SystemExit(f"輸入的 {name} 是空的，或每一筆都沒有 id，配不出任何一組。")
    return items


def main() -> int:
    ap = argparse.ArgumentParser(description="從生成的上衣與下身裡挑一組最搭的")
    ap.add_argument("--input", required=True,
                    help="JSON 檔路徑，內容是 {intent, tops, bottoms}")
    ap.add_argument("--timeout", type=float, default=_DEFAULT_TIMEOUT,
                    help=f"codex exec 的逾時秒數，預設 {_DEFAULT_TIMEOUT}")
    ap.add_argument("--dry-run", action="store_true",
                    help="只組 prompt 不呼叫模型，印出 prompt 與會走的退場結果")
    args = ap.parse_args()

    path = Path(args.input)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SystemExit(f"讀不到 --input {path}：{exc}")
    except ValueError as exc:
        raise SystemExit(f"--input {path} 不是合法的 JSON：{exc}")
    if not isinstance(payload, dict):
        raise SystemExit(f"--input {path} 的最外層要是物件 {{intent, tops, bottoms}}")

    intent = payload.get("intent") or {}
    tops = _candidates(payload.get("tops"), "tops")
    bottoms = _candidates(payload.get("bottoms"), "bottoms")
    prompt = _build_prompt(intent, tops, bottoms)

    if args.dry_run:
        print(prompt)
        print("\n[dry-run] 沒有呼叫 codex，沒有花額度。下面這行是模型失敗時會走的退場結果：")
        print(json.dumps(_fallback(tops, bottoms), ensure_ascii=False))
        return 0

    started = time.monotonic()
    result = _validated(_call_codex(prompt, args.timeout), tops, bottoms) \
        or _fallback(tops, bottoms)
    # 耗時走 stderr：stdout 的最後一行是契約，只放那四個欄位。
    print(f"[info] {result['source']}，{time.monotonic() - started:.1f} 秒", file=sys.stderr)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
