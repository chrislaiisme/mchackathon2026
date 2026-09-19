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

from backend.engine01_intent import zones
from backend.shared.schemas import Intent, ProductCard, RetrievalResult

# 混合檢索＋可解釋性分數拆解比單純查資料庫慢，給比 Pinterest 那邊更寬的逾時。
_TIMEOUT_SECONDS = 20.0
_REWRITE_TIMEOUT_SECONDS = 90.0


def _base_url() -> str:
    # ENGINE02 負責人交接文件指定的本機啟動方式是
    # `uvicorn mcp_servers.catalog.main:app --port 8002`（Hermes app 遷移後的
    # 新路徑），不是原本以為的 `backend.engine02_retrieval.main:app --port 8002`
    # ——兩個模組內容目前逐位元組相同，只是這次推薦走新路徑。2026-09-19 port
    # 修正：預設值原本誤植成 8000，跟 ENGINE01 自己的 port 撞了，這裡只是
    # fallback 預設值，.env 有設 ENGINE02_BASE_URL 就不會用到這行。
    return os.environ.get("ENGINE02_BASE_URL", "http://localhost:8002")


# 前端 onboarding UI（frontend/components/intentweave/onboarding-experience.tsx
# 的 GENDER_OPTIONS）存的是英文字串，但 ENGINE02 的 engine02/intent_adapter.py::
# ZH_GENDER 只認得中文詞（"女"／"男"／"中性"⋯）——兩邊沒對過詞彙表，導致
# gender 訊號送過去等於沒送（_zh_lookup 找不到就直接丟掉，不會報錯，所以
# 一直沒被發現）。2026-09-19 真人測試發現：使用者 onboarding 選了 Woman，
# 卻被推薦男生襯衫，就是這個問題。這裡在送出前先轉成 ENGINE02 認得的中文詞，
# 不動 engine02/intent_adapter.py（那是對方負責的檔案）。
# ENGINE02 的 ZH_GENDER 表（engine02/intent_adapter.py）真正認得的輸出值只有這三種。
_ENGINE02_GENDER_VALUES = {"女", "男", "中性"}
_GENDER_TO_ENGINE02: dict[str, str] = {
    "woman": "女",
    "man": "男",
    "non-binary": "中性",
}


def _normalize_gender_for_engine02(gender: str) -> Optional[str]:
    """把前端 onboarding 存的英文性別字串轉成 ENGINE02 認得的中文詞；已經是中文詞
    的（例如測試或其他呼叫端直接給「女」）原樣放行，對不到的（例如「Prefer not to
    say」）回傳 None，呼叫端就不送這個訊號，不要硬塞一個查不到的值進去（那樣跟
    完全不送效果一樣，但會誤導看程式碼的人以為有在用）。"""
    trimmed = gender.strip()
    if trimmed in _ENGINE02_GENDER_VALUES:
        return trimmed
    return _GENDER_TO_ENGINE02.get(trimmed.lower())


