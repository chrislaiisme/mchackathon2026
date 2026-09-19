"""把 Intent 組成一句話，給 ENGINE02 的 /visual-search 當 retrieval_text 用。

背景：ENGINE02 自己的研究文件（docs/research/visual-search-gaps.md 缺口 #1）
記錄了一個真的 bug——`retrieval_text` 是空字串時，查詢向量會變成「80% 一個
通用英文字 "clothing" ＋ 20% 上傳的照片」，等於大部分權重被雜訊吃掉。只要
一定帶一個有意義的 `retrieval_text`，就能繞開這個已知問題，不用等 ENGINE02
那邊修（見 engine02_client.py::visual_search() 的呼叫端）。
"""

from __future__ import annotations

from backend.shared.schemas import Intent


def intent_to_query_text(intent: Intent) -> str:
    """把 Intent 裡有值的欄位攤平成一句空白分隔的描述文字。

    刻意不做語法上通順的句子（例如「我想要一件黑色的外套」）——ENGINE02 這邊
    是拿去算 embedding，不是給人看的文案，關鍵字堆疊已經足夠承載語意，沒必要
    為了語感增加複雜度。欄位順序大致依「品項 → 屬性 → 情境」排，方便除錯時
    人眼快速掃過。
    """
    parts: list[str] = []
    if intent.item_type:
        parts.append(intent.item_type)
    parts.extend(intent.colors)
    if intent.material:
        parts.append(intent.material)
    if intent.pattern:
        parts.append(intent.pattern)
    if intent.fit:
        parts.append(intent.fit)
    if intent.collar:
        parts.append(intent.collar)
    parts.extend(intent.style_keywords)
    if intent.occasion:
        parts.append(intent.occasion)
    if intent.season:
        parts.append(intent.season)
    return " ".join(parts)
