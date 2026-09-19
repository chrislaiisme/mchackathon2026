"""生成單品概念圖：把 ENGINE 02 的回傳整理成生圖要的材料，交給 Hermes 執行。

分兩段，界線刻意畫清楚：

* **寫 prompt** 是政策，屬於 Hermes skill（`agent/skills/concept-image-director/`）。
* **執行生圖與存檔** 是流程，屬於這裡；不交給模型決定要不要做。

skill 還沒到位時用 `fallback_prompt()`，所以整條路今天就能跑，skill 完成後換掉那一個函式即可。

為什麼材料取自 ENGINE 02 而不是 ENGINE 01：`relaxed`（目錄給不出什麼）、
`unresolved_from_intent`（哪些話目錄詞彙表達不了）、`requirements`（哪些是使用者說出口的硬條件）
這三樣只有 ENGINE 02 知道，而它們正是生圖的主角。但使用者的原話一定要一起帶 ——
像「珍珠褲鏈」這種目錄沒有的概念會在 ENGINE 02 的結構化欄位裡整個消失。
"""
from __future__ import annotations

import os
import re
import shutil
import uuid
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

# 生成圖存這裡，由 BFF 的 /generated/<檔名> 提供給前端。
GENERATED_DIR = Path(os.environ.get("GENERATED_IMAGES_DIR", "data/generated"))
HERMES_REPO = Path(os.environ.get("HERMES_AGENT_REPO", Path.home() / ".hermes" / "hermes-agent"))


class SkillInput(BaseModel):
    """交給生圖 skill 的材料。`utterance` 放第一位是刻意的 —— 目錄詞彙表達不了的細節只存在於原話。"""

    utterance: str = ""
    hard: list[str] = Field(default_factory=list)          # 使用者說出口的硬條件，必須出現在圖上
    design: list[str] = Field(default_factory=list)        # 有方向性的設計偏好（例：寬鬆版型↑）
    relaxed: list[str] = Field(default_factory=list)       # 目錄給不出來而被放寬的條件 —— 生圖的主角
    unresolved: list[str] = Field(default_factory=list)    # 目錄詞彙對不到的說法
    reference_image: Optional[str] = None                  # 目錄商品的真實照片（本機路徑）
    reference_attributes: dict[str, str] = Field(default_factory=dict)


def build_skill_input(retrieval: dict[str, Any], utterance: str = "",
                      reference_item_id: Optional[str] = None) -> SkillInput:
    """從 ENGINE 02 的回傳挑出生圖要的材料。"""
    e02 = retrieval.get("engine02") or {}
    detail = e02.get("match_score_detail") or {}
    reqs = detail.get("requirements") or []

    products = retrieval.get("products") or []
    ref = None
    if reference_item_id:
        ref = next((p for p in products if str(p.get("product_id")) == str(reference_item_id)), None)
    ref = ref or (products[0] if products else None)

    return SkillInput(
        utterance=utterance,
        hard=[str(r.get("requirement")) for r in reqs if r.get("kind") == "hard"],
        design=[str(r.get("requirement")) for r in reqs if r.get("kind") == "design"],
        relaxed=[str(x) for x in (detail.get("relaxed") or [])],
        unresolved=[str(x) for x in (e02.get("unresolved_from_intent") or [])],
        reference_image=_catalog_image_path(ref.get("image_url")) if ref else None,
        reference_attributes={k: str(v) for k, v in ((ref or {}).get("attributes") or {}).items()},
    )


def _catalog_image_path(image_url: Optional[str]) -> Optional[str]:
    """ENGINE 02 的 `/images/<item_id>` 轉成本機檔案路徑；找不到就回 None（改成憑空生成）。"""
    if not image_url:
        return None
    item_id = str(image_url).rstrip("/").split("/")[-1]
    catalog = Path(os.environ.get("ENGINE02_CATALOG", "data/catalog/kagl")) / "images"
    for ext in (".jpg", ".jpeg", ".png"):
        candidate = catalog / f"{item_id}{ext}"
        if candidate.exists():
            return str(candidate)
    return None


# 平拍商品圖的視覺規則：要和目錄照片同一種語言，`/visual-search` 的 embedding 才比得準。
_FLAT_LAY_RULES = (
    "Flat product photograph on a plain white background, single garment filling the frame, "
    "no model, no mannequin, no props, no scene, no text, no logos, no watermark, "
    "even studio lighting, sharp focus, e-commerce catalog style."
)


def fallback_prompt(data: SkillInput) -> str:
    """skill 未就緒時的備用 prompt。刻意保守：只陳述材料，不自行發揮。"""
    parts: list[str] = []
    if data.utterance:
        parts.append(f"The shopper asked for: {data.utterance}")
    if data.relaxed:
        parts.append("The catalog could not supply this, so generate it: " + "；".join(data.relaxed))
    if data.hard:
        parts.append("These must be visible in the image: " + ", ".join(data.hard))
    if data.design:
        parts.append("Lean toward: " + ", ".join(data.design))
    if data.unresolved:
        parts.append("Details the catalog vocabulary could not express, keep them: " + "；".join(data.unresolved))
    if data.reference_image:
        parts.append("Use the provided reference image for the overall garment type and framing; "
                     "change only what the request above asks for.")
    parts.append(_FLAT_LAY_RULES)
    return "\n".join(parts)


def _dispatch_image_generate(prompt: str, reference_image: Optional[str]) -> dict[str, Any]:
    """經 Hermes 的工具註冊表生圖。流程決定何時生，不讓模型自己判斷。"""
    import sys

    if str(HERMES_REPO) not in sys.path:
        sys.path.insert(0, str(HERMES_REPO))
    # Hermes 的工具在模組被 import 時才把自己註冊進 registry，少了這行會是
    # 「Unknown tool: image_generate」。
    import tools.image_generation_tool  # noqa: F401
    from tools.registry import registry

    args: dict[str, Any] = {"prompt": prompt, "aspect_ratio": "square"}
    if reference_image:
        args["image_url"] = reference_image
    raw = registry.dispatch("image_generate", args)
    import json

    return json.loads(raw) if isinstance(raw, str) else raw


def generate(data: SkillInput, prompt: Optional[str] = None) -> dict[str, Any]:
    """產生一張平拍單品圖，回傳 `ConceptImage` 形狀的 dict；失敗回 `{"error": ...}`。

    `prompt` 給定時就用它（skill 寫好的），否則用 fallback。
    """
    used = prompt or fallback_prompt(data)
    try:
        result = _dispatch_image_generate(used, data.reference_image)
    except Exception as exc:  # 生圖不該讓整輪掛掉
        return {"error": f"{type(exc).__name__}: {exc}"[:300], "prompt_used": used}

    if not result.get("success"):
        return {"error": str(result.get("error"))[:300], "error_type": result.get("error_type"),
                "prompt_used": used}
    if result.get("image_source") != "final":
        return {"error": "只拿到進行中的半成品影格，沒有完整結果", "prompt_used": used}

    src = Path(result["image"])
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{re.sub(r'[^a-zA-Z0-9]+', '-', src.stem)[:40]}-{uuid.uuid4().hex[:8]}{src.suffix}"
    shutil.copy(src, GENERATED_DIR / name)

    return {
        "image_url": f"/generated/{name}",
        "prompt_used": used,
        # response_id 是 OpenAI Responses API 的多輪接續用的；Hermes 這條路不支援，恆為 None。
        "response_id": None,
        "reference_image_used": data.reference_image,
        "pixel_size": result.get("pixel_size"),
        "model": result.get("model"),
    }
