"""backend/engine01_intent/zones.py 的單元測試。"""

from __future__ import annotations

from backend.engine01_intent import zones
from backend.shared.schemas import Intent


def test_zone_of_bottom():
    assert zones.zone_of("bottom") == "bottom"
    assert zones.zone_of("Bottom") == "bottom"  # 大小寫不拘
    assert zones.zone_of(" bottom ") == "bottom"  # 頭尾空白不拘


def test_zone_of_everything_else_is_top():
    for category in ("top", "outerwear", "dress", "shoes", "bag", "accessory", "jewelry", "other", None, ""):
        assert zones.zone_of(category) == "top"


def test_is_dress():
    assert zones.is_dress("dress") is True
    assert zones.is_dress("Dress") is True
    assert zones.is_dress("top") is False
    assert zones.is_dress(None) is False
    assert zones.is_dress("") is False


def test_default_category_for_zone():
    intent = Intent(colors=["黑色"])
    assert zones.default_category_for_zone("top", intent) == "上衣"
    assert zones.default_category_for_zone("bottom", intent) == "褲子"


def test_resolve_zone_for_item_type_dress_words():
    # 「洋裝」「連身裙」「連衣裙」都要被 engine02.taxonomy 的同義詞表判成連身裙——
    # 這是 /concept-image 分區判斷的關鍵，之前完全沒有這個判斷，連身裙一律
    # 被當成普通單品，見 docs 記錄的那個 bug。
    for word in ("洋裝", "連身裙", "連衣裙"):
        assert zones.resolve_zone_for_item_type(word) == ("top", True)


def test_resolve_zone_for_item_type_non_dress_words():
    assert zones.resolve_zone_for_item_type("白襯衫") == ("top", False)
    assert zones.resolve_zone_for_item_type("牛仔褲") == ("bottom", False)


def test_resolve_zone_for_item_type_unresolvable_or_empty():
    # 解析不出來、空字串、None 都保守回傳 ("top", False)，跟 zone_of() 對
    # 未知類別的防禦性預設一致，不會讓呼叫端出錯。
    assert zones.resolve_zone_for_item_type("完全亂打不存在的字") == ("top", False)
    assert zones.resolve_zone_for_item_type("") == ("top", False)
    assert zones.resolve_zone_for_item_type(None) == ("top", False)
