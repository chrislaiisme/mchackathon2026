"""旅行打包膠囊衣櫥 (travel capsule wardrobe).

Pick a handful of garments that multiply into as many distinct outfits as possible for the trip:

  outfits = compatible (top × bottom × shoes) + compatible (dress × shoes)

Colour rule: neutrals (Black / White / Grey / Navy Blue / Beige and their close shades) go with
everything; an outfit may contain at most ONE non-neutral colour. An item with no colour is treated
as neutral (we cannot judge it, so we do not punish it) -- and the notes say so.

Weather: the trip's forecast range sets a warmth band (catalog column `warmth`, 0..3, if present);
items far outside the band are dropped. A rainy day forces one `water_repellent` outerwear if the
catalog has one; a cold day asks for an outer layer.

Budget: the core (one of each needed slot) is chosen with the exact multiple-choice knapsack in
engine02.outfit_budget.plan_outfit; extra pieces are then added greedily by outfit gain, followed by
a small swap local search. Unpriced items are skipped whenever a budget is set (never assumed free).
"""

from __future__ import annotations

import math
from itertools import product
from typing import Any

import pandas as pd

from ..context.base import DailyForecast
from ..outfit_budget import plan_outfit

NEUTRALS = {
    "black", "white", "off white", "cream", "grey", "gray", "charcoal", "grey melange", "silver",
    "navy blue", "navy", "beige", "khaki", "nude", "skin", "taupe",
}

CATEGORY_ALIASES = {
    "top": "top", "tops": "top", "topwear": "top", "shirt": "top", "shirts": "top", "tshirts": "top",
    "t-shirt": "top", "blouse": "top", "tee": "top", "上衣": "top",
    "bottom": "bottom", "bottoms": "bottom", "bottomwear": "bottom", "pants": "bottom",
    "trousers": "bottom", "jeans": "bottom", "skirt": "bottom", "shorts": "bottom", "褲子": "bottom",
    "dress": "dress", "dresses": "dress", "洋裝": "dress",
    "outerwear": "outerwear", "outer": "outerwear", "jacket": "outerwear", "coat": "outerwear",
    "外套": "outerwear",
    "shoes": "shoes", "shoe": "shoes", "footwear": "shoes", "鞋": "shoes", "鞋子": "shoes",
}
SLOT_ZH = {"top": "上衣", "bottom": "下身", "dress": "洋裝", "outerwear": "外套", "shoes": "鞋子"}

RAIN_PROB = 50.0
COLD_C = 18.0
MAX_POOL_PER_SLOT = 12


# --------------------------------------------------------------------------- small helpers

def _isnan(v) -> bool:
    return v is None or v is pd.NA or (isinstance(v, float) and math.isnan(v))


def _slot(row) -> str | None:
    for col in ("category", "subcategory"):
        v = row.get(col)
        if not _isnan(v):
            s = CATEGORY_ALIASES.get(str(v).strip().lower())
            if s:
                return s
    return None


def _is_neutral(color) -> bool:
    return _isnan(color) or str(color).strip().lower() in NEUTRALS


def _compatible(colors: list) -> bool:
    return sum(0 if _is_neutral(c) else 1 for c in colors) <= 1


def _warmth_for_temp(t: float) -> int:
    if t >= 26:
        return 0
    if t >= 20:
        return 1
    if t >= 13:
        return 2
    return 3


def _day_temp(f: DailyForecast) -> tuple[float | None, float | None]:
    lo = f.apparent_min_c if f.apparent_min_c is not None else f.temp_min_c
    hi = f.apparent_max_c if f.apparent_max_c is not None else f.temp_max_c
    return lo, hi


def _is_rainy(f: DailyForecast) -> bool:
    return ((f.precip_prob_pct or 0) >= RAIN_PROB) or ((f.precip_mm or 0) >= 1.0)


def _is_cold(f: DailyForecast) -> bool:
    lo, _ = _day_temp(f)
    return lo is not None and lo < COLD_C


# --------------------------------------------------------------------------- outfit counting

