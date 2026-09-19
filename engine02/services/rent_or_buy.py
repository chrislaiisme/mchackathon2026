"""租還是買 (rent-or-buy advisor).

Rule of thumb, stated plainly on the card:
  * a bold piece (boldness >= 2) or a one-off formal occasion (婚禮 / 尾牙 / 畢業典禮 ...) worn at
    most twice -> rent;
  * a staple -> buy, and show cost-per-wear when the item HAS a price (price / times_expected);
  * otherwise -> either.

Never invents a price: no price in the item -> cost_per_wear is None and the text says so.
"""

from __future__ import annotations

import math
from typing import Any

ONE_OFF_OCCASIONS = ("婚禮", "喜宴", "喜酒", "尾牙", "春酒", "畢業典禮", "謝師宴", "舞會", "晚宴",
                     "頒獎", "wedding", "prom", "gala", "graduation", "black tie", "banquet")
BOLD_MIN = 2
STAPLE_CATEGORIES = ("top", "bottom", "shoes", "tshirts", "shirts", "jeans", "trousers")


def _num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or f < 0 else f


def advise(item: dict, occasion: str | None = None, times_expected: int | None = None) -> dict[str, Any]:
    """Rent, buy or either -- with cost-per-wear only when a real price exists."""
    item = item or {}
    title = str(item.get("title") or "這件")
    price = _num(item.get("price"))
    boldness = _num(item.get("boldness"))
    occ_text = " ".join(str(x) for x in (occasion, item.get("occasion")) if x).lower()
    one_off = any(k in occ_text for k in ONE_OFF_OCCASIONS)
    bold = boldness is not None and boldness >= BOLD_MIN
    times = int(times_expected) if times_expected is not None and times_expected > 0 else None

    cpw = round(price / times, 1) if (price is not None and times) else None
    price_txt = (f"標價 {price:.0f} 元" if price is not None else "這件沒有標價，我們不猜價格")
    cpw_txt = (f"，穿 {times} 次平均每次 {cpw:.0f} 元" if cpw is not None
               else ("，無法計算每次穿著成本" if price is None and times else ""))

    rare = times is not None and times <= 2
    if (bold or one_off) and (rare or (times is None and one_off)):
        why = []
        if bold:
            why.append("這件驚艷但一年穿一次")
        if one_off:
            why.append("這種場合一年難得幾回")
        return {"advice": "rent", "cost_per_wear": cpw, "one_off": one_off, "bold": bold,
                "explanation_zh": f"{title}：{'、'.join(why)}，租比較划算 ✨（{price_txt}{cpw_txt}）"
                                  + "；租來的還能每場換新造型，衣櫃也不會爆"}

    staple = not bold and not one_off
    if staple:
        if cpw is not None:
            verdict = ("每次不到 100 元，天天穿超值，直接買" if cpw < 100
                       else "常穿的基本款，買了會一直用到")
            return {"advice": "buy", "cost_per_wear": cpw, "one_off": False, "bold": False,
                    "explanation_zh": f"{title}：{price_txt}{cpw_txt}，{verdict} 👍"}
        return {"advice": "buy", "cost_per_wear": None, "one_off": False, "bold": False,
                "explanation_zh": f"{title}：百搭基本款，會穿很多次，建議買（{price_txt}{cpw_txt}）"}

    return {"advice": "either", "cost_per_wear": cpw, "one_off": one_off, "bold": bold,
            "explanation_zh": f"{title}：有特色但你打算穿 {times or '不少'} 次，租或買都合理"
                              f"（{price_txt}{cpw_txt}）；確定會常穿就買，只是想試試就先租"}