def intent_rank(
    intent: Intent,
    session_id: str,
    round: int,
    message: str,
    top_k: int = 6,
    user_sub: Optional[str] = None,
    gender: Optional[str] = None,
    feedback: Optional[dict] = None,
    prev_intent: Optional[dict] = None,
    rewrite_key: Optional[str] = None,
) -> Optional[RetrievalResult]:
    """呼叫 ENGINE02 的 `POST /intent/rank`，回傳團隊介面契約的 `RetrievalResult`。

    `user_sub` 有值時把 `session_id` 組成 `f"{user_sub}:{session_id}"`，比照
    `/retrieve` 原本內建的「同一台 demo 機器上不同登入者不要共用一份 session」
    邏輯——這支端點本身沒做這件事，改呼叫端做。`gender` 有值時（先經過
    `_normalize_gender_for_engine02()` 轉成中文詞）塞進送出的 intent dict
    額外一個 `gender` key：`engine02/intent_adapter.py` 有明確的處理邏輯
    接住這個 key（即使它不在我們 `Intent` model 的正式欄位裡，見
    `intent_adapter.py:288-291` 的註解）。

    `feedback`（2026-09-19 新增）：ENGINE03 `POST /feedback` 回傳的
    `engine02_feedback` dict（`chosen_item_ids`／`rejected_item_ids`／
    `choice_history`／`design_weight_delta`），原封不動往下傳——ENGINE02 的
    `engine02/intent_adapter.py::feedback_from_engine03()` 已經確認這幾個 key
    都在它認得的欄位集合裡，會原樣放行，不需要在這裡多做任何轉換。**這個
    dict 絕對不能含有 `"ops"` key**：那會被 `engine02/api.py` 導去另一條給
    ENGINE02 自己 `/handshake` 協定用的路徑，跟 ENGINE03 真正回傳的形狀是
    兩回事，ENGINE03 回傳的 `engine02_feedback` 不會有這個 key，可以放心直傳。

    `prev_intent`（2026-09-19 新增）：上一輪的 `Intent`（呼叫 `/intent` 覆寫前
    的舊值，session_store 存的 `state.prev_intent`），讓 ENGINE02 同時回傳
    「用本輪意圖評」跟「用上一輪意圖評」兩個 match_score 做誠實度對照——這是
    ENGINE02 自己要求要顯示的既有機制，ENGINE01 之前一直沒送。
    """
    namespaced_session_id = f"{user_sub}:{session_id}" if user_sub else session_id
    if rewrite_key:
        namespaced_session_id = f"{namespaced_session_id}:{rewrite_key}"
    intent_payload = intent.model_dump()
    normalized_gender = _normalize_gender_for_engine02(gender) if gender else None
    if normalized_gender:
        intent_payload["gender"] = normalized_gender

    try:
        resp = requests.post(
            f"{_base_url()}/engine02/intent/rank",
            json={
                "session_id": namespaced_session_id,
                "round": round,
                "message": message,
                "intent": intent_payload,
                "top_k": top_k,
                "feedback": feedback,
                "prev_intent": prev_intent,
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


def rewrite_recommendation_reasons(rewrite_session_ids: list[str]) -> dict[str, dict]:
    """Return ENGINE02's fact-checked copy for cards in retained zone slates.

    ENGINE02 deliberately makes this a separate, slower endpoint. Failures are
    non-fatal: callers keep the ranking-time template reason rather than making a
    completed recommendation disappear just because optional copy refinement did
    not finish.
    """
    rewritten: dict[str, dict] = {}
    for rewrite_session_id in dict.fromkeys(rewrite_session_ids):
        try:
            resp = requests.post(
                f"{_base_url()}/engine02/explain/rewrite",
                json={"session_id": rewrite_session_id},
                timeout=_REWRITE_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            for card in resp.json().get("cards", []):
                item_id = card.get("item_id")
                text = card.get("text")
                if item_id and text:
                    rewritten[str(item_id)] = {
                        "reason": str(text),
                        "explanation_source": str(card.get("source") or "template"),
                    }
        except (requests.RequestException, ValueError, TypeError, AttributeError):
            continue
    return rewritten


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


def complete_look(anchor_item_id: str, target_zone: zones.Zone, k: int = 5) -> Optional[list[ProductCard]]:
    """呼叫 ENGINE02 的 `POST /complete-look`，回傳依相容性排序過、落在
    `target_zone` 那個分區的互補商品，每一件都帶 ENGINE02 自己算出來的
    真實 `reason`（`engine02/service.py::complete_look()` 的 `_slate_reason()`，
    根據 contributions／category_score／price 組字，不是隨機湊的）。

    HTTP 層的 `n_categories` 只能控制「回傳幾個依統計共現排出來的互補分類」，
    不能直接指定要哪一個分類——這裡固定要 8 個（等於 ENGINE02 目前粗分類的
    數量），確保 `target_zone` 對應的分類幾乎一定會出現在回傳的 slates 裡，
    再用 `zones.zone_of()` 從裡面挑出來。

    錨點不在商品庫（例如其實是生圖，ENGINE02 完全沒有這張圖的相容性資料，
    會回 400）、目標分區沒有出現在任何 slate 裡、連線失敗，一律回傳 `None`
    ——呼叫端（`style_me.py`）要有備援，不能假設這支一定有結果。
    """
    try:
        resp = requests.post(
            f"{_base_url()}/engine02/complete-look",
            json={"anchor_item_ids": [anchor_item_id], "n_categories": 8, "k": k},
            timeout=_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        slates = resp.json().get("slates", [])
        base = _base_url()
        for slate in slates:
            if zones.zone_of(slate.get("category")) != target_zone:
                continue
            cards: list[ProductCard] = []
            for item in slate.get("items", []):
                item_id = item.get("item_id")
                if not item_id:
                    continue
                cards.append(
                    ProductCard(
                        product_id=item_id,
                        image_url=f"{base}/engine02/images/{item_id}",
                        title=item.get("title") or "",
                        attributes={"category": slate.get("category")} if slate.get("category") else {},
                        score=float(item.get("score", 0.0)),
                        reason=item.get("reason") or "跟你選的這件很搭",
                        explanation_source="complete_look",
                    )
                )
            return cards if cards else None
        return None  # target_zone 對應的分類沒有出現在任何 slate 裡
    except (requests.RequestException, ValidationError, ValueError, TypeError, KeyError):
        return None
