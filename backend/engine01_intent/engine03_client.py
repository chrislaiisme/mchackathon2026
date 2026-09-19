"""HTTP client for ENGINE03（backend/engine03_feedback/），從 ENGINE01 這邊呼叫。

背景：這是現場真正在跑的「前端直打 ENGINE01、ENGINE01 直打 ENGINE02」架構的最後一段
缺口——ENGINE03 早就有真實實作（`backend/engine03_feedback/`，`POST /feedback`），但
一直沒有人從 ENGINE01 這邊接上去。不走 `bff/main.py` 那套平行的 Hermes orchestration
（那是給另一條技術棧用的，跟這裡的 session_store 會重複，且現場沒有東西實際呼叫它）。

跟 `engine02_client.py` 一樣的防禦哲學：連線失敗、逾時、非預期回應一律回傳 `None`，
不往外丟例外，讓 `/feedback` 端點可以回一個乾淨的 502，不會讓 ENGINE03 掛掉連帶弄垮
ENGINE01。**跟 ENGINE02 不同的地方**：ENGINE03 的 `POST /feedback` 掛了
`Depends(get_current_user)`（跟 ENGINE01 共用同一把 `SESSION_SECRET`），一定要把
呼叫端的 `Authorization` header 原樣往下轉，不然 `DEV_BYPASS_AUTH=false` 時會直接
401——ENGINE02 完全不驗證，這裡不能照抄 engine02_client.py 省略這一步。
"""

from __future__ import annotations

import os
from typing import Optional

import requests

# 這輪回饋的批次量通常不大（幾張卡片＋一組整套喜歡），不需要 engine02_client.py
# 那種為了混合檢索多留的寬逾時。
_TIMEOUT_SECONDS = 10.0


def _base_url() -> str:
    return os.environ.get("ENGINE03_BASE_URL", "http://localhost:8003")


def submit_feedback(
    session_id: str,
    previous_rounds: list[dict],
    current_round: dict,
    authorization: Optional[str] = None,
) -> Optional[dict]:
    """呼叫 ENGINE03 的 `POST /feedback`，回傳原始的 `Engine3Response` dict（不轉成
    pydantic model——那是 ENGINE03 自己的 `contracts.py`，ENGINE01 只當它是黑盒子
    轉送，不 import 對方的實作模組，維持跟 `engine02_client.py` 一樣「用自己的
    `backend/shared/schemas.py` 當交界」的原則）。

    `current_round` 是 ENGINE03 `FeedbackRound` 的形狀（`round`／`shown_item_ids`／
    `shown_generated_item_ids`／`item_feedbacks`／`outfit_feedbacks`），呼叫端
    （`main.py::post_feedback()`）負責組好；這裡只加 `session_id`／`previous_rounds`
    兩個 `Engine3Request` 額外要求的欄位，不重新驗證內容——驗證是 ENGINE03 自己的
    responsibility（pydantic model_validator），這裡驗證失敗會直接是 4xx，一樣被
    當成失敗回傳 `None`。
    """
    try:
        resp = requests.post(
            f"{_base_url()}/feedback",
            json={"session_id": session_id, "previous_rounds": previous_rounds, **current_round},
            headers={"Authorization": authorization} if authorization else {},
            timeout=_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data.get("engine02_feedback"), dict) else None
    except (requests.RequestException, ValueError, TypeError, AttributeError, KeyError):
        return None
