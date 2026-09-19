"""engine02.rewrite: ChatGPT-voiced reasons (Codex CLI) -- layered, concrete, fact-checked,
never blocking /rank."""

import json
import subprocess
from pathlib import Path

import pytest

from engine02.rewrite import (CodexRewriter, RewriteCache, check, reason_facts_for_model, rewrite_cards,
                              situation_facts)

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "catalog" / "kagl" / "items.parquet"
VOCAB = ["Navy Blue", "Formal", "Black", "Casual", "Blue"]

SITUATION = [
    {"source": "travel", "label": "台北 → 札幌 約 2,696 km・飛行約 4.1 小時", "shown_on_card": False,
     "numbers": {"km": 2696, "travel_hours": 4.1}},
    {"source": "travel", "label": "往年同期晚上 7 點體感約 5°C → 厚外套、羊毛針織才夠暖", "shown_on_card": True,
     "numbers": {"hour": 19, "feels_c": 4.7}},
]
CARD = {"item_id": "a", "title": "Navy shirt", "template": "修身剪裁（+0.18）",
        "facts": [{"type": "design", "label": "修身剪裁", "direction": "has", "contribution": 0.18,
                   "serves_needs": ["看起來專業"]},
                  {"type": "context", "label": "往年同期晚上 7 點體感約 5°C → 厚外套、羊毛針織才夠暖",
                   "source": "travel", "contribution": 0.2}],
        "item": {"category": "top", "color": "Navy Blue", "season": "Summer", "style": "classic", "price": 790,
                 "currency": "TWD", "price_estimated": True,
                 "中文": {"品項": "襯衫", "顏色": "深藍色", "季節": "夏季", "風格": "經典"}}}
CARD_B = {"item_id": "b", "title": "Dress", "template": "避開正式感（+0.09）",
          "facts": [{"type": "design", "label": "正式感", "direction": "avoids", "contribution": 0.09}],
          "item": {"category": "dress", "color": "Blue", "中文": {"品項": "洋裝", "顏色": "藍色"}}}


def test_concrete_numbers_from_the_facts_pass_and_invented_ones_do_not():
    ok = "飛行約 4 小時、晚上 7 點體感只有 5°C；這件 Navy Blue 修身襯衫估計價 790 元，裡面加件針織剛好。"
    assert check(ok, CARD, VOCAB, SITUATION) is None                       # 4.1 -> 4, 4.7 -> 5 are roundings
    assert check("札幌約 2,700 公里遠，修身剪裁很適合。", CARD, VOCAB, SITUATION) is None
    assert "number 12" in check("晚上只有 12°C，修身剪裁很適合。", CARD, VOCAB, SITUATION)
    assert "0.18" in check("修身剪裁加了 0.18 分。", CARD, VOCAB, SITUATION)       # scores are not facts
    assert "catalogue word" in check("這件 Black 的修身剪裁很適合你。", CARD, VOCAB, SITUATION)
    assert "estimate" in check("修身剪裁，只要 790 元。", CARD, VOCAB, SITUATION)  # estimated price, unlabelled
    assert "longer" in check("很" * 151, CARD, VOCAB, SITUATION)
    assert check("", CARD, VOCAB) == "empty"


def test_chinese_attribute_words_must_be_this_cards_own():
    # a colour / style / season the item does not have is refused even when written in Chinese
    # (the catalogue-vocabulary check alone only knows the English words)
    assert check("這件深藍色襯衫走經典風，夏季正好穿。", CARD, VOCAB, SITUATION) is None
    assert check("這件海軍藍襯衫很經典。", CARD, VOCAB, SITUATION) is None           # same colour family
    assert "colour" in check("這件黑色襯衫很經典。", CARD, VOCAB, SITUATION)
    assert "風格" in check("這件深藍色襯衫走前衛風。", CARD, VOCAB, SITUATION)
    assert "季節" in check("這件深藍色襯衫是春季款。", CARD, VOCAB, SITUATION)
    # a word the facts themselves use is fine even if it is not the item's attribute
    sit = SITUATION + [{"source": "festival", "label": "中秋烤肉：深色、好活動的休閒穿搭", "shown_on_card": True, "numbers": {}}]
    assert check("中秋烤肉穿深色好活動，這件深藍色襯衫夠休閒。", CARD, VOCAB, sit) is None


