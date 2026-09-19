"""Reasons from the score decomposition; the LLM may only re-word verified facts.

- Grounded ≠ faithful (Maes et al., IUI-W 2025): the reason must be a term that actually
  decides the rank, so only terms selected by the reason mode (counterfactual necessity,
  contrastive margin or minimal sufficient set; see rerank.py) are cited.
- The LLM paraphrase is checked in code: every label or number it mentions must be in
  the facts it was given, otherwise we fall back to the template sentence.
"""

from __future__ import annotations

import json
import re
from typing import Callable

from .contracts import Contribution

GROUP_LABEL = {
    "dense": "整體風格和你描述的相近",
    "bm25": "商品描述直接提到你要的關鍵字",
    "compat": "和你指定的單品搭配度高",
    "trend": "符合近期趨勢關鍵字",
    "rerank": "重排模型判定和需求高度相關",
    "penalty": "和你否決過的商品不同",
    "freshness": "這件你這輪還沒看過",
    "context": "符合你現在的情境",
}


def _context_label(term: str) -> str:
    """The situation behind a context term ("明天新竹體感 14°C → 防潑水外套"), for this request."""
    try:
        from .context.engine import CONTEXT_LABELS
        return CONTEXT_LABELS.get().get(term) or GROUP_LABEL["context"]
    except Exception:                        # noqa: BLE001
        return GROUP_LABEL["context"]


def template_reasons(
    contribs: list[Contribution],
    element_labels: dict[str, str],
    need_labels: dict[str, str],
    relaxed: list[str],
) -> tuple[list[str], list[dict]]:
    # the pipeline has already decided (and capped) which terms are displayed
    need_labels = {**need_labels, "feedback_adjust": "你上一輪的回饋",
                   "external_prior": "外部趨勢／企劃偏好（非你本人的輸入）",
                   "profile_prior": "你開場挑的偏好",
                   "stated_design": "你這句話裡說的"}
    cited = [c for c in contribs if c.cited and c.contribution > 0]
    cited.sort(key=lambda c: -c.contribution)
    # context can stack five situations on one card; the two strongest carry the story, the rest
    # are still in `contributions` (and still sum into the score) for anyone who opens the detail
    ctx_seen = 0
    kept = []
    for c in cited:
        if c.group == "context":
            ctx_seen += 1
            if ctx_seen > 2:
                continue
        kept.append(c)
    cited = kept
    reasons, facts = [], []
    for c in cited:
        if c.group == "design":
            d = c.term.split(":", 1)[1]
            label = element_labels.get(d, d)
            top_needs = sorted(c.need_shares.items(), key=lambda kv: -kv[1])[:2]
            serves = "、".join(need_labels.get(n, n) for n, v in top_needs if v > 0)
            # a positive contribution comes either from "has d and d is wanted" or from
            # "lacks d and d is unwanted" — the sentence must say which
            avoids = c.weight < 0
            phrase = f"避開{label}" if avoids else label
            # the meta-sources are not needs, so "對應你想要的「你這句話裡說的」" reads as nonsense;
            # they are provenance and the sentence should say where the weight came from
            sources = [n for n, v in top_needs
                       if v > 0 and n in ("stated_design", "feedback_adjust", "profile_prior",
                                          "external_prior")]
            needs_only = "、".join(need_labels.get(n, n) for n, v in top_needs
                                   if v > 0 and n not in sources)
            tail = ""
            if needs_only:
                tail = f"，對應你想要的「{needs_only}」"
            elif sources:
                tail = f"（{need_labels.get(sources[0], sources[0])}）"
            text = f"{phrase}（+{c.contribution:.2f}）" + tail
            facts.append({"type": "design", "label": label, "direction": "avoids" if avoids else "has",
                          "contribution": round(c.contribution, 2),
                          "serves_needs": [need_labels.get(n, n) for n, v in top_needs if v > 0]})
        elif c.group == "context":
            label = _context_label(c.term)
            text = f"{label}（+{c.contribution:.2f}）"
            facts.append({"type": "context", "label": label, "source": c.term.split(":")[1],
                          "contribution": round(c.contribution, 2)})
        else:
            text = f"{GROUP_LABEL.get(c.group, c.term)}（+{c.contribution:.2f}）"
            facts.append({"type": c.group, "label": GROUP_LABEL.get(c.group, c.term),
                          "contribution": round(c.contribution, 2)})
        reasons.append(text)
    for r in relaxed:
        slot = r.split(":")[0]
        reasons.append(f"注意：為了有足夠結果，放寬了「{slot}」條件（{r}）")
        facts.append({"type": "relaxed", "label": slot, "detail": r})
    return reasons, facts


_NUM = re.compile(r"\d+(?:\.\d+)?")


def verify_paraphrase(text: str, facts: list[dict], vocabulary: list[str]) -> bool:
    """Reject text that cites a number or a known label absent from the facts."""
    allowed_nums = set()
    allowed_labels = set()
    for f in facts:
        for k, v in f.items():
            if isinstance(v, (int, float)):
                allowed_nums.add(f"{v}")
                allowed_nums.add(f"{abs(v):.2f}")
            if isinstance(v, str):
                allowed_labels.add(v)
            if isinstance(v, list):
                allowed_labels.update(x for x in v if isinstance(x, str))
    for num in _NUM.findall(text):
        if num not in allowed_nums and f"{float(num):.2f}" not in allowed_nums:
            return False
    for label in vocabulary:
        if label and label in text and not any(label in a for a in allowed_labels):
            return False
    return True


class LlmBudget:
    """Caps what one request can spend on paraphrases, and gives up after the first failure.

    `explain()` falls back to the template whenever the callable raises, so exhausting the budget
    is expressed as an exception. Without this, a slow or dead endpoint costs (cards x timeout).
    """

    def __init__(self, llm: Callable[[str], str], total_s: float = 1.5):
        self.llm, self.total_s = llm, total_s
        self.spent = 0.0
        self.failed = False

    def __call__(self, prompt: str) -> str:
        import time

        if self.failed or self.spent >= self.total_s:
            raise TimeoutError(f"paraphrase budget of {self.total_s}s used up ({self.spent:.2f}s)")
        t = time.perf_counter()
        try:
            return self.llm(prompt)
        except Exception:
            self.failed = True  # one failure is enough: the rest of the cards use templates
            raise
        finally:
            self.spent += time.perf_counter() - t


PARAPHRASE_PROMPT = (
    "你是服飾推薦系統的說明撰寫器。只能使用下面 JSON 裡的事實，把它寫成一句自然、"
    "不超過 60 字的繁體中文推薦理由。不得加入 JSON 沒有的屬性、需求、數字或形容。\n"
    "JSON：{facts}"
)


def explain(
    reasons: list[str],
    facts: list[dict],
    vocabulary: list[str],
    llm: Callable[[str], str] | None,
) -> tuple[str, str]:
    template = "；".join(reasons) if reasons else "符合你設定的條件"
    if llm is None or not facts:
        return template, "template"
    try:
        text = llm(PARAPHRASE_PROMPT.format(facts=json.dumps(facts, ensure_ascii=False))).strip()
    except Exception:
        return template, "template"
    if text and verify_paraphrase(text, facts, vocabulary):
        return text, "llm"
    return template, "template"
