"""Reasons in a stylist's voice, written by the team's own ChatGPT account (Codex CLI): layered,
concrete (the real temperature, flight time, days to the festival, the item's own colour and
price), and still fact-checked sentence by sentence.

Why a separate step and not inside /rank: a Codex call through a ChatGPT sign-in takes ~10-20 s
for a whole slate, while /rank takes ~13 ms and gives an LLM at most 1.5 s. So /rank always
answers with the template reasons at once and remembers, per session, each card's facts plus the
shopper's situation; the front end asks POST /explain/rewrite afterwards and swaps the text in.

What the model gets, per card (no ranking scores -- "+0.42" means nothing to a shopper):
  * situation  -- the context signals THIS card was ranked for, with their raw numbers rounded
                  (台北 23°C → 札幌 8°C, 4.1 h flight, 46% rainy days, 中秋 in 3 days ...); a card
                  picked for its style gets none, so it is never explained by the weather;
  * background -- display-only signals shared by the slate (distance, lucky colour), tips only;
  * item       -- the card's own catalogue facts (category, colour, season, occasion, style, price
                  and whether that price is an estimate);
  * reasons    -- what put the card on the slate, most important first.

What stays true whatever the model writes (`check`):
  * every number in the sentence must be one of those facts' numbers (rounding allowed: 4.1 h may
    be "約 4 小時"), so no temperature or percentage can be invented;
  * a catalogue word (colour, occasion ...) must belong to this card;
  * an estimated price may only be quoted together with 「估計」;
  * a failed, slow or signed-out Codex never breaks anything: those cards keep their templates;
  * `source` says who wrote each sentence ("codex", "cache" or "template").

Enable with ENGINE02_REWRITER=codex on a machine where `codex login` was done with the ChatGPT
account (Codex CLI, https://github.com/openai/codex). Calls count against that plan's usage.
ENGINE02_CODEX_BIN, ENGINE02_CODEX_MODEL, ENGINE02_CODEX_EFFORT (default low),
ENGINE02_CODEX_TIMEOUT (seconds, default 120), ENGINE02_REWRITE_CACHE (json file; default
data/cache/rewrites.json) tune it.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
MAX_CHARS = 150
MAX_SESSIONS = 500
PROMPT_VERSION = "v5-own-situation"

REWRITE_PROMPT = (
    "你是服飾推薦 App 裡的專屬造型師。每張推薦卡片有：商品資料（item）、它被推薦的原因（reasons，重要的排前面），"
    "以及這張卡真的因它而被推薦的情境（situation，含具體數字）。另有一份整批共用的背景資訊（background）。\n"
    "請為每張卡片寫一段 2～3 句、合計 60～120 字的繁體中文推薦理由，直接對消費者說話（用「你」），要有層次：\n"
    "  第一層｜為什麼是現在：只有這張卡的 situation 不是空的時候，才引用其中的具體數字（溫度、體感、降雨機率、紫外線、"
    "飛行時間、節慶倒數天數等）；situation 是空的，就直接從商品本身切入，不要提天氣或節慶。\n"
    "  第二層｜為什麼是這件：用 item 的品類、顏色、季節、場合、風格，對應 reasons 裡的理由。\n"
    "  第三層｜一句實用建議：怎麼穿、怎麼搭、要注意什麼；若提到價格，item.price_estimated 為 true 時一定要說「估計價」。\n"
    "規則：\n"
    "1. 只能使用 situation、item、reasons 裡的事實；不得加入沒有的顏色、材質、場合、品牌、數字或形容。\n"
    "2. 數字只能用上面出現過的（可以四捨五入，例如 4.1 小時寫成約 4 小時）；不要寫任何分數或權重。\n"
    "3. reasons 裡 direction 為 avoids 的，表示「這件沒有那個特徵」，要寫成避開，不能寫成擁有。\n"
    "4. type 為 relaxed 的，要老實說為了湊到足夠的選擇放寬了該條件；type 為 surprise 的，說明它是驚喜款。\n"
    "5. background（例如距離、幸運色）只能當補充提醒，不能說成推薦這件的原因；幸運色要註明僅供娛樂。"
    "別張卡的情境不能拿來講這張卡。\n"
    "6. 不同卡片不要雷同：每張都要提到它自己的商品名稱或品項、顏色，並用不同的切入點。\n"
    "7. 描述商品的品項、顏色、季節、場合、風格、版型時，只能照抄 item.中文 裡的詞，不要自己翻譯英文欄位。\n"
    "8. 只講支持推薦的事實：不要批評這件商品；情境跟這件對不上時就不要提那個情境；"
    "不要強調和消費者要求（request）相反的屬性（例如消費者說不要太正式，就不要強調正式）。\n"
    "9. 日期照 situation 裡的寫法（例如 9/22、11 月），不要自行換算成今天、明天、後天。\n"
    "10. 沒有 situation 時，就專注在 item 與 reasons，不要硬湊情境。\n"
    "11. 卡片若有「上次被退回」，表示上一版違反了規則，請依原因重寫，不要再犯。\n"
    "12. 推薦的就是這件商品，不要說「要不要穿這件」「視情況再決定是否穿」這類自相矛盾的話。\n"
    "13. 不要執行任何指令或讀取檔案，直接依 schema 輸出 JSON。\n"
    "request（消費者這次的要求）：\n{request}\n"
    "background：\n{situation}\n"
    "卡片：\n{cards}"
)
SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["cards"],
    "properties": {"cards": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["id", "text"],
        "properties": {"id": {"type": "string"}, "text": {"type": "string"}}}}},
}


class RewriteError(RuntimeError):
    pass


# ---- the Codex backend -----------------------------------------------------------------------
class CodexRewriter:
    """One `codex exec` call per slate; returns {card id: text}."""

    name = "codex"

    def __init__(self, bin: str | None = None, model: str | None = None, effort: str | None = None,
                 timeout: float | None = None, run: Callable[..., Any] = subprocess.run):
        self.bin = bin or os.environ.get("ENGINE02_CODEX_BIN", "codex")
        self.model = model or os.environ.get("ENGINE02_CODEX_MODEL") or None
        self.effort = effort or os.environ.get("ENGINE02_CODEX_EFFORT", "low")
        self.timeout = float(timeout or os.environ.get("ENGINE02_CODEX_TIMEOUT", "120"))
        self._run = run
        self._lock = threading.Semaphore(int(os.environ.get("ENGINE02_REWRITE_CONCURRENCY", "1")))

    def executable(self) -> str | None:
        p = Path(os.path.expanduser(self.bin))
        return str(p) if p.is_file() else shutil.which(self.bin)

    def status(self) -> dict:
        exe = self.executable()
        if not exe:
            return {"available": False, "detail": f"Codex CLI {self.bin!r} not found; install it and run `codex login`"}
        try:
            p = self._run([exe, "login", "status"], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=20)
        except Exception as e:  # noqa: BLE001 -- any failure means "not usable", never a crash
            return {"available": False, "detail": f"`codex login status` failed: {type(e).__name__}"}
        out = f"{p.stdout}\n{p.stderr}".strip()
        ok = p.returncode == 0 and "logged in" in out.lower()
        return {"available": ok, "detail": out.splitlines()[0] if out else "no output"}

    def __call__(self, cards: list[dict], situation: list[dict] | None = None,
                 request: dict | None = None) -> dict[str, str]:
        exe = self.executable()
        if not exe:
            raise RewriteError(f"Codex CLI {self.bin!r} not found")
        prompt = REWRITE_PROMPT.format(request=json.dumps(request or {}, ensure_ascii=False),
                                       situation=json.dumps(situation or [], ensure_ascii=False),
                                       cards=json.dumps(cards, ensure_ascii=False))
        with self._lock, tempfile.TemporaryDirectory(prefix="engine02-rewrite-") as tmp:
            schema, out = Path(tmp) / "schema.json", Path(tmp) / "last.json"
            schema.write_text(json.dumps(SCHEMA), encoding="utf-8")
            cmd = [exe, "exec", "--skip-git-repo-check", "--ephemeral", "--sandbox", "read-only",
                   "-C", tmp, "-c", f"model_reasoning_effort={self.effort}",
                   "--output-schema", str(schema), "-o", str(out)]
            if self.model:
                cmd += ["-m", self.model]
            cmd.append("-")
            try:
                p = self._run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=self.timeout, cwd=tmp)
            except subprocess.TimeoutExpired as e:
                raise RewriteError(f"codex exec timed out after {self.timeout:.0f}s") from e
            if p.returncode != 0 or not out.exists():
                tail = (p.stderr or p.stdout or "")[-300:]
                raise RewriteError(f"codex exec failed (exit {p.returncode}): {tail}")
            try:
                data = json.loads(out.read_text(encoding="utf-8"))
            except ValueError as e:
                raise RewriteError("codex returned something that is not JSON") from e
        return {str(c.get("id")): str(c.get("text") or "").strip() for c in data.get("cards", [])
                if isinstance(c, dict)}


def get_rewriter() -> CodexRewriter | None:
    return CodexRewriter() if os.environ.get("ENGINE02_REWRITER", "").strip().lower() == "codex" else None


# ---- the facts the model may use --------------------------------------------------------------
# raw detail keys that are plumbing, not something to tell a shopper
_SKIP_DETAIL = {"lat", "lon", "ramp", "warmth_target", "transport_inferred", "hourly_source", "source_url",
                "key", "system", "climate_normal", "uv_trigger", "fetched_at", "source", "festival_en",
                "origin", "destination", "place", "date", "start", "end", "kind", "headline"}
_ITEM_COLS = ("category", "subcategory", "color", "season", "occasion", "gender", "style", "fit",
              "pattern", "price", "currency", "price_estimated", "price_basis")


def _num(v: float) -> float | int:
    """Round a raw number the way a person would say it: 2696.4 -> 2696, 4.09 -> 4.1, -15.2 -> 15."""
    v = abs(float(v))
    return int(round(v)) if v >= 10 or abs(v - round(v)) < 0.05 else round(v, 1)


def situation_facts(ctx, today=None) -> list[dict]:
    """Every context signal for this request (ranking or display-only) with its rounded numbers."""
    if ctx is None:
        return []
    from .context.engine import build_signals, is_empty

    if is_empty(ctx):
        return []
    try:
        sigs, _ = build_signals(ctx, today=today)
    except Exception:  # noqa: BLE001 -- no situation is better than no rewrite
        return []
    out = []
    for s in sigs:
        nums = {}
        for k, v in (s.detail or {}).items():
            if k in _SKIP_DETAIL or isinstance(v, bool):
                continue
            if isinstance(v, (int, float)) and not (isinstance(v, float) and math.isnan(v)):
                nums[k] = _num(v)
            elif isinstance(v, str) and len(v) <= 40:
                nums[k] = v
        out.append({"source": s.source, "label": s.label, "shown_on_card": bool(s.affects_ranking), "numbers": nums})
    return out


# ---- fixed Chinese names for the item's attributes -------------------------------------------
# The model must use these words verbatim; `check` rejects a colour / season / style / fit /
# occasion word that is neither this card's nor in any fact (a white shirt written up as 海軍藍,
# a vintage jacket as 前衛 -- both happened before these existed).
COLOR_EXACT_ZH = {"Navy Blue": "深藍色", "Turquoise Blue": "土耳其藍", "Teal": "藍綠色", "Maroon": "酒紅色",
                  "Olive": "橄欖綠", "Off White": "米白色", "Cream": "奶油白", "Charcoal": "炭灰色",
                  "Khaki": "卡其色", "Mustard": "芥末黃", "Burgundy": "酒紅色", "Silver": "銀色", "Gold": "金色"}
FAMILY_ZH = {"black": "黑色", "white": "白色", "grey": "灰色", "blue": "藍色", "red": "紅色", "pink": "粉色",
             "purple": "紫色", "green": "綠色", "yellow": "黃色", "orange": "橘色", "brown": "棕色", "beige": "米色"}
SEASON_ZH = {"Spring": ["春季", "春天", "春"], "Summer": ["夏季", "夏天", "夏"], "Fall": ["秋季", "秋天", "秋"],
             "Winter": ["冬季", "冬天", "冬"]}
OCCASION_ZH = {"Formal": ["正式"], "Casual": ["休閒", "日常"], "Smart Casual": ["商務休閒", "半正式"],
               "Sports": ["運動"], "Travel": ["旅行", "旅遊"], "Ethnic": ["民族風"]}
STYLE_ZH = {"classic": ["經典"], "romantic": ["浪漫"], "minimalist": ["簡約", "極簡"], "streetwear": ["街頭"],
            "preppy": ["學院"], "sporty": ["運動風"], "bohemian": ["波希米亞"], "edgy": ["個性", "酷"],
            "vintage": ["復古"], "avant_garde": ["前衛"]}
FIT_ZH = {"regular": ["標準版型"], "loose": ["寬鬆"], "slim": ["合身", "修身"]}
AMBIGUOUS_ZH = {"合身", "日常"}
RELATIVE_DAYS = ("今天", "明天", "後天", "昨天", "今晚", "明晚")
CATEGORY_ZH = {"top": "上衣", "bottom": "下身", "dress": "洋裝", "outerwear": "外套", "shoes": "鞋款",
               "bag": "包款", "accessory": "配件", "jewelry": "飾品"}


def _color_words() -> dict[str, str]:
    """Chinese colour word -> colour family (only words of 2+ characters: 米, 金, 粉 alone are too
    common in ordinary text -- 公里, 金額)."""
    from .attribute_fill import COLOR_ZH
    words = {w: f for w, f in COLOR_ZH.items() if len(w) >= 2}
    words.update({w: None for w in COLOR_EXACT_ZH.values()})
    words.update({w: f for f, w in FAMILY_ZH.items()})
    return words


def _zh_item(v: dict) -> dict:
    zh = {}
    if v.get("subcategory") or v.get("title"):
        from .price_estimate import _match
        hit = _match(str(v.get("subcategory") or "")) or _match(str(v.get("title") or ""))
        if hit:
            zh["品項"] = hit[0]
    if not zh.get("品項") and v.get("category") in CATEGORY_ZH:
        zh["品項"] = CATEGORY_ZH[v["category"]]
    color = v.get("color")
    if color:
        from .attribute_fill import color_family
        fam = color_family(str(color))
        zh["顏色"] = COLOR_EXACT_ZH.get(str(color)) or FAMILY_ZH.get(fam or "", "")
    for col, table, key in (("season", SEASON_ZH, "季節"), ("occasion", OCCASION_ZH, "場合"),
                            ("style", STYLE_ZH, "風格"), ("fit", FIT_ZH, "版型")):
        if v.get(col) in table:
            zh[key] = table[v[col]][0]
    return {k: w for k, w in zh.items() if w}


def item_facts(catalog, item_id: str) -> dict:
    """The card's own catalogue facts (what a sentence may say about the item itself), with the
    fixed Chinese names the model must use under 中文."""
    pos = catalog.pos(item_id) if catalog is not None else None
    if pos is None:
        return {}
    out = {"title": catalog.attr(pos, "title")}
    for col in _ITEM_COLS:
        v = catalog.attr(pos, col)
        if v is None or (isinstance(v, str) and not v.strip()):
            continue
        if hasattr(v, "item"):          # numpy scalar -> python
            v = v.item()
        out[col] = _num(v) if isinstance(v, float) and col == "price" else v
    zh = _zh_item(out)
    out.pop("title")
    if zh:
        out["中文"] = zh
    return out


def own_situation(card: dict, situation: list[dict] | None) -> tuple[list[dict], list[dict]]:
    """(the signals this card was actually ranked for, the display-only background).

    A situation that did not put the card on the slate must not be told as its reason -- the same
    rule the template follows (minimal sufficient set): otherwise a black dress picked for its style
    reads as "picked because it is 30°C"."""
    cited = {f.get("label") for f in card.get("facts") or [] if f.get("type") == "context"}
    own = [s for s in situation or [] if s.get("label") in cited]
    background = [s for s in situation or [] if not s.get("shown_on_card")]
    return own, background


def reason_facts_for_model(facts: list[dict]) -> list[dict]:
    """Drop the ranking scores; keep the order (most important first)."""
    return [{k: v for k, v in f.items() if k not in ("contribution",)} for f in facts]


# ---- what /rank leaves behind for the rewrite ----------------------------------------------------
_SESSIONS: "OrderedDict[str, dict]" = OrderedDict()
_SESSIONS_LOCK = threading.Lock()


def remember(session_id: str, items, catalog=None, context=None, request: dict | None = None) -> None:
    """Keep each shown card (title, template, facts, item facts), the context and what was asked."""
    cards = {}
    for it in items:
        iid = str(it.item_id)
        cards[iid] = {"item_id": iid, "title": str(it.title),
                      "template": getattr(it, "explanation", None) or "；".join(it.reasons),
                      "facts": list(getattr(it, "reason_facts", []) or []),
                      "item": item_facts(catalog, iid)}
    with _SESSIONS_LOCK:
        _SESSIONS[str(session_id)] = {"cards": cards, "context": context, "request": request or {}}
        _SESSIONS.move_to_end(str(session_id))
        while len(_SESSIONS) > MAX_SESSIONS:
            _SESSIONS.popitem(last=False)


def remembered(session_id: str) -> dict:
    with _SESSIONS_LOCK:
        got = _SESSIONS.get(str(session_id))
        return {"cards": dict(got["cards"]), "context": got["context"], "request": got.get("request") or {}} if got else {}


# ---- cache: the same facts never cost a second call (and the demo can be pre-warmed) -------------
class RewriteCache:
    def __init__(self, path: Path | None):
        self.path = path
        self._d: dict[str, str] = {}
        self._lock = threading.Lock()
        if path and path.exists():
            try:
                self._d = json.loads(path.read_text(encoding="utf-8"))
            except ValueError:
                self._d = {}

    @staticmethod
    def key(card: dict, situation: list[dict] | None = None, request: dict | None = None) -> str:
        basis = json.dumps([PROMPT_VERSION, card.get("title"), card.get("facts"), card.get("item"), situation, request],
                           ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha1(basis.encode("utf-8")).hexdigest()

    def get(self, card: dict, situation: list[dict] | None = None, request: dict | None = None) -> str | None:
        return self._d.get(self.key(card, situation, request))

    def put(self, card: dict, text: str, situation: list[dict] | None = None, request: dict | None = None) -> None:
        with self._lock:
            self._d[self.key(card, situation, request)] = text
            if self.path:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.write_text(json.dumps(self._d, ensure_ascii=False, indent=0), encoding="utf-8")


_CACHE: RewriteCache | None = None


def cache() -> RewriteCache:
    global _CACHE
    if _CACHE is None:
        p = os.environ.get("ENGINE02_REWRITE_CACHE", str(ROOT / "data" / "cache" / "rewrites.json"))
        _CACHE = RewriteCache(Path(p) if p else None)
    return _CACHE


# ---- the check ---------------------------------------------------------------------------------
_NUM = re.compile(r"\d+(?:\.\d+)?")


def _numbers_in(obj, out: set[float], skip=("contribution",)) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k not in skip:
                _numbers_in(v, out, skip)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _numbers_in(v, out, skip)
    elif isinstance(obj, bool):
        return
    elif isinstance(obj, (int, float)):
        out.add(abs(float(obj)))
    elif isinstance(obj, str):
        for n in _NUM.findall(obj.replace(",", "")):
            out.add(float(n))


def _strings_in(obj, out: set[str]) -> None:
    if isinstance(obj, dict):
        for v in obj.values():
            _strings_in(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _strings_in(v, out)
    elif isinstance(obj, str):
        out.add(obj)


def _allowed(n: float, allowed: set[float]) -> bool:
    # the number itself, or a person's rounding of an allowed number (4.1 -> 4, 2696 -> 2700, 23.4 -> 23)
    for a in allowed:
        if abs(n - a) < 1e-6 or n == round(a) or abs(n - round(a, 1)) < 1e-6:
            return True
        if a >= 100 and n % 100 == 0 and abs(n - a) <= 50:
            return True
    return False


def check(text: str, card: dict, vocabulary: list[str], situation: list[dict] | None = None,
          request: dict | None = None) -> str | None:
    """None when the text may be shown, else why it may not."""
    if not text:
        return "empty"
    if len(text) > MAX_CHARS:
        return f"longer than {MAX_CHARS} characters"
    if not card.get("facts"):
        return "this card has no facts to check against"
    allowed: set[float] = set()
    _numbers_in([card.get("facts"), card.get("item"), situation, card.get("title"), request], allowed)
    for n in _NUM.findall(text.replace(",", "")):
        if not _allowed(float(n), allowed):
            return f"cites the number {n}, which is in none of this card's facts"
    labels: set[str] = set()
    _strings_in([card.get("facts"), card.get("item"), situation, card.get("title"), request], labels)
    item = card.get("item") or {}
    zh = item.get("中文") or {}
    # the item's own attributes in the forms a sentence uses them: 寬鬆 -> 寬鬆版型, 街頭 -> 街頭風
    for v in zh.values():
        labels.update({v, f"{v}版型", f"{v}風", f"{v}風格", f"{v}款"})
    for word in vocabulary:
        if word and word in text and not any(word in s for s in labels):
            return f"uses the catalogue word {word!r}, which is not this card's"
    fact_text = "\n".join(labels)
    # 今天／明天／後天: the model does not know today's date; only the facts' own wording may be used
    for w in RELATIVE_DAYS:
        if w in text and w not in fact_text:
            return f"says {w}, but the facts give a date, not a day relative to today"
    # Chinese attribute words: a colour / season / occasion / style / fit word must be this card's
    # own (its 中文 names, or a synonym in the same colour family) or appear in some fact
    own_family = None
    if item.get("color"):
        from .attribute_fill import color_family
        own_family = color_family(str(item["color"]))
    scan = text
    for word, fam in sorted(_color_words().items(), key=lambda kv: -len(kv[0])):
        if word in scan:
            ok = word == zh.get("顏色") or (fam is not None and fam == own_family) or word in fact_text
            if not ok:
                return f"calls it {word}, but this card's colour is {zh.get('顏色') or item.get('color')}"
            scan = scan.replace(word, "")
    for key, table in (("季節", SEASON_ZH), ("場合", OCCASION_ZH), ("風格", STYLE_ZH), ("版型", FIT_ZH)):
        own = next((ws for ws in table.values() if zh.get(key) in ws), [])
        for ws in table.values():
            for w in ws:
                # 合身 / 日常 are ordinary words too (「試穿確認是否合身」), not a claim about the cut
                if w in AMBIGUOUS_ZH:
                    continue
                if len(w) >= 2 and w in scan and w not in own and w not in fact_text:
                    return f"says {w}, but this card's {key} is {zh.get(key) or '(unknown)'}"
    price = item.get("price")
    if item.get("price_estimated") and price is not None:
        for form in {f"{int(round(price))}", f"{int(round(price)):,}"}:
            if form in text and "估" not in text:
                return "quotes an estimated price without saying it is an estimate"
    return None


# ---- the rewrite itself ------------------------------------------------------------------------
def rewrite_cards(cards: list[dict], vocabulary: list[str], rewriter: Callable[..., dict] | None,
                  store: RewriteCache | None = None, situation: list[dict] | None = None,
                  request: dict | None = None) -> dict:
    """[{item_id, title, template, facts, item}] -> {"cards": [...], "backend", "seconds", "error"}."""
    t0 = time.perf_counter()
    out: dict[str, dict] = {c["item_id"]: {"item_id": c["item_id"], "text": c.get("template") or "",
                                           "source": "template", "template": c.get("template") or "",
                                           "rejected": None} for c in cards}
    # each card only sees (and is only checked against) its own situation + the background
    visible = {c["item_id"]: sum(own_situation(c, situation), []) for c in cards}
    background = [s for s in situation or [] if not s.get("shown_on_card")]
    todo = []
    for c in cards:
        hit = store.get(c, visible[c["item_id"]], request) if store else None
        if hit and check(hit, c, vocabulary, visible[c["item_id"]], request) is None:
            out[c["item_id"]].update(text=hit, source="cache")
        elif c.get("facts"):
            todo.append(c)
    error = None
    if todo and rewriter is not None:
        payload = [{"id": c["item_id"], "title": c.get("title"), "item": c.get("item") or {},
                    "reasons": reason_facts_for_model(c["facts"]),
                    "situation": own_situation(c, situation)[0]} for c in todo]
        retry: list[dict] = []
        for attempt in range(2):          # one retry, told why the first sentence was refused
            batch = payload if attempt == 0 else retry
            if not batch:
                break
            try:
                got = rewriter(batch, background, request)
            except Exception as e:  # noqa: BLE001 -- the templates are already in `out`
                error = f"{type(e).__name__}: {e}"
                break
            retry = []
            for p in batch:
                c = next(x for x in todo if x["item_id"] == p["id"])
                text = got.get(c["item_id"], "")
                why = check(text, c, vocabulary, visible[c["item_id"]], request)
                if why is None:
                    out[c["item_id"]].update(text=text, source=getattr(rewriter, "name", "llm"),
                                             rejected=None, retried=attempt == 1)
                    if store:
                        store.put(c, text, visible[c["item_id"]], request)
                elif text:
                    out[c["item_id"]].update(rejected=why, rejected_text=text)
                    retry.append({**p, "上次被退回": {"句子": text, "原因": why}})
    return {"backend": getattr(rewriter, "name", None) if rewriter else None, "situation": situation or [],
            "request": request or {},
            "cards": [out[c["item_id"]] for c in cards],
            "seconds": round(time.perf_counter() - t0, 2), "error": error}
