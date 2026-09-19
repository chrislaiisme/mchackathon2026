"""Assemble a complete outfit within one total budget.

The brief's own example is 「幫我準備一套正式場合的服裝，預算 3,000 元」: the budget is for the
WHOLE outfit, not for each garment. A per-item filter at 3,000 happily returns four items that cost
3,000 each, which is not what anyone meant, and 20% of the score is 「搭配是否完整可購買」.

The choice is one item per slot (top / bottom / outer / shoes ...), each from that slot's ranked
candidates, maximising total ranking score subject to Σ price ≤ budget. That is a multiple-choice
knapsack, and with a handful of slots and a handful of candidates each, exact dynamic programming
over a price grid is both fast and simple — no heuristic to explain away.

What this module refuses to do:
  * silently drop a slot to fit the budget — an incomplete outfit is reported as incomplete;
  * pretend an item with no price is free — unpriced items are excluded and counted;
  * return the cheapest outfit. The objective is the ranking score; the budget is a constraint.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence


@dataclass
class OutfitChoice:
    slot: str
    item_id: str
    title: str
    price: float
    score: float


@dataclass
class OutfitPlan:
    complete: bool
    items: list[OutfitChoice] = field(default_factory=list)
    total_price: float = 0.0
    budget: float | None = None
    missing_slots: list[str] = field(default_factory=list)
    unpriced_skipped: int = 0
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "complete": self.complete,
            "budget": self.budget,
            "total_price": round(self.total_price, 2),
            "remaining": (round(self.budget - self.total_price, 2)
                          if self.budget is not None else None),
            "items": [{"slot": c.slot, "item_id": c.item_id, "title": c.title,
                       "price": round(c.price, 2), "score": round(c.score, 4)} for c in self.items],
            "missing_slots": self.missing_slots,
            "unpriced_skipped": self.unpriced_skipped,
            "note": self.note,
        }


def plan_outfit(slots: dict[str, Sequence[tuple[str, str, float, float]]],
                budget: float | None, *, grid: float = 1.0) -> OutfitPlan:
    """Pick one candidate per slot to maximise total score subject to the total price.

    `slots` maps a slot name to candidates as (item_id, title, price, score). A candidate whose
    price is None or NaN is skipped and counted: an item we cannot price cannot be part of a claim
    that the outfit is purchasable.

    Exact multiple-choice knapsack by DP on a price grid (`grid` is the quantisation in currency
    units; 1.0 is exact for whole-currency prices).
    """
    import math

    usable: dict[str, list[tuple[str, str, float, float]]] = {}
    unpriced = 0
    for slot, cands in slots.items():
        keep = []
        for item_id, title, price, score in cands:
            if price is None or (isinstance(price, float) and math.isnan(price)) or price < 0:
                unpriced += 1
                continue
            keep.append((str(item_id), str(title), float(price), float(score)))
        if keep:
            usable[slot] = keep

    missing = [s for s in slots if s not in usable]

    if budget is None:
        # no budget: take the best-scoring candidate in every slot
        picks = [OutfitChoice(s, *max(c, key=lambda x: x[3])[:2],
                              price=max(c, key=lambda x: x[3])[2],
                              score=max(c, key=lambda x: x[3])[3])
                 for s, c in usable.items()]
        return OutfitPlan(complete=not missing, items=picks,
                          total_price=sum(p.price for p in picks), budget=None,
                          missing_slots=missing, unpriced_skipped=unpriced,
                          note="沒有給預算，每個部位各取分數最高的一件")

    cap = int(round(budget / grid))
    NEG = float("-inf")
    # dp[c] = best total score using the slots processed so far at cost exactly <= c
    dp = [0.0] + [NEG] * cap
    back: list[dict[int, tuple[str, int]]] = []
    order = list(usable)
    for slot in order:
        nxt = [NEG] * (cap + 1)
        chosen: dict[int, tuple[str, int]] = {}
        for c_prev in range(cap + 1):
            if dp[c_prev] == NEG:
                continue
            for item_id, _title, price, score in usable[slot]:
                c_new = c_prev + int(round(price / grid))
                if c_new > cap:
                    continue
                if dp[c_prev] + score > nxt[c_new]:
                    nxt[c_new] = dp[c_prev] + score
                    chosen[c_new] = (item_id, c_prev)
        dp = nxt
        back.append(chosen)

    best_cost = max((c for c in range(cap + 1) if dp[c] != NEG), key=lambda c: dp[c], default=None)
    if best_cost is None:
        cheapest = sum(min(c[2] for c in v) for v in usable.values())
        return OutfitPlan(complete=False, items=[], total_price=0.0, budget=budget,
                          missing_slots=list(usable) + missing, unpriced_skipped=unpriced,
                          note=(f"這個預算湊不出完整的一套：光是每個部位各取最便宜的一件就要 "
                                f"{cheapest:.0f}，超過 {budget:.0f}"))

    picks: list[OutfitChoice] = []
    cost = best_cost
    for slot, chosen in reversed(list(zip(order, back))):
        item_id, c_prev = chosen[cost]
        item = next(x for x in usable[slot] if x[0] == item_id)
        picks.append(OutfitChoice(slot, item[0], item[1], item[2], item[3]))
        cost = c_prev
    picks.reverse()

    total = sum(p.price for p in picks)
    return OutfitPlan(
        complete=not missing, items=picks, total_price=total, budget=budget,
        missing_slots=missing, unpriced_skipped=unpriced,
        note=(f"在 {budget:.0f} 的預算內湊出 {len(picks)} 件，合計 {total:.0f}"
              + (f"；{'、'.join(missing)} 這些部位沒有可用商品，所以這套並不完整"
                 if missing else "")),
    )
