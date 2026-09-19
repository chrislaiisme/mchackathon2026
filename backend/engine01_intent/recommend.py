"""上衣／下身兩分區推薦 orchestration——POST /recommend 背後的邏輯。

補上 ENGINE01 之前完全沒有的「呼叫 ENGINE02」這一段（見
docs/interface-contract.md 待確認事項），並且在 ENGINE02 既有的檢索能力
之上，組出使用者這次要的固定兩分區（上衣／下身，每區最多 6 件）展示邏輯：

- 有參考圖：呼叫 `engine02_client.visual_search()` 決定「主分區」的結果。
- 沒有參考圖、使用者要整套（`outfit_requested=True`）：兩個分區都當作
  使用者要的，各自代進代表性品項各查一次。
- 沒有參考圖、使用者要單品：先查一次拿到主分區的結果，另一分區代進代表性
  品項再查一次（除非是連身裙，下身區要整個留空，見 `zones.is_dress()`）。

任何一次 ENGINE02 呼叫失敗（`engine02_client` 回傳 `None`），對應分區就是
空的 `products`，不會讓整個端點掛掉。
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

import requests

from backend.engine01_intent import engine02_client, zones
from backend.engine01_intent.query_text import intent_to_query_text
from backend.shared.schemas import Intent, ProductCard, UserProfile, ZonedRecommendationResult, ZoneSlate

# 跟 main.py 的 _UPLOADS_DIR 算法一致——本機上傳的參考圖存在這裡，
# reference_image_url 是 "/files/<sub>/<file>" 這種相對網址，要轉回本機路徑
# 才能讀出 bytes 送給 ENGINE02。
_UPLOADS_DIR = Path(__file__).resolve().parents[2] / "data" / "uploads"
_IMAGE_FETCH_TIMEOUT_SECONDS = 10.0


def _resolve_image_bytes(reference_image: str) -> Optional[bytes]:
    """把 reference_image_url（本機 "/files/..." 或 Pinterest 的遠端網址）
    讀成 bytes。任何失敗（檔案不存在、網路錯誤）都回傳 None，呼叫端會退回
    純文字流程，不擋主流程。"""
    try:
        if reference_image.startswith("/files/"):
            local_path = _UPLOADS_DIR / reference_image.removeprefix("/files/")
            return local_path.read_bytes()
        if reference_image.startswith("http://") or reference_image.startswith("https://"):
            resp = requests.get(reference_image, timeout=_IMAGE_FETCH_TIMEOUT_SECONDS)
            resp.raise_for_status()
            return resp.content
        return None
    except (OSError, requests.RequestException):
        return None


def _with_item_type(intent: Intent, item_type: str) -> Intent:
    """回傳一份複製的 Intent，只換掉 item_type，其餘欄位（顏色／風格／場合／
    季節等）維持不變——用來組「代進某個分區的代表性品項」查詢，不動原本
    session 存的 intent。"""
    return intent.model_copy(update={"item_type": item_type})


def _with_style_fallback(intent: Intent, profile: UserProfile) -> Intent:
    """這一輪 style_keywords 是空的時候，退回 UserProfile.style_preferences
    當這次送出去的 style_keywords——只影響這次要送給 ENGINE02 的 payload，
    不寫回 session 裡存的 intent（使用者這輪真的講了風格時，個人檔案的
    舊偏好不會蓋過去；完全沒提風格時，才退回個人化的背景偏好）。"""
    if intent.style_keywords or not profile.style_preferences:
        return intent
    return intent.model_copy(update={"style_keywords": profile.style_preferences})


def _primary_zone_slate(products: list[ProductCard]) -> tuple[zones.Zone, bool, list[ProductCard]]:
    """依第一件（分數最高的）商品的 category 決定主分區跟是不是連身裙；
    查不到任何商品時（ENGINE02 連不上或沒有命中）預設歸上衣區，仍然標
    requested=True——這是使用者實際問的那一區，就算沒查到結果也一樣。"""
    if not products:
        return "top", False, products
    category = products[0].attributes.get("category")
    return zones.zone_of(category), zones.is_dress(category), products


def resolve_reference_image_for_retrieval(
    reference_image_url: Optional[str],
    reference_image_source: Literal["user_upload", "pinterest", "none"],
) -> Optional[str]:
    """決定這一輪要不要把參考圖送進 visual_search()——只信任使用者自己上傳的圖。

    2026-09-19 真人測試發現：Pinterest fallback 比對到的圖（板子上關鍵字硬湊出來的，
    使用者根本沒看過、沒選過）如果也送進 visual_search()，圖片相似度搜出來的第一件
    商品的 category 會直接決定「這輪主要在講哪個分區」，蓋掉使用者自己打的文字意圖——
    真人測試打「商務白色襯衫」，上衣區結果被換成一雙襪子就是這樣來的。使用者自己上傳
    的圖沒有這個問題（那是使用者自己選的、真的想比對的圖），所以只有 `user_upload`
    這個來源才放行，`pinterest`／`none` 一律當沒有參考圖，退回純文字流程。"""
    if reference_image_source == "user_upload":
        return reference_image_url
    return None


def build_zoned_recommendation(
    intent: Intent,
    session_id: str,
    round: int,
    message_history: list[str],
    reference_image: Optional[str],
    user_profile: UserProfile,
) -> ZonedRecommendationResult:
    message = " ".join(message_history)
    outgoing_intent = _with_style_fallback(intent, user_profile)

    # 有參考圖：先試著用圖片比對決定主分區的結果。
    if reference_image:
        image_bytes = _resolve_image_bytes(reference_image)
        if image_bytes is not None:
            visual_products = engine02_client.visual_search(
                image_bytes, intent_to_query_text(outgoing_intent), top_k=6
            )
            if visual_products is not None:
                primary_zone, is_dress, primary_products = _primary_zone_slate(visual_products)
                return _assemble_single_item_result(
                    outgoing_intent, session_id, round, message, user_profile,
                    primary_zone, is_dress, primary_products,
                )
        # 抓不到圖或 visual_search 失敗，不擋主流程，退回下面純文字流程。

    if outgoing_intent.outfit_requested:
        top_products = engine02_client.intent_rank(
            _with_item_type(outgoing_intent, zones.default_category_for_zone("top", outgoing_intent)),
            session_id, round, message, top_k=6,
            user_sub=user_profile.sub, gender=user_profile.gender,
        )
        bottom_products = engine02_client.intent_rank(
            _with_item_type(outgoing_intent, zones.default_category_for_zone("bottom", outgoing_intent)),
            session_id, round, message, top_k=6,
            user_sub=user_profile.sub, gender=user_profile.gender,
        )
        return ZonedRecommendationResult(
            session_id=session_id,
            round=round,
            outfit_requested=True,
            zones=[
                ZoneSlate(zone="top", requested=True, products=_products_of(top_products)),
                ZoneSlate(zone="bottom", requested=True, products=_products_of(bottom_products)),
            ],
        )

    # 單品：先用原始意圖查一次拿主分區的結果。
    primary_result = engine02_client.intent_rank(
        outgoing_intent, session_id, round, message, top_k=6,
        user_sub=user_profile.sub, gender=user_profile.gender,
    )
    primary_zone, is_dress, primary_products = _primary_zone_slate(_products_of(primary_result))
    return _assemble_single_item_result(
        outgoing_intent, session_id, round, message, user_profile,
        primary_zone, is_dress, primary_products,
    )


def _products_of(result) -> list[ProductCard]:
    # engine02_client 的兩支函式，一支回傳 RetrievalResult | None（intent_rank），
    # 一支直接回傳 list[ProductCard] | None（visual_search）——這裡統一接住
    # 兩種可能，失敗一律當空清單，呼叫端不用各自判斷型別。
    if result is None:
        return []
    if isinstance(result, list):
        return result
    return result.products


def _assemble_single_item_result(
    intent: Intent,
    session_id: str,
    round: int,
    message: str,
    user_profile: UserProfile,
    primary_zone: zones.Zone,
    is_dress: bool,
    primary_products: list[ProductCard],
) -> ZonedRecommendationResult:
    other_zone: zones.Zone = "bottom" if primary_zone == "top" else "top"

    if is_dress:
        # 連身裙：下身區整個留空，不呼叫 ENGINE02 代查——這是使用者明確
        # 要求的規則，不是查詢失敗。
        other_slate = ZoneSlate(zone=other_zone, requested=False, products=[])
    else:
        other_products = engine02_client.intent_rank(
            _with_item_type(intent, zones.default_category_for_zone(other_zone, intent)),
            session_id, round, message, top_k=6,
            user_sub=user_profile.sub, gender=user_profile.gender,
        )
        other_slate = ZoneSlate(zone=other_zone, requested=False, products=_products_of(other_products))

    primary_slate = ZoneSlate(zone=primary_zone, requested=True, products=primary_products)
    zone_slates = [primary_slate, other_slate]
    zone_slates.sort(key=lambda slate: slate.zone)  # 固定順序：bottom 在前、top 在後，回應穩定好測試

    return ZonedRecommendationResult(
        session_id=session_id,
        round=round,
        outfit_requested=False,
        zones=zone_slates,
    )
