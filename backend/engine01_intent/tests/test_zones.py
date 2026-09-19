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
