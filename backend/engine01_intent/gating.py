"""決定性的澄清問題把關——2026-09-19 新增。

背景：使用者要求「一定要把核心欄位都問到才傳給 ENGINE02，用選擇題，控制在 5 題以內」。
`prompts.py` 的 `INTENT_SYSTEM_PROMPT` 已經請 LLM 優先針對核心欄位出題、同一欄位不要
重複問，但這些終究只是「拜託」——LLM 每次呼叫都是獨立的，沒有任何機制強制它真的遵守
「總共不超過 5 題」這種跨輪次的全域限制。這支模組就是那個不依賴 LLM 自律的硬性把關：
不管 LLM 這輪吐出什麼 clarifying_questions，都要先經過 `filter_clarifying_questions()`
過濾，才能放進回傳給前端的 IntentResponse。
"""

from __future__ import annotations

from backend.shared.schemas import ClarifyingQuestion, Intent

# 核心欄位：缺了就優先問。item_type 有特殊處理，見 missing_core_fields()——
# outfit_requested=True（使用者要整套）時 item_type 不算缺。
# budget_min／budget_max／fit／pattern／collar 刻意不在這裡：使用者已經確認
# 這幾個不主動問，留空或讓 ENGINE02 當作沒有限制處理就好。
CORE_FIELDS: tuple[str, ...] = ("item_type", "colors", "occasion", "material", "season", "style_keywords")

# 使用者明確要求的總題數上限——是整個 session 累加的題數，不是每輪的題數。
MAX_CLARIFYING_QUESTIONS = 5


def missing_core_fields(intent: Intent) -> list[str]:
    """回傳目前 Intent 裡還沒填的核心欄位名稱清單。

    `item_type` 比較特別：使用者要的是「一整套」（outfit_requested=True）時，
    問「你想要哪個品項」沒有意義（套裝請求本來就不是在問單一品項），所以這種
    情況下 item_type 不算缺，即使它本身是 None。
    """
    missing: list[str] = []
    for name in CORE_FIELDS:
        if name == "item_type" and intent.outfit_requested:
            continue
        value = getattr(intent, name)
        # colors／style_keywords 是 list，空陣列視為「還沒填」；其餘是純量欄位，None 視為「還沒填」。
        if isinstance(value, list):
            if not value:
                missing.append(name)
        elif not value:
            missing.append(name)
    return missing


def filter_clarifying_questions(
    questions: list[ClarifyingQuestion], asked_core_fields: set[str]
) -> list[ClarifyingQuestion]:
    """把 LLM 這輪吐出來的 clarifying_questions 過濾成真正會送給前端的清單。

    三條規則：(1) 只保留欄位落在 CORE_FIELDS 的問題——非核心欄位的問題就算
    LLM 不小心生出來也一律濾掉；(2) 同一個核心欄位在這個 session 裡只問一次，
    `asked_core_fields` 已經問過的欄位直接跳過；(3) 全部題數（這次保留的 +
    這個 session 之前已經問過的）不能超過 MAX_CLARIFYING_QUESTIONS，超過的部分截斷。

    這個函式**有副作用**：對每一題真正保留下來的問題，會把它的 field 加進
    `asked_core_fields`（原地修改傳進來的 set），呼叫端要把這個 set 存回
    session 狀態，不然下一輪這個把關就失效了。
    """
    budget_left = MAX_CLARIFYING_QUESTIONS - len(asked_core_fields)
    if budget_left <= 0:
        return []

    kept: list[ClarifyingQuestion] = []
    for question in questions:
        if question.field not in CORE_FIELDS:
            continue
        if question.field in asked_core_fields:
            continue
        if len(kept) >= budget_left:
            break
        kept.append(question)
        asked_core_fields.add(question.field)

    return kept