def test_no_false_alarms_on_the_cards_own_words_and_no_relative_days():
    loose = {**CARD_B, "item": {"category": "bottom", "color": "Yellow", "fit": "loose",
                                "中文": {"品項": "裙子", "顏色": "黃色", "版型": "寬鬆"}}}
    assert check("這件黃色裙子是寬鬆版型，好活動。", loose, VOCAB + ["寬鬆版型"]) is None
    assert check("深藍色襯衫試穿時確認是否合身。", CARD, VOCAB, SITUATION) is None      # 合身 as an ordinary word
    assert "後天" in check("後天體感 5°C，這件深藍色襯衫夠用。", CARD, VOCAB, SITUATION)
    today = SITUATION + [{"source": "mood", "label": "今天元氣滿滿 → 飽和色走起", "shown_on_card": True, "numbers": {}}]
    assert check("今天元氣滿滿，這件深藍色襯衫很經典。", CARD, VOCAB, today) is None


def test_a_refused_sentence_gets_one_retry_with_the_reason():
    calls = []

    def fake(cards, situation, request=None):
        calls.append(cards)
        if len(calls) == 1:
            return {"a": "這件黑色襯衫很經典。"}
        assert cards[0]["上次被退回"]["原因"]
        return {"a": "這件深藍色襯衫很經典。"}
    fake.name = "codex"
    out = rewrite_cards([CARD], VOCAB, fake, None, situation=SITUATION)["cards"][0]
    assert len(calls) == 2 and out["source"] == "codex" and out["retried"] and out["rejected"] is None


def test_the_model_never_sees_ranking_scores_and_gets_situation_and_item():
    seen = {}

    def fake(cards, situation, request=None):
        seen["cards"], seen["situation"] = cards, situation
        return {"a": "飛行約 4 小時、晚上體感約 5°C，這件 Navy Blue 修身剪裁襯衫很俐落。"}
    fake.name = "codex"
    out = rewrite_cards([CARD], VOCAB, fake, None, situation=SITUATION)
    assert out["cards"][0]["source"] == "codex"
    card = seen["cards"][0]
    assert "contribution" not in json.dumps(card["reasons"]) and card["item"]["color"] == "Navy Blue"
    assert seen["situation"] == [SITUATION[0]]                   # the rewriter's shared part: background only
    assert card["situation"] == [SITUATION[1]]                   # this card's own, cited situation


def test_a_card_not_picked_for_the_weather_cannot_be_explained_by_it():
    from engine02.rewrite import own_situation
    own, bg = own_situation(CARD_B, SITUATION)
    assert own == [] and bg == [SITUATION[0]]
    seen = {}

    def fake(cards, situation, request=None):
        seen["card"] = cards[0]
        return {"b": "晚上 7 點體感約 5°C，這件藍色洋裝避開了正式感。"}
    fake.name = "codex"
    out = rewrite_cards([CARD_B], VOCAB, fake, None, situation=SITUATION)["cards"][0]
    assert seen["card"]["situation"] == []
    assert out["source"] == "template" and "number" in out["rejected"]     # 5°C is not this card's
    assert reason_facts_for_model(CARD["facts"])[0] == {k: v for k, v in CARD["facts"][0].items() if k != "contribution"}


