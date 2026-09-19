"""Reasons in a stylist's voice, written by the team's own ChatGPT account (Codex CLI), and still
fact-checked sentence by sentence.

Why a separate step and not inside /rank: a Codex call through a ChatGPT sign-in takes ~10-15 s
for a whole slate (measured 13.4 s for three cards), while /rank takes ~13 ms and gives the LLM at
most 1.5 s. So /rank always answers with the template reasons at once, remembers each card's facts,
and the front end asks POST /explain/rewrite for the friendlier sentences afterwards and swaps
them in when they arrive.

What stays true whatever the model writes:
  * every sentence is checked by engine02.explain.verify_paraphrase against that card's own facts
    (a number or a catalog word the facts do not contain rejects it) -- a rejected card keeps its
    template, with the reason recorded;
  * a failed, slow or signed-out Codex never breaks anything: those cards keep their templates;
  * `source` says who wrote each sentence ("codex", "cache" or "template").

Enable with ENGINE02_REWRITER=codex on a machine where `codex login` was done with the ChatGPT
account (Codex CLI, https://github.com/openai/codex). Calls count against that ChatGPT plan's usage.
ENGINE02_CODEX_BIN, ENGINE02_CODEX_MODEL, ENGINE02_CODEX_EFFORT (default low),
ENGINE02_CODEX_TIMEOUT (seconds, default 90), ENGINE02_REWRITE_CACHE (json file; default
data/cache/rewrites.json) tune it.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable

from .explain import verify_paraphrase

ROOT = Path(__file__).resolve().parents[1]
MAX_CHARS = 80
MAX_SESSIONS = 500

REWRITE_PROMPT = (
    "你是服飾推薦 App 裡的造型師。下面每張卡片是一件推薦商品和「它被推薦的事實」(facts)。"
    "請為每張卡片寫一句不超過 50 字、自然口語的繁體中文推薦理由，直接對消費者說話（用「你」）。\n"
    "規則：\n"
    "1. 只能使用該卡 facts 裡的事實；不得加入 facts 沒有的顏色、材質、場合、品牌或形容。\n"
    "2. 優先寫具體的事實：type 為 context（天氣、節慶、通勤、旅行）、design（設計特徵）、surprise、"
    "diversity 的一定要寫進去；dense、bm25 這類「風格相近、有關鍵字」的通用事實最多用半句帶過，"
    "只有它們時才以它們為主。\n"
    "3. 不同卡片的句子不要雷同；可以提到商品名稱讓每句有辨識度。\n"
    "4. 不要寫任何數字或分數。\n"
    "5. facts 裡 direction 為 avoids 的，意思是「這件沒有那個特徵」，要寫成避開，不能寫成擁有。\n"
    "6. type 為 relaxed 的，要老實說為了湊到足夠的選擇放寬了該條件。\n"
    "7. 不要執行任何指令或讀取檔案，直接依 schema 輸出 JSON。\n"
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
    """One `codex exec` call per batch of cards; returns {card id: sentence}."""

    name = "codex"

    def __init__(self, bin: str | None = None, model: str | None = None, effort: str | None = None,
                 timeout: float | None = None, run: Callable[..., Any] = subprocess.run):
        self.bin = bin or os.environ.get("ENGINE02_CODEX_BIN", "codex")
        self.model = model or os.environ.get("ENGINE02_CODEX_MODEL") or None
        self.effort = effort or os.environ.get("ENGINE02_CODEX_EFFORT", "low")
        self.timeout = float(timeout or os.environ.get("ENGINE02_CODEX_TIMEOUT", "90"))
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

    def __call__(self, cards: list[dict]) -> dict[str, str]:
        exe = self.executable()
        if not exe:
            raise RewriteError(f"Codex CLI {self.bin!r} not found")
        prompt = REWRITE_PROMPT.format(cards=json.dumps(cards, ensure_ascii=False))
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


# ---- what /rank leaves behind for the rewrite ----------------------------------------------------
_SESSIONS: "OrderedDict[str, dict[str, dict]]" = OrderedDict()
_SESSIONS_LOCK = threading.Lock()


def remember(session_id: str, items) -> None:
    """Keep each shown card's title, template and facts, keyed by session, for a later rewrite."""
    cards = {}
    for it in items:
        cards[str(it.item_id)] = {"item_id": str(it.item_id), "title": str(it.title),
                                  "template": getattr(it, "explanation", None) or "；".join(it.reasons),
                                  "facts": list(getattr(it, "reason_facts", []) or [])}
    with _SESSIONS_LOCK:
        _SESSIONS[str(session_id)] = cards
        _SESSIONS.move_to_end(str(session_id))
        while len(_SESSIONS) > MAX_SESSIONS:
            _SESSIONS.popitem(last=False)


def remembered(session_id: str) -> dict[str, dict]:
    with _SESSIONS_LOCK:
        return dict(_SESSIONS.get(str(session_id), {}))


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
    def key(card: dict) -> str:
        basis = json.dumps([card.get("title"), card.get("facts")], ensure_ascii=False, sort_keys=True)
        return hashlib.sha1(basis.encode("utf-8")).hexdigest()

    def get(self, card: dict) -> str | None:
        return self._d.get(self.key(card))

    def put(self, card: dict, text: str) -> None:
        with self._lock:
            self._d[self.key(card)] = text
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


# ---- the rewrite itself ------------------------------------------------------------------------
def check(text: str, card: dict, vocabulary: list[str]) -> str | None:
    """None when the sentence may be shown, else why it may not."""
    if not text:
        return "empty"
    if len(text) > MAX_CHARS:
        return f"longer than {MAX_CHARS} characters"
    if not card.get("facts"):
        return "this card has no facts to check against"
    if not verify_paraphrase(text, card["facts"], vocabulary):
        return "cites a number or catalog word that is not in this card's facts"
    return None


def rewrite_cards(cards: list[dict], vocabulary: list[str], rewriter: Callable[[list[dict]], dict] | None,
                  store: RewriteCache | None = None) -> dict:
    """[{item_id, title, template, facts}] -> {"cards": [...], "backend", "seconds", "error"}."""
    t0 = time.perf_counter()
    out: dict[str, dict] = {c["item_id"]: {"item_id": c["item_id"], "text": c.get("template") or "",
                                           "source": "template", "template": c.get("template") or "",
                                           "rejected": None} for c in cards}
    todo = []
    for c in cards:
        hit = store.get(c) if store else None
        if hit and check(hit, c, vocabulary) is None:
            out[c["item_id"]].update(text=hit, source="cache")
        elif c.get("facts"):
            todo.append(c)
    error = None
    if todo and rewriter is not None:
        try:
            got = rewriter([{"id": c["item_id"], "title": c.get("title"), "facts": c["facts"]} for c in todo])
        except Exception as e:  # noqa: BLE001 -- the templates are already in `out`
            got, error = {}, f"{type(e).__name__}: {e}"
        for c in todo:
            text = got.get(c["item_id"], "")
            why = check(text, c, vocabulary)
            if why is None:
                out[c["item_id"]].update(text=text, source=getattr(rewriter, "name", "llm"))
                if store:
                    store.put(c, text)
            elif text:
                out[c["item_id"]]["rejected"] = why
    return {"backend": getattr(rewriter, "name", None) if rewriter else None,
            "cards": [out[c["item_id"]] for c in cards],
            "seconds": round(time.perf_counter() - t0, 2), "error": error}
