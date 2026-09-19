"""Pinterest API v5 用戶端 —— 從團隊策展的板子裡，比對出一張跟目前 Intent 最相關的參考圖。

背景（詳見 docs/pinterest-and-generation.md）：Pinterest API v5 的 Trial access
只能讀寫／搜尋連結帳號自己的 board／pin，沒辦法對整個公開網站做關鍵字搜尋。實際
做法是團隊先手動策展一個板子（放理想的參考／目標圖），這支模組再從這個板子裡挑
一張跟目前 Intent 最相關的圖。**這張圖只能給 ENGINE02 內部當參考特徵／生成 prompt
素材，絕對不能顯示在使用者畫面上**（版權考量，這條規則使用者已經在 2026-09-19
確認過，這次新增的「使用者沒上傳圖就用 Pinterest 圖」用途也一樣要遵守）。

這支模組刻意處處防禦：沒有 token、板子找不到、API 逾時、或任何其他例外，
一律回傳 None，絕對不能讓 Pinterest 查詢失敗擋住 POST /intent 的主流程——
跟 engine02/llm.py 的 openai_llm()「有最好、沒有就優雅退回」是同一種設計哲學。
"""

from __future__ import annotations

import os
from typing import Optional

import requests

from backend.shared.schemas import Intent

_API_BASE = "https://api.pinterest.com/v5"
_TIMEOUT_SECONDS = 5.0

# 板子名稱 -> board_id 的快取。一場 demo 裡板子不會改名，沒必要每一輪 /intent
# 都重新打一次 GET /boards 列表去找 id，用一個 process 內的簡單 dict 快取就夠。
_board_id_cache: dict[str, Optional[str]] = {}


def _access_token() -> Optional[str]:
    """讀 PINTEREST_ACCESS_TOKEN，沒設定就回傳 None（呼叫端要能優雅跳過，不是報錯）。"""
    return os.environ.get("PINTEREST_ACCESS_TOKEN") or None


def _board_name() -> str:
    """要比對的板子名稱，預設是使用者這次提供的板子（intentweave-references）。"""
    return os.environ.get("PINTEREST_BOARD_NAME", "intentweave-references")


def _normalize_board_name(name: str) -> str:
    """比對板子名稱前先正規化：轉小寫、去頭尾空白、把連字號／底線都當空白，
    這樣網址 slug（"intentweave-references"）跟顯示名稱（"IntentWeave References"）
    才會被視為同一個板子。"""
    return name.strip().lower().replace("-", " ").replace("_", " ")


