"""backend/engine01_intent/gating.py 的單元測試。

涵蓋 missing_core_fields()（含 outfit_requested=True 時 item_type 不算缺）跟
filter_clarifying_questions()（非核心欄位被濾掉、同欄位不重複問、5 題預算截斷）。
"""

from __future__ import annotations

from backend.engine01_intent import gating
from backend.shared.schemas import ClarifyingOption, ClarifyingQuestion, Intent


def _question(field: str) -> ClarifyingQuestion:
    return ClarifyingQuestion(
        field=field,
        question=f"關於 {field} 的問題",
        options=[ClarifyingOption(id="a", label="A")],
    )


def test_missing_core_fields_on_blank_intent():
    intent = Intent()
    assert set(gating.missing_core_fields(intent)) == set(gating.CORE_FIELDS)


def test_missing_core_fields_ignores_item_type_when_outfit_requested():
    intent = Intent(outfit_requested=True, colors=["黑色"], occasion="正式場合", material="羊毛", season="秋冬", style_keywords=["簡約"])
    assert gating.missing_core_fields(intent) == []


def test_missing_core_fields_still_wants_item_type_for_single_item():
    intent = Intent(colors=["黑色"], occasion="正式場合", material="羊毛", season="秋冬", style_keywords=["簡約"])
    assert gating.missing_core_fields(intent) == ["item_type"]


def test_filter_drops_non_core_field_questions():
    questions = [_question("fit"), _question("budget_min")]
    kept = gating.filter_clarifying_questions(questions, set())
    assert kept == []


def test_filter_keeps_core_field_questions_and_records_them():
    asked: set[str] = set()
    kept = gating.filter_clarifying_questions([_question("colors"), _question("fit")], asked)
    assert [q.field for q in kept] == ["colors"]
    assert asked == {"colors"}


def test_filter_does_not_reask_a_field_already_asked():
    asked = {"colors"}
    kept = gating.filter_clarifying_questions([_question("colors"), _question("occasion")], asked)
    assert [q.field for q in kept] == ["occasion"]
    assert asked == {"colors", "occasion"}


def test_filter_truncates_at_five_question_budget():
    asked = {"item_type", "colors", "occasion", "material"}  # 4 已經問過
    kept = gating.filter_clarifying_questions([_question("season"), _question("style_keywords")], asked)
    # 只剩 1 個預算，兩題只能留下第一個
    assert [q.field for q in kept] == ["season"]
    assert asked == {"item_type", "colors", "occasion", "material", "season"}


def test_filter_returns_nothing_once_budget_exhausted():
    asked = {"item_type", "colors", "occasion", "material", "season"}  # 已經 5 題
    kept = gating.filter_clarifying_questions([_question("style_keywords")], asked)
    assert kept == []
