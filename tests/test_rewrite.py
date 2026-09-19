"""engine02.rewrite: ChatGPT-voiced reasons (Codex CLI), fact-checked, never blocking /rank."""

import json
import subprocess
from pathlib import Path

import pytest

from engine02.rewrite import CodexRewriter, RewriteCache, check, rewrite_cards

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "catalog" / "kagl" / "items.parquet"
VOCAB = ["Navy Blue", "Formal", "Black", "Casual"]

CARD = {"item_id": "a", "title": "Navy shirt", "template": "修身剪裁（+0.18）",
        "facts": [{"type": "design", "label": "修身剪裁", "direction": "has", "contribution": 0.18,
                   "serves_needs": ["看起來專業"]}]}
CARD_B = {"item_id": "b", "title": "Dress", "template": "避開正式感（+0.09）",
          "facts": [{"type": "design", "label": "正式感", "direction": "avoids", "contribution": 0.09}]}


def test_check_rejects_invented_numbers_words_and_long_text():
    assert check("修身剪裁，讓你看起來很專業。", CARD, VOCAB) is None
    assert "number" in check("修身剪裁，只要 990 元。", CARD, VOCAB)          # a number not in the facts
    assert "catalog word" in check("Navy Blue 的修身剪裁很適合你。", CARD, VOCAB)  # a colour not in the facts
    assert "longer" in check("很" * 81, CARD, VOCAB)
    assert check("", CARD, VOCAB) == "empty"


def test_rewrite_keeps_template_when_the_model_invents_and_uses_it_when_faithful(tmp_path):
    def fake(cards):
        assert [c["id"] for c in cards] == ["a", "b"] and all("facts" in c for c in cards)
        return {"a": "修身剪裁，讓你面試看起來更專業。", "b": "這件是 Black 的，很正式。"}
    fake.name = "codex"
    store = RewriteCache(tmp_path / "c.json")
    out = rewrite_cards([CARD, CARD_B], VOCAB, fake, store)
    a, b = out["cards"]
    assert a["source"] == "codex" and a["text"].startswith("修身剪裁")
    assert b["source"] == "template" and b["text"] == CARD_B["template"] and b["rejected"]
    # the faithful one is cached: a second request makes no call at all
    again = rewrite_cards([CARD], VOCAB, lambda cards: pytest.fail("called again"), RewriteCache(tmp_path / "c.json"))
    assert again["cards"][0]["source"] == "cache"


def test_a_failing_or_missing_rewriter_leaves_every_template_in_place():
    def boom(cards):
        raise RuntimeError("signed out")
    out = rewrite_cards([CARD, CARD_B], VOCAB, boom, None)
    assert [c["source"] for c in out["cards"]] == ["template", "template"] and "signed out" in out["error"]
    out = rewrite_cards([CARD], VOCAB, None, None)
    assert out["backend"] is None and out["cards"][0]["text"] == CARD["template"]


def test_codex_command_is_non_interactive_read_only_and_schema_bound(tmp_path):
    seen = {}

    def run(cmd, **kw):
        seen["cmd"], seen["input"] = cmd, kw.get("input")
        out = Path(cmd[cmd.index("-o") + 1])
        assert json.loads(Path(cmd[cmd.index("--output-schema") + 1]).read_text(encoding="utf-8"))["required"] == ["cards"]
        out.write_text(json.dumps({"cards": [{"id": "a", "text": "修身剪裁很適合你。"}]}), encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    exe = tmp_path / "codex.exe"
    exe.write_text("")
    rw = CodexRewriter(bin=str(exe), run=run, effort="low")
    assert rw([{"id": "a", "title": "t", "facts": CARD["facts"]}]) == {"a": "修身剪裁很適合你。"}
    cmd = seen["cmd"]
    assert cmd[1] == "exec" and "--ephemeral" in cmd and cmd[cmd.index("--sandbox") + 1] == "read-only"
    assert cmd[-1] == "-" and "修身剪裁" in seen["input"] and "不要寫任何數字" in seen["input"]


def test_codex_failure_and_timeout_raise_so_templates_stay(tmp_path):
    exe = tmp_path / "codex.exe"
    exe.write_text("")

    def slow(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 1)

    with pytest.raises(Exception, match="timed out"):
        CodexRewriter(bin=str(exe), run=slow)([{"id": "a", "facts": []}])
    assert CodexRewriter(bin="definitely-not-installed-codex").status()["available"] is False


@pytest.mark.skipif(not CATALOG.exists(), reason="needs data/catalog/kagl")
def test_rank_remembers_facts_and_rewrite_endpoint_serves_them(monkeypatch, tmp_path):
    monkeypatch.setenv("ENGINE02_ENCODER", "hash")
    monkeypatch.setenv("ENGINE02_LLM", "none")
    monkeypatch.setenv("ENGINE02_DEMO", "1")
    monkeypatch.setenv("ENGINE02_REWRITE_CACHE", str(tmp_path / "rw.json"))
    import engine02.rewrite as rwmod
    monkeypatch.setattr(rwmod, "_CACHE", None)

    def fake(cards):
        return {c["id"]: "這件很適合你。" for c in cards}
    fake.name = "codex"
    monkeypatch.setattr(rwmod, "get_rewriter", lambda: fake)
    from fastapi.testclient import TestClient

    from engine02.api import app

    with TestClient(app) as c:
        r = c.post("/rank", json={"session_id": "rw1", "retrieval_text": "white shirt", "options": {"top_k": 3}}).json()
        assert any(it["reason_facts"] for it in r["items"])            # facts travel with each card
        out = c.post("/explain/rewrite", json={"session_id": "rw1"}).json()
        assert [x["item_id"] for x in out["cards"]] == [it["item_id"] for it in r["items"]]
        # a card with facts is rewritten; a card with none (「符合你設定的條件」) keeps its template
        for it, x in zip(r["items"], out["cards"]):
            assert x["source"] == ("codex" if it["reason_facts"] else "template")
        assert c.post("/explain/rewrite", json={"session_id": "never-ranked"}).status_code == 404
        ir = c.post("/intent/rank", json={"session_id": "rw2", "intent": {"item_type": "襯衫"}, "top_k": 2}).json()
        assert ir["engine02"]["rewrite"]["endpoint"] == "/explain/rewrite"
        assert c.post("/explain/rewrite", json={"session_id": ir["engine02"]["rewrite"]["session_id"]}).status_code == 200
