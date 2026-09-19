"""「幫你搭」——POST /style-me 背後的邏輯。

使用者明確要求「不能隨機配，要有理由」。做法分兩條路，依序嘗試：

1. 先問 ENGINE02 的 `POST /complete-look`：拿錨點商品去查真正依相容性排序過
   的互補商品，每一件都帶 ENGINE02 自己算出來的理由（顏色／風格相容之類），
   不是我們自己編的。
2. 錨點不在 ENGINE02 商品庫（最常見的情況：錨點其實是生圖，生成模組還沒
   做出來，但將來這條路一定會發生）：退回「代表性品項查詢＋LLM 生一句
   理由」——選出來的商品不是靠相容性分數，理由是 `codex exec` 現生的，
   會帶入目前對話脈絡（顏色／風格關鍵字／場合），比完全隨機配對更有根據。

兩條路都拿不到候選商品（該分區在商品庫裡真的沒有東西）才回傳 `None`。
"""

from __future__ import annotations

from typing import Optional

from backend.engine01_intent import engine02_client, llm_client, zones
from backend.engine01_intent.recommend import _products_of, _with_item_type
from backend.shared.schemas import Intent, ProductCard, UserProfile

_FALLBACK_REASON = "依你的風格偏好推薦這個搭配"


def _fallback_reason(candidate: ProductCard, target_zone: zones.Zone, intent: Intent, message_history: list[str]) -> str:
    reason = llm_client.generate_freeform_text(
        "用一句話（20 字以內，中文）說明為什麼這件商品適合搭配使用者這次想要的風格，"
        "不要用「我」「使用者」這種字眼，直接講搭配的理由。\n"
        f"商品名稱：{candidate.title}\n"
        f"使用者目前的偏好——顏色：{intent.colors}，風格關鍵字：{intent.style_keywords}，"
        f"場合：{intent.occasion}，季節：{intent.season}\n"
        f"這幾輪對話內容：{' '.join(message_history)}",
        timeout_seconds=20.0,
    )
    return reason or _FALLBACK_REASON


def build_styled_complement(
    session_id: str,
    round: int,
    message_history: list[str],
    intent: Intent,
    user_profile: UserProfile,
    anchor_product_id: str,
    anchor_zone: zones.Zone,
) -> Optional[tuple[zones.Zone, ProductCard]]:
    target_zone: zones.Zone = "bottom" if anchor_zone == "top" else "top"

    # 路徑一：ENGINE02 的相容性排序，真實理由。
    complete_look_products = engine02_client.complete_look(anchor_product_id, target_zone, k=1)
    if complete_look_products:
        return target_zone, complete_look_products[0]

    # 路徑二：錨點不在商品庫（或該分區沒有互補 slate）——退回代表性品項查詢，
    # 理由交給 LLM 生，可以參考對話脈絡。
    fallback_intent = _with_item_type(intent, zones.default_category_for_zone(target_zone, intent))
    fallback_result = engine02_client.intent_rank(
        fallback_intent, session_id, round, " ".join(message_history), top_k=1,
        user_sub=user_profile.sub, gender=user_profile.gender,
    )
    candidates = _products_of(fallback_result)
    if not candidates:
        return None  # 這個分區在商品庫裡真的沒有東西可以推薦

    candidate = candidates[0]
    reason = _fallback_reason(candidate, target_zone, intent, message_history)
    styled = candidate.model_copy(update={"reason": reason, "explanation_source": "llm_fallback"})
    return target_zone, styled
