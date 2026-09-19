"""`POST /outfit-pair` 與 `bff/images/outfit_pair.py` 的測試。

不跑真的 codex（太慢、要吃額度）：端點測試靠 monkeypatch 替換 `bff.main.pair_outfit`
（跟 `bff/main.py` 裡 `_post` 的「測試會替換這個函式」是同一套做法）；模組本身的
子行程接線用 `--dry-run` 驗證，真的會跑一次 `pair_outfit.py`，但那條路徑不呼叫 codex。
"""
from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from bff import main as bff_main
from bff.images.outfit_pair import OutfitPairUnavailable, pair_outfit

client = TestClient(bff_main.app)

_TOPS = [
    {"id": "top-ai-1", "label": "落肩箱型", "keywords": {"item_type": "上衣", "fit": "寬鬆"}},
    {"id": "top-ai-2", "label": "合身短版", "keywords": {"item_type": "上衣", "fit": "合身"}},
]
_BOTTOMS = [
    {"id": "bottom-ai-1", "label": "寬鬆桶褲", "keywords": {"item_type": "褲子", "fit": "寬鬆"}},
    {"id": "bottom-ai-2", "label": "錐形褲", "keywords": {"item_type": "褲子", "fit": "合身"}},
]


def _payload() -> dict[str, Any]:
    return {"session_id": "s1", "intent": {"item_type": "牛仔褲", "colors": ["深色"], "fit": "寬鬆"},
            "tops": _TOPS, "bottoms": _BOTTOMS}


# --- 正常路徑：pair_outfit() 回傳合法結果就原樣透出 -------------------------

def test_outfit_pair_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bff_main, "pair_outfit", lambda intent, tops, bottoms: {
        "top_id": "top-ai-2", "bottom_id": "bottom-ai-1",
        "reason": "合身短版收窄上身，寬鬆桶褲往下放寬，比例對得起來。", "source": "llm"})

    r = client.post("/outfit-pair", json=_payload())

    assert r.status_code == 200
    body = r.json()
    assert body == {"top_id": "top-ai-2", "bottom_id": "bottom-ai-1",
                    "reason": "合身短版收窄上身，寬鬆桶褲往下放寬，比例對得起來。", "source": "llm"}


# --- 第二層退場之一：腳本跑不起來（找不到腳本／逾時／stdout 壞掉） -----------

def test_outfit_pair_falls_back_when_script_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(intent: Any, tops: Any, bottoms: Any) -> dict[str, Any]:
        raise OutfitPairUnavailable("pair_outfit.py 超過 60 秒沒回來")

    monkeypatch.setattr(bff_main, "pair_outfit", _boom)

    r = client.post("/outfit-pair", json=_payload())

    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "fallback"
    assert body["top_id"] == "top-ai-1"       # tops[0]
    assert body["bottom_id"] == "bottom-ai-1"  # bottoms[0]
    assert body["reason"]


# --- 第二層退場之二：腳本回傳的 id 不在這次請求的清單裡 ----------------------

def test_outfit_pair_falls_back_when_id_not_in_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bff_main, "pair_outfit", lambda intent, tops, bottoms: {
        "top_id": "top-ai-99", "bottom_id": "bottom-ai-1",  # top-ai-99 不在這次的候選裡
        "reason": "隨便一句理由", "source": "llm"})

    r = client.post("/outfit-pair", json=_payload())

    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "fallback"
    assert body["top_id"] == "top-ai-1"
    assert body["bottom_id"] == "bottom-ai-1"


# --- 請求本身不合法：tops／bottoms 給空清單，永遠 200 的例外 -----------------

@pytest.mark.parametrize("field", ["tops", "bottoms"])
def test_outfit_pair_rejects_empty_candidate_list(field: str) -> None:
    payload = _payload()
    payload[field] = []

    r = client.post("/outfit-pair", json=payload)

    assert r.status_code == 422


# --- 模組本身：真的呼叫 pair_outfit.py（--dry-run，不叫 codex）驗證接線 -----

def test_pair_outfit_module_dry_run_hits_real_script() -> None:
    result = pair_outfit(_payload()["intent"], _TOPS, _BOTTOMS, dry_run=True)

    # --dry-run 不呼叫模型，一定是腳本自己組出來的退場結果；驗的是「子行程/JSON
    # 接線是通的」，不是配對判斷本身（判斷邏輯屬於 pair_outfit.py／SKILL.md）。
    assert result["source"] == "fallback"
    assert result["top_id"] == "top-ai-1"
    assert result["bottom_id"] == "bottom-ai-1"
    assert result["reason"]
