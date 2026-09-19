"""上衣／下身兩分區對照——只在 ENGINE01 這邊，不改 engine02/ 套件本身。

ENGINE02 的 `engine02/taxonomy.py::legacy_coarse()` 已經有一個 9 分類的粗分
（top/bottom/outerwear/dress/shoes/bag/accessory/jewelry/other），這正是
ENGINE02 回傳商品時 `category` 欄位會帶的值。這裡把這 9 類再分進兩個展示
分區：只有 `bottom` 歸下身區，其餘（含 outerwear/shoes/bag/accessory/
jewelry/other）一律歸上衣區——這是刻意簡化的暫定慣例（使用者這次只要求
上衣／下身兩區，不是三區或更細），之後要更細緻分類要跟前端／ENGINE02
負責人一起談，見 docs/interface-contract.md 第 6 節。
"""

from __future__ import annotations

from typing import Literal, Optional

from backend.shared.schemas import Intent

Zone = Literal["top", "bottom"]

_BOTTOM_CATEGORY = "bottom"
_DRESS_CATEGORY = "dress"


def zone_of(category: Optional[str]) -> Zone:
    """把 ENGINE02 回傳的粗分類對應成上衣或下身分區。查不到／None 的類別
    防禦性地歸上衣區，不讓未知類別讓呼叫端出錯或憑空消失。"""
    if category and category.strip().lower() == _BOTTOM_CATEGORY:
        return "bottom"
    return "top"


def is_dress(category: Optional[str]) -> bool:
    """連身裙／洋裝：依使用者規則歸上衣區顯示，但下身區要整個留空
    （不代預設品項去查 ENGINE02），因為連身裙本身就涵蓋了下半身，
    見 recommend.py 的 build_zoned_recommendation()。"""
    return bool(category) and category.strip().lower() == _DRESS_CATEGORY


# 使用者沒有明確要求某個分區時，代一個代表性品項去問 ENGINE02，
# 顏色／風格／場合／季節等既有資訊維持不變，只是把 item_type 換成
# 這個分區的代表詞——讓沒被明確要求的分區也能有東西可以展示、試穿。
_DEFAULT_ITEM_TYPE: dict[Zone, str] = {
    "top": "上衣",
    "bottom": "褲子",
}


def default_category_for_zone(zone: Zone, intent: Intent) -> str:
    """使用者沒明確要求 `zone` 這個分區時，回傳一個代表性品項名稱。
    呼叫端負責複製 `intent` 再把 `item_type` 換成這個回傳值，這裡
    不直接修改 `intent`（保持這個函式單純、可測試）。"""
    return _DEFAULT_ITEM_TYPE[zone]
