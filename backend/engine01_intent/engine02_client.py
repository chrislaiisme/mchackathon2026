"""HTTP client for ENGINE02, called from ENGINE01's orchestration (recommend.py).

背景：ENGINE01 之前完全沒有程式碼呼叫 ENGINE02（docs/interface-contract.md
明文列出的待確認事項），這支模組補上這個缺口。整合端點是 ENGINE02 負責人在
交接文件裡指名的 `POST /intent/rank`（"the single touchpoint for ENGINE01
team"）——透過既有介接層掛在 `{ENGINE02_BASE_URL}/engine02/intent/rank`，
跟 `backend/engine02_retrieval/main.py` 的 `POST /retrieve` 呼叫的是同一套
`engine02/intent_adapter.py` 邏輯、回傳同一個 `RetrievalResult` 形狀，差別
只是 `/intent/rank` 沒有內建 bearer token 驗證跟 session 前綴——這兩件事
改這裡自己做。

跟 `backend/pinterest/client.py`、`engine02/llm.py` 一樣的防禦哲學：連線
失敗、逾時、非預期回應一律回傳 `None`，不往外丟例外，讓 `/recommend` 端點
可以優雅降級（該分區就回空清單），不會讓 ENGINE02 掛掉連帶弄垮 ENGINE01。
"""

from __future__ import annotations

import base64
import os
from typing import Optional

import requests
from pydantic import ValidationError

from backend.shared.schemas import Intent, ProductCard, RetrievalResult

# 混合檢索＋可解釋性分數拆解比單純查資料庫慢，給比 Pinterest 那邊更寬的逾時。
_TIMEOUT_SECONDS = 20.0


def _base_url() -> str:
    # ENGINE02 負責人交接文件指定的本機啟動方式是
    # `uvicorn mcp_servers.catalog.main:app --port 8000`（Hermes app 遷移後的
    # 新路徑），不是原本以為的 `backend.engine02_retrieval.main:app --port 8002`
    # ——兩個模組內容目前逐位元組相同，只是這次推薦走新路徑跟新 port。
    return os.environ.get("ENGINE02_BASE_URL", "http://localhost:8000")


def intent_rank(
    intent: Intent,
    session_id: str,
    round: int,
    message: str,
    top_k: int = 6,
    user_sub: Optional[str] = None,
    gender: Optional[str] = None,
) -> Optional[RetrievalResult]:
    """呼叫 ENGINE02 的 `POST /intent/rank`，回傳團隊介面契約的 `RetrievalResult`。

    `user_sub` 有值時把 `session_id` 組成 `f"{user_sub}:{session_id}"`，比照
    `/retrieve` 原本內建的「同一台 demo 機器上不同登入者不要共用一份 session」
    邏輯——這支端點本身沒做這件事，改呼叫端做。`gender` 有值時塞進送出的
    intent dict 額外一個 `gender` key：`engine02/intent_adapter.py` 有明確
    的處理邏輯接住這個 key（即使它不在我們 `Intent` model 的正式欄位裡，
    見 `intent_adapter.py:288-291` 的註解）。
    """
    namespaced_session_id = f"{user_sub}:{session_id}" if user_sub else session_id
    intent_payload = intent.model_dump()
    if gender:
        intent_payload["gender"] = gender

    try:
        resp = requests.post(
            f"{_base_url()}/engine02/intent/rank",
            json={
                "session_id": namespaced_session_id,
                "round": round,
                "message": message,
                "intent": intent_payload,
                "top_k": top_k,
            },
            timeout=_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        # ENGINE02 的回應除了 RetrievalResult 的欄位之外還夾帶一個 "engine02"
        # debug 區塊（unresolved_from_intent 等）；RetrievalResult 沒有定義
        # 這個欄位，Pydantic v2 對未宣告的多餘欄位預設就是忽略，不用先手動濾掉。
        return RetrievalResult(**resp.json())
    except (requests.RequestException, ValidationError, ValueError, TypeError):
        # 連線失敗、逾時、回應格式跟預期不符……任何原因都當成「這次問不到」，
        # 不要讓例外往上炸壞整個 /recommend 端點。
        return None


def visual_search(
    image_bytes: bytes, retrieval_text: str, top_k: int = 6
) -> Optional[list[ProductCard]]:
    """呼叫 ENGINE02 的 `POST /visual-search`，把原始回應轉成縮水版 `ProductCard`。

    `retrieval_text` 一定要是非空字串（見 `query_text.py` 的說明）——這支端點
    在 `retrieval_text` 是空字串時，查詢向量會被 ENGINE02 那邊一個已知 bug
    稀釋成「80% 一個通用英文字 + 20% 照片」，帶非空文字可以繞開它，不用等
    ENGINE02 那邊修（見 docs/research/visual-search-gaps.md 缺口 #1）。

    回傳的是**縮水版** `ProductCard`：這支端點回的是 ENGINE02 原始排序結果
    （`RankedItem`），不是 `/intent/rank` 那樣經過 `response_to_retrieval_result()`
    轉換過的完整可解釋性資料，所以 `reason`／`explanation_source` 這裡只能
    給一個固定說明，沒有逐項貢獻拆解——這是真實的能力落差，不是漏做，見
    docs/interface-contract.md 第 6 節。
    """
    try:
        resp = requests.post(
            f"{_base_url()}/engine02/visual-search",
            json={
                "image_base64": base64.b64encode(image_bytes).decode("ascii"),
                "retrieval_text": retrieval_text,
                "top_k": top_k,
                "profile": False,  # 不需要設計要素側寫，只要商品排序結果
            },
            timeout=_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("response", {}).get("items", [])
        base = _base_url()
        cards: list[ProductCard] = []
        for item in items:
            item_id = item.get("item_id")
            if not item_id:
                continue
            category = item.get("category")
            cards.append(
                ProductCard(
                    product_id=item_id,
                    image_url=f"{base}/engine02/images/{item_id}",
                    title=item.get("title") or "",
                    attributes={"category": category} if category else {},
                    score=float(item.get("score", 0.0)),
                    reason="依你上傳的參考圖比對",
                    explanation_source="visual_search",
                )
            )
        return cards
    except (requests.RequestException, ValidationError, ValueError, TypeError, KeyError):
        return None