def _find_board_id(token: str, board_name: str) -> Optional[str]:
    """依板子名稱找 board_id；找不到、逾時或 API 出錯都回傳 None，並快取結果。"""
    if board_name in _board_id_cache:
        return _board_id_cache[board_name]

    board_id: Optional[str] = None
    try:
        resp = requests.get(
            f"{_API_BASE}/boards",
            headers={"Authorization": f"Bearer {token}"},
            params={"page_size": 100},
            timeout=_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        # 2026-09-19 真實 API 驗證時發現：網址 slug（連字號分隔）跟板子實際
        # 顯示名稱（空白分隔，例如 "IntentWeave References"）不一樣，直接
        # 完全比對字串會找不到板子。這裡把連字號／底線都當成空白處理再比對，
        # 兩種寫法都吃得到，比較不會因為這種常見落差就靜默找不到板子。
        target = _normalize_board_name(board_name)
        for board in resp.json().get("items", []):
            if _normalize_board_name(str(board.get("name", ""))) == target:
                board_id = board.get("id")
                break
    except Exception:
        # 任何原因（網路、額度、格式改變）都當成「這次找不到板子」，不要讓例外往上炸。
        board_id = None

    _board_id_cache[board_name] = board_id
    return board_id


def _fetch_pins(token: str, board_id: str) -> list[dict]:
    """拉這個板子上全部的 pin（標題／描述／圖片網址），出錯就回傳空清單。"""
    try:
        resp = requests.get(
            f"{_API_BASE}/boards/{board_id}/pins",
            headers={"Authorization": f"Bearer {token}"},
            params={"page_size": 100},
            timeout=_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        return resp.json().get("items", [])
    except Exception:
        return []


def _pin_image_url(pin: dict) -> Optional[str]:
    """從 pin 的 media.images 裡挑一張圖的網址；Pinterest 會回好幾種尺寸，這裡
    只是要給 ENGINE02 當內部參考素材，不要求特定解析度，挑得到就好。"""
    images = (pin.get("media") or {}).get("images") or {}
    for size in images.values():
        url = (size or {}).get("url")
        if url:
            return url
    return None


# 2026-09-19 真實 API 驗證時發現：團隊板子上的 pin 標題/描述全部是英文
# （策展來源是英文的穿搭圖庫），但 Intent 欄位幾乎都是中文——原本純子字串
# 比對「黑色」跟「black」永遠對不上，等於整個比對邏輯實際命中率是 0%。
# 這裡補一個小型中英對照表，只涵蓋最常見的顏色／風格詞彙，讓中文關鍵字
# 也能命中英文 pin 文字；沒收錄的詞就維持原樣比對（例如剛好中英同形的
# 品牌詞、或本來就是英文的欄位值）。刻意不做完整的機器翻譯，這仍然是
# best-effort 比對，不是正式的多語言檢索。
_ZH_EN_FASHION_TERMS: dict[str, str] = {
    "黑色": "black", "白色": "white", "灰色": "gray", "咖啡色": "brown",
    "棕色": "brown", "卡其色": "khaki", "米色": "beige", "奶油色": "cream",
    "藍色": "blue", "海軍藍": "navy", "紅色": "red", "綠色": "green",
    "粉色": "pink", "粉紅色": "pink", "黃色": "yellow", "紫色": "purple",
    "橘色": "orange", "橙色": "orange",
    "復古": "vintage", "老錢風": "old money", "簡約": "minimalist",
    "極簡": "minimalist", "街頭": "street style", "街頭風": "street style",
    "學院風": "preppy", "休閒": "casual", "正式": "formal", "優雅": "elegant",
    "文青": "aesthetic", "文藝": "poetcore", "秋冬": "fall", "春夏": "summer",
}


def _intent_keywords(intent: Intent) -> list[str]:
    """把 Intent 裡有值的欄位攤平成一組關鍵字，用來跟 pin 的文字做子字串比對。

    刻意不斷詞（中英文混雜，中文沒有空白分詞不好處理），直接拿整個欄位值當
    一個關鍵字去檢查是不是 pin 文字的子字串——夠簡單、夠快，符合這是內部
    best-effort 比對，不是正式的檢索演算法的定位。有中英對照的詞會兩種都
    加進去比對（見 `_ZH_EN_FASHION_TERMS`），沒有的維持原樣。
    """
    keywords: list[str] = []
    keywords.extend(intent.colors)
    keywords.extend(intent.style_keywords)
    for value in (
        intent.item_type,
        intent.occasion,
        intent.material,
        intent.season,
        intent.fit,
        intent.pattern,
        intent.collar,
    ):
        if value:
            keywords.append(value)
    keywords = [k for k in keywords if k and k.strip()]
    translated = [_ZH_EN_FASHION_TERMS[k] for k in keywords if k in _ZH_EN_FASHION_TERMS]
    return keywords + translated


def find_reference_image(intent: Intent) -> Optional[str]:
    """依目前的 Intent，從團隊 Pinterest 板子裡找一張最相關的圖網址。

    比對邏輯：Intent 攤平出來的每個關鍵字，是不是任一 pin 的標題/描述/alt_text
    的子字串（不分大小寫），命中數最高且至少命中一個的 pin 勝出。沒有 token、
    板子找不到、沒有任何命中、或任何例外，一律回傳 None——呼叫端（main.py 的
    post_intent）看到 None 就直接跳過，不帶參考圖繼續跑，這是代辦事項明確
    要求的行為（「Pinterest 裡沒有符合的就不用圖片進去 ENGINE02 推薦」）。
    """
    try:
        token = _access_token()
        if not token:
            return None

        keywords = _intent_keywords(intent)
        if not keywords:
            return None

        board_id = _find_board_id(token, _board_name())
        if not board_id:
            return None

        pins = _fetch_pins(token, board_id)
        if not pins:
            return None

        best_pin: Optional[dict] = None
        best_score = 0
        for pin in pins:
            text = " ".join(
                str(pin.get(field, "")) for field in ("title", "description", "alt_text")
            ).lower()
            score = sum(1 for kw in keywords if kw.lower() in text)
            if score > best_score:
                best_score = score
                best_pin = pin

        if best_pin is None or best_score == 0:
            return None

        return _pin_image_url(best_pin)
    except Exception:
        # 最外層再包一次——任何沒預料到的錯誤都不能讓 /intent 掛掉，寧可沒有參考圖。
        return None
