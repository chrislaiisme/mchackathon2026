"""Hard-constraint filtering with an explicit relaxation ladder.

Hard constraints are filters, not score terms (Taobao MGDSPR, KDD 2021; Vespa
constrained ANN). When the filter empties the candidate set we relax one step at a
time in a fixed order (cf. eBay null-query rewriting, WWW 2012) and report which step
was taken, so the explanation can say it instead of hiding it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .contracts import HardConstraints

SLOT_COLUMNS = ("category", "color", "occasion", "season", "gender")

# Each step is (slot, action). "allow_unknown" keeps the constraint but lets items with
# a missing attribute through; "drop" removes the constraint; "budget_x1.2" widens budget.
DEFAULT_LADDER: tuple[tuple[str, str], ...] = (
    ("color", "allow_unknown"),
    ("season", "allow_unknown"),
    ("occasion", "allow_unknown"),
    ("season", "drop"),
    ("occasion", "drop"),
    ("budget", "x1.2"),
    ("color", "drop"),
    ("budget", "drop"),
    # category and gender are never relaxed: a wrong category is not a recommendation
)


@dataclass
class FilterResult:
    mask: np.ndarray
    applied: dict[str, list[str]]
    relaxed: list[str] = field(default_factory=list)


def _norm(s) -> str | None:
    if s is None or (isinstance(s, float) and np.isnan(s)):
        return None
    return str(s).strip().lower()


def _slot_mask(col: pd.Series, values: list[str], allow_unknown: bool, also: pd.Series | None = None) -> np.ndarray:
    vals = {v.strip().lower() for v in values}
    norm = col.map(_norm)
    ok = norm.isin(vals).to_numpy(copy=True)
    if also is not None:  # category values may also name a subcategory ("blazer")
        ok |= also.map(_norm).isin(vals).to_numpy(copy=True)
    if allow_unknown:
        ok |= norm.isna().to_numpy(copy=True)
    return ok


def build_mask(
    items: pd.DataFrame,
    c: HardConstraints,
    state: dict[str, str],
    excluded_positions: list[int] | None = None,
) -> tuple[np.ndarray, dict[str, list[str]]]:
    n = len(items)
    mask = np.ones(n, dtype=bool)
    applied: dict[str, list[str]] = {}

    for slot_name in SLOT_COLUMNS:
        slot = getattr(c, slot_name)
        if not slot.is_hard() or not slot.values or state.get(slot_name) == "drop":
            continue
        also = items["subcategory"] if slot_name == "category" and "subcategory" in items else None
        mask &= _slot_mask(items[slot_name], slot.values, state.get(slot_name) == "allow_unknown", also)
        applied[slot_name] = list(slot.values)

    b = c.budget
    if b.is_hard() and (b.max_price is not None or b.min_price is not None) and state.get("budget") != "drop":
        price = pd.to_numeric(items["price"], errors="coerce").to_numpy(copy=True)
        factor = 1.2 if state.get("budget") == "x1.2" else 1.0
        ok = ~np.isnan(price)
        if b.max_price is not None:
            ok &= price <= b.max_price * factor
        if b.min_price is not None:
            ok &= price >= b.min_price
        mask &= ok
        applied["budget"] = [f"{b.min_price or 0}-{b.max_price}{'×1.2' if factor > 1 else ''}"]

    # exclusions from ENGINE 03 are always hard and never relaxed
    for attr, values in c.excluded_values.items():
        if attr not in items.columns or not values:
            continue
        vals = {v.lower() for v in values}
        mask &= ~items[attr].map(_norm).isin(vals).to_numpy(copy=True)
        applied[f"not_{attr}"] = list(values)

    if excluded_positions:
        mask[excluded_positions] = False
    return mask, applied


def filter_with_relaxation(
    items: pd.DataFrame,
    c: HardConstraints,
    min_results: int,
    excluded_positions: list[int] | None = None,
    ladder: tuple[tuple[str, str], ...] = DEFAULT_LADDER,
) -> FilterResult:
    state: dict[str, str] = {}
    mask, applied = build_mask(items, c, state, excluded_positions)
    relaxed: list[str] = []
    for slot, action in ladder:
        if mask.sum() >= min_results:
            break
        if slot not in applied or state.get(slot) == "drop":
            continue
        state[slot] = action
        mask, applied = build_mask(items, c, state, excluded_positions)
        relaxed.append(f"{slot}:{action}")
    return FilterResult(mask=mask, applied=applied, relaxed=relaxed)


def satisfies(items: pd.DataFrame, pos: int, c: HardConstraints) -> bool:
    """Rule-based check used by metrics (independent of the ranking score)."""
    row = items.iloc[[pos]]
    mask, _ = build_mask(row.reset_index(drop=True), c, state={})
    return bool(mask[0])