def test_rewrite_keeps_template_when_the_model_invents_and_caches_when_faithful(tmp_path):
    def fake(cards, situation, request=None):
        return {"a": "修身剪裁，讓你面試看起來更專業。", "b": "這件是 Black 的，很正式。"}
    fake.name = "codex"
    store = RewriteCache(tmp_path / "c.json")
    a, b = rewrite_cards([CARD, CARD_B], VOCAB, fake, store)["cards"]
    assert a["source"] == "codex"
    assert b["source"] == "template" and b["text"] == CARD_B["template"] and b["rejected"] and b["rejected_text"]
    again = rewrite_cards([CARD], VOCAB, lambda *a: pytest.fail("called again"), RewriteCache(tmp_path / "c.json"))
    assert again["cards"][0]["source"] == "cache"
    # a different situation is a different sentence, not a cache hit
    other = rewrite_cards([CARD], VOCAB, None, RewriteCache(tmp_path / "c.json"), situation=SITUATION)
    assert other["cards"][0]["source"] == "template"


def test_a_failing_or_missing_rewriter_leaves_every_template_in_place():
    def boom(cards, situation, request=None):
        raise RuntimeError("signed out")
    out = rewrite_cards([CARD, CARD_B], VOCAB, boom, None)
    assert [c["source"] for c in out["cards"]] == ["template", "template"] and "signed out" in out["error"]
    out = rewrite_cards([CARD], VOCAB, None, None)
    assert out["backend"] is None and out["cards"][0]["text"] == CARD["template"]


def test_situation_facts_carry_the_real_numbers(monkeypatch):
    from datetime import date

    from engine02.contracts import ContextInput
    monkeypatch.setenv("ENGINE02_DEMO", "1")
    sit = situation_facts(ContextInput(city="新竹", lat=24.8, lon=120.97, event_date="2026-09-22", commute="scooter"),
                          today=date(2026, 9, 19))
    assert sit and all({"source", "label", "shown_on_card", "numbers"} <= set(s) for s in sit)
    assert all("lat" not in s["numbers"] and "ramp" not in s["numbers"] for s in sit)
    assert situation_facts(None) == []


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
    assert rw([{"id": "a", "title": "t", "reasons": []}], SITUATION) == {"a": "修身剪裁很適合你。"}
    cmd = seen["cmd"]
    assert cmd[1] == "exec" and "--ephemeral" in cmd and cmd[cmd.index("--sandbox") + 1] == "read-only"
    assert cmd[-1] == "-" and "2,696" in seen["input"] and "第一層" in seen["input"]


def test_codex_failure_and_timeout_raise_so_templates_stay(tmp_path):
    exe = tmp_path / "codex.exe"
    exe.write_text("")

    def slow(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 1)

    with pytest.raises(Exception, match="timed out"):
        CodexRewriter(bin=str(exe), run=slow)([{"id": "a", "reasons": []}])
    assert CodexRewriter(bin="definitely-not-installed-codex").status()["available"] is False


@pytest.mark.skipif(not CATALOG.exists(), reason="needs data/catalog/kagl")
def test_rank_remembers_facts_and_rewrite_endpoint_serves_them(monkeypatch, tmp_path):
    monkeypatch.setenv("ENGINE02_ENCODER", "hash")
    monkeypatch.setenv("ENGINE02_LLM", "none")
    monkeypatch.setenv("ENGINE02_DEMO", "1")
    monkeypatch.setenv("ENGINE02_REWRITE_CACHE", str(tmp_path / "rw.json"))
    import engine02.rewrite as rwmod
    monkeypatch.setattr(rwmod, "_CACHE", None)
    seen = {}

    def fake(cards, situation, request=None):
        seen["item"] = cards[0]["item"]
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
        for it, x in zip(r["items"], out["cards"]):
            assert x["source"] == ("codex" if it["reason_facts"] else "template")
        assert seen["item"].get("category") and "price" in seen["item"]    # the item's own facts went along
        assert c.post("/explain/rewrite", json={"session_id": "never-ranked"}).status_code == 404
        ir = c.post("/intent/rank", json={"session_id": "rw2", "intent": {"item_type": "襯衫"}, "top_k": 2}).json()
        assert ir["engine02"]["rewrite"]["endpoint"] == "/explain/rewrite"
        assert c.post("/explain/rewrite", json={"session_id": ir["engine02"]["rewrite"]["session_id"]}).status_code == 200
