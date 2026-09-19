"""backend/engine01_intent/query_text.py 的單元測試。"""

from __future__ import annotations

from backend.engine01_intent.query_text import intent_to_query_text
from backend.shared.schemas import Intent


def test_empty_intent_gives_empty_string():
    assert intent_to_query_text(Intent()) == ""


def test_combines_populated_fields_in_order():
    intent = Intent(
        item_type="外套",
        colors=["黑色"],
        material="羊毛",
        style_keywords=["簡約", "剪裁俐落"],
        occasion="正式場合",
        season="秋冬",
    )
    assert intent_to_query_text(intent) == "外套 黑色 羊毛 簡約 剪裁俐落 正式場合 秋冬"


def test_never_returns_an_empty_string_worth_of_whitespace_only():
    # 只有 colors 這種 list 欄位有值的情況也要正常組出字串，不要留下多餘空白。
    intent = Intent(colors=["黑色", "白色"])
    assert intent_to_query_text(intent) == "黑色 白色"