def _outfits(chosen: list[str], info: dict[str, dict]) -> list[list[str]]:
    by = {"top": [], "bottom": [], "dress": [], "shoes": []}
    for i in chosen:
        s = info[i]["slot"]
        if s in by:
            by[s].append(i)
    out: list[list[str]] = []
    for t, b, s in product(by["top"], by["bottom"], by["shoes"]):
        if _compatible([info[t]["color"], info[b]["color"], info[s]["color"]]):
            out.append([t, b, s])
    for d, s in product(by["dress"], by["shoes"]):
        if _compatible([info[d]["color"], info[s]["color"]]):
            out.append([d, s])
    return out


def _objective(chosen: list[str], info: dict[str, dict]) -> tuple[int, float, float]:
    n = len(_outfits(chosen, info))
    score = sum(info[i]["score"] for i in chosen)
    cost = sum(info[i]["price"] or 0.0 for i in chosen)
    return (n, round(score, 6), -cost)


def _cost(chosen: list[str], info: dict[str, dict]) -> float:
    return sum(info[i]["price"] or 0.0 for i in chosen)


# --------------------------------------------------------------------------- main entry

def plan_capsule(items: pd.DataFrame, forecasts: list[DailyForecast], n_items: int = 8,
                 budget: float | None = None,
                 scores: dict[str, float] | None = None) -> dict[str, Any]:
    """Pack a capsule of at most `n_items` garments that yields the most distinct outfits."""
    scores = scores or {}
    forecasts = list(forecasts or [])
    notes: list[str] = []

    # ---- trip weather summary
    los = [t for t in (_day_temp(f)[0] for f in forecasts) if t is not None]
    his = [t for t in (_day_temp(f)[1] for f in forecasts) if t is not None]
    rainy = any(_is_rainy(f) for f in forecasts)
    cold = any(_is_cold(f) for f in forecasts)
    has_warmth = "warmth" in items.columns
    band = None
    if has_warmth and (los or his):
        w_hot = _warmth_for_temp(max(his or los))
        w_cold = _warmth_for_temp(min(los or his))
        band = (min(w_hot, w_cold), max(w_hot, w_cold))

    # ---- candidate pool
    has_price = "price" in items.columns
    has_wr = "water_repellent" in items.columns
    info: dict[str, dict] = {}
    unpriced = 0
    too_far = 0
    for _, row in items.iterrows():
        row = row.to_dict()
        slot = _slot(row)
        if slot is None:
            continue
        iid = str(row.get("item_id"))
        # budgets are in NT$: use the comparable price when the catalog has one (crawl_tw lists
        # some items in USD)
        price = row.get("price_twd") if "price_twd" in row else (row.get("price") if has_price else None)
        price = None if _isnan(price) else float(price)
        if budget is not None and price is None:
            unpriced += 1
            continue
        score = float(scores.get(iid, scores.get(row.get("item_id"), 0.0)) or 0.0)
        warmth = row.get("warmth") if has_warmth else None
        warmth = None if _isnan(warmth) else int(warmth)
        if band is not None and warmth is not None:
            lo_w, hi_w = band
            # outer layers may run one step warmer (they come off indoors)
            hi_ok = hi_w + (1 if slot == "outerwear" else 0)
            dist = max(lo_w - warmth, warmth - hi_ok, 0)
            if dist > 1:
                too_far += 1
                continue
            score -= 0.3 * dist
        if _is_neutral(row.get("color")):
            score += 0.05  # neutrals multiply outfits; a tiny nudge in their favour
        wr = bool(row.get("water_repellent")) if has_wr and not _isnan(row.get("water_repellent")) else False
        info[iid] = {"slot": slot, "color": None if _isnan(row.get("color")) else row.get("color"),
                     "price": price, "score": score, "warmth": warmth, "water_repellent": wr,
                     "price_estimated": bool(row.get("price_estimated")) if not _isnan(row.get("price_estimated")) else False,
                     "title": str(row.get("title") or iid)}

    # keep the best few per slot so the search stays instant
    pool: dict[str, list[str]] = {}
    for iid, d in info.items():
        pool.setdefault(d["slot"], []).append(iid)
    for s in pool:
        pool[s].sort(key=lambda i: -info[i]["score"])
        pool[s] = pool[s][:MAX_POOL_PER_SLOT]
    candidates = [i for ids in pool.values() for i in ids]

    if budget is not None and unpriced:
        notes.append(f"有預算時不猜價格：{unpriced} 件沒有標價的商品先跳過了")
    if too_far:
        notes.append(f"依這趟的氣溫，{too_far} 件太厚或太薄的衣服沒放進候選")

    # ---- which outer does the trip need?
    outer_pool = pool.get("outerwear", [])
    need_outer = rainy or cold
    rain_outers = [i for i in outer_pool if info[i]["water_repellent"]]
    if rainy and not rain_outers:
        notes.append("有雨天，但商品庫裡找不到標示防潑水的外套，記得自備雨具 ☔")
    outer_choices = rain_outers if (rainy and rain_outers) else outer_pool

    # ---- core: exact knapsack over (top, bottom, shoes [, outer]) or (dress, shoes [, outer])
    def core_for(slots: list[str]) -> list[str] | None:
        cand = {}
        for s in slots:
            ids = outer_choices if s == "outerwear" else pool.get(s, [])
            if not ids:
                return None
            cand[s] = [(i, info[i]["title"], info[i]["price"], info[i]["score"]) for i in ids]
        if budget is None:
            return [max(cand[s], key=lambda x: x[3])[0] for s in slots]
        plan = plan_outfit(cand, budget)
        return [c.item_id for c in plan.items] if plan.complete and plan.items else None

    core = None
    for base in (["top", "bottom", "shoes"], ["dress", "shoes"]):
        slots = base + (["outerwear"] if need_outer and outer_choices else [])
        core = core_for(slots)
        if core is None and need_outer:
            core = core_for(base)
            if core is not None:
                notes.append("預算不夠再帶一件外套，先把基本款湊齊")
        if core is not None:
            break

    empty = {"items": [], "outfits": [], "n_outfits": 0, "per_day_plan": [],
             "total_price": 0.0, "budget": budget}
    if core is None:
        notes.append("湊不出一套完整穿搭（上衣＋下身＋鞋，或洋裝＋鞋）"
                     + ("，預算可能太緊" if budget is not None else "，商品庫缺少某個部位"))
        return {**empty, "notes_zh": notes}

    if len(core) > n_items:
        core = [i for i in core if info[i]["slot"] != "outerwear"][:n_items]
        notes.append(f"只能帶 {n_items} 件，外套只好割捨")
    protected = {i for i in core if info[i]["slot"] == "outerwear"}
    chosen = list(core)

    # ---- greedy growth by outfit gain
    def within_budget(sel: list[str]) -> bool:
        return budget is None or _cost(sel, info) <= budget + 1e-9

    while len(chosen) < n_items:
        cur = _objective(chosen, info)
        best, best_obj = None, cur
        for i in candidates:
            if i in chosen or info[i]["slot"] == "outerwear":
                continue
            trial = chosen + [i]
            if not within_budget(trial):
                continue
            obj = _objective(trial, info)
            if obj[0] > cur[0] and obj > best_obj:
                best, best_obj = i, obj
        if best is None:
            break
        chosen.append(best)

    # ---- local search: 1-for-1 swaps that add outfits (or score at equal outfits)
    for _ in range(3):
        improved = False
        for out_i in list(chosen):
            if out_i in protected:
                continue
            for in_i in candidates:
                if in_i in chosen or info[in_i]["slot"] == "outerwear":
                    continue
                trial = [in_i if x == out_i else x for x in chosen]
                if not within_budget(trial):
                    continue
                if _objective(trial, info)[:2] > _objective(chosen, info)[:2]:
                    chosen, improved = trial, True
                    break
        if not improved:
            break

    outfits = _outfits(chosen, info)
    n_out = len(outfits)
    outer_id = next((i for i in chosen if info[i]["slot"] == "outerwear"), None)

    # ---- per-day plan: never repeat an outfit while there are unused ones
    per_day = []
    used: list[int] = []
    for f in forecasts:
        lo, hi = _day_temp(f)
        mean_t = (lo + hi) / 2 if lo is not None and hi is not None else (lo if lo is not None else hi)
        target_w = _warmth_for_temp(mean_t) if mean_t is not None else None

        def fit(k: int) -> tuple:
            ws = [info[i]["warmth"] for i in outfits[k] if info[i]["warmth"] is not None]
            wdist = abs(sum(ws) / len(ws) - target_w) if ws and target_w is not None else 0
            return (k in used, used.count(k), wdist, -sum(info[i]["score"] for i in outfits[k]))

        if not outfits:
            break
        k = min(range(n_out), key=fit)
        used.append(k)
        look = list(outfits[k])
        why = []
        if mean_t is not None:
            why.append(f"{f.place} 約 {lo:.0f}–{hi:.0f}°C" if lo is not None and hi is not None
                       else f"{f.place} 約 {mean_t:.0f}°C")
        if outer_id and (_is_rainy(f) or _is_cold(f)):
            look.append(outer_id)
            if _is_rainy(f) and info[outer_id]["water_repellent"]:
                why.append(f"降雨機率 {f.precip_prob_pct or 0:.0f}%，披上防潑水外套不怕淋濕")
            elif _is_rainy(f):
                why.append("會下雨，外套先穿上、傘也別忘了")
            else:
                why.append("早晚偏涼，加件外套剛好")
        elif _is_rainy(f):
            why.append("會下雨，記得帶傘")
        if used.count(k) == 1:
            why.append("這套還沒穿過，拍照不撞衫 📸")
        else:
            why.append("穿搭用完一輪，挑最適合這天天氣的再穿一次")
        per_day.append({"date": f.date, "outfit": look, "why_zh": "；".join(why)})

    # ---- lively summary
    total = _cost(chosen, info) if (has_price and all(info[i]["price"] is not None for i in chosen)) else None
    days = len(forecasts)
    headline = f"{len(chosen)} 件衣服 → {n_out} 套穿搭"
    if days:
        headline += (f"，{days} 天都不重複" if n_out >= days else f"，{days} 天裡會有幾套重複登場")
    notes.insert(0, headline + " ✨")
    counts = {}
    for i in chosen:
        counts[info[i]["slot"]] = counts.get(info[i]["slot"], 0) + 1
    notes.insert(1, "打包清單：" + "、".join(f"{SLOT_ZH[s]} {n} 件" for s, n in counts.items()))
    if rainy and outer_id and info[outer_id]["water_repellent"]:
        notes.append("行程中有雨天，已放進一件防潑水外套 🌧️")
    n_est = sum(1 for i in chosen if info[i]["price_estimated"])
    if budget is not None and total is not None:
        notes.append(f"合計 {total:.0f} 元，預算 {budget:.0f} 元內還剩 {budget - total:.0f} 元"
                     + (f"（其中 {n_est} 件是估計價，非實際標價）" if n_est else ""))
    elif total is not None and n_est:
        notes.append(f"合計約 {total:.0f} 元（其中 {n_est} 件是估計價，非實際標價）")
    if any(info[i]["color"] is None for i in chosen):
        notes.append("有幾件沒有顏色資料，先當作百搭色計算")
    nn = sum(1 for i in chosen if not _is_neutral(info[i]["color"]))
    if nn:
        notes.append(f"用中性色打底，只留 {nn} 件亮色當重點，怎麼配都不打架")

    return {
        "items": [{"item_id": i, "slot": info[i]["slot"], "title": info[i]["title"],
                   "color": info[i]["color"], "price": info[i]["price"],
                   "price_estimated": info[i]["price_estimated"]} for i in chosen],
        "outfits": outfits,
        "n_outfits": n_out,
        "per_day_plan": per_day,
        "total_price": total,
        "budget": budget,
        "notes_zh": notes,
    }
