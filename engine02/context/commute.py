"""Commute -> ranking preferences (intuition v0, not yet measured). Taiwan edition.

  scooter 機車族  : 風切 + 雨淋 -> 防潑水、多一級保暖、避開長洋裝與飄逸寬版（會捲進輪子/被吹開）
  mrt     捷運族  : 車廂冷氣 vs 月台悶熱 -> 一件輕薄外套/針織開衫隨時穿脫
  walk    走路族  : 鞋子要好走 -> 鞋款與運動休閒風加分
  bike    Ubike族 : 要跨得上去 -> 褲裝、運動風，裙裝減分；下雨再加防潑水
  car     開車族  : 不怕風吹雨打 -> 放膽穿，大膽/結構感單品加分

Given a forecast (weather.DailyForecast), rain/cold/heat make the exposed modes stronger.
"""

from __future__ import annotations

from .base import MAX_SIGNAL_WEIGHT, AttributePref, ContextSignal, DailyForecast

EVIDENCE = "intuition v0 (not yet measured)"
EXPOSED = {"scooter", "bike", "walk"}


def _cap(w: float) -> float:
    return max(-MAX_SIGNAL_WEIGHT, min(MAX_SIGNAL_WEIGHT, w))


def _feels(fc: DailyForecast | None) -> float | None:
    if fc is None:
        return None
    lo = fc.apparent_min_c if fc.apparent_min_c is not None else fc.temp_min_c
    hi = fc.apparent_max_c if fc.apparent_max_c is not None else fc.temp_max_c
    vals = [v for v in (lo, hi) if v is not None]
    return sum(vals) / len(vals) if vals else None


def _resolve(ctx, today, forecast):
    if forecast is not None:
        return forecast
    if getattr(ctx, "lat", None) is None or getattr(ctx, "lon", None) is None:
        return None
    from . import weather
    day = getattr(ctx, "event_date", None) or (today.isoformat() if hasattr(today, "isoformat")
                                                else str(today))
    return weather.fetch_forecast(ctx.lat, ctx.lon, str(day)[:10], place=getattr(ctx, "city", None) or "")


def _sig(label, prefs, design=None, detail=None) -> ContextSignal:
    return ContextSignal(source="commute", label=label, prefs=prefs, design_steps=design or {},
                         affects_ranking=True, opt_in=False, evidence=EVIDENCE, detail=detail or {})


def signals(ctx, today, forecast: DailyForecast | None = None) -> list[ContextSignal]:
    mode = getattr(ctx, "commute", None)
    if not mode:
        return []
    fc = _resolve(ctx, today, forecast)
    rain = (fc.precip_prob_pct or 0.0) if fc is not None else 0.0
    rainy = fc is not None and (rain >= 60 or (fc.precip_mm or 0.0) >= 10)
    wind = (fc.wind_max_kmh or 0.0) if fc is not None else 0.0
    feels = _feels(fc)
    cold = feels is not None and feels <= 18
    hot = feels is not None and feels >= 30
    detail = {"commute": mode, "precip_prob_pct": rain if fc else None, "feels_like_c": feels,
              "wind_max_kmh": wind if fc else None}

    if mode == "scooter":
        wr = 0.4 if rainy else 0.2
        prefs = [AttributePref("water_repellent", _cap(wr), "機車族防潑水", values=[True]),
                 AttributePref("category", -0.25 if rainy else -0.2, "長洋裝騎車會捲、會被吹開",
                               values=["dress"]),
                 AttributePref("category", 0.2, "擋風外套", values=["outerwear"])]
        if cold or feels is None:
            # 時速 40 的風切 ≈ 體感再低好幾度：保暖往上加一級
            from .weather import warmth_target
            base = 2.0 if feels is None else float(min(3, warmth_target(feels) + 1))
            prefs.append(AttributePref("warmth", 0.25, "風切體感更冷，保暖 +1", target=base))
        if rainy:
            prefs.append(AttributePref("color", -0.15, "淺色被濺到很明顯",
                                       values=["White", "Off White", "Cream", "Beige"]))
        design = {"relaxed_fit": -1.0, "tailored_fit": 1.0}
        if rainy:
            label = f"騎車族 + 下雨 {rain:.0f}% → 防潑水 + 不怕風的版型，雨衣裡面也要好看"
        elif hot:
            prefs.append(AttributePref("warmth", 0.15, "薄薄一層就好", target=1.0))
            label = f"機車族 + 體感 {feels:.0f}°C → 薄防曬外套擋風擋太陽，長裙先收起來"
        elif wind >= 30:
            label = f"騎車族 + 陣風 {wind:.0f} km/h → 擋風外套、合身版型，不當風中飄逸哥/姐"
        else:
            label = "機車族出門 → 擋風外套 + 合身版型，長裙飄飄先收起來"
        return [_sig(label, prefs, design, detail)]

    if mode == "mrt":
        prefs = [AttributePref("category", 0.2, "冷氣車廂加一件", values=["outerwear"]),
                 AttributePref("warmth", 0.15, "輕薄好穿脫", target=1.0)]
        design = {"soft_knit": 1.0}
        label = "捷運族 → 車廂冷氣 vs 月台悶熱，帶件薄外套/針織衫隨穿隨脫"
        if hot:
            label = f"捷運族 + 室外體感 {feels:.0f}°C → 外面熱、車廂凍，薄針織外套是救星"
        if rainy:
            prefs.append(AttributePref("water_repellent", 0.15, "走到捷運站那段路", values=[True]))
        return [_sig(label, prefs, design, detail)]

    if mode == "walk":
        prefs = [AttributePref("category", 0.15, "好走的鞋最重要", values=["shoes"]),
                 AttributePref("style", 0.15, "走整天也舒服", values=["sporty", "minimalist", "streetwear"])]
        design = {"athletic_style": 1.0, "casual_style": 1.0}
        label = "走路族 → 好走的鞋 + 舒服休閒風，萬步也不腳痛"
        if rainy:
            prefs.append(AttributePref("water_repellent", 0.3, "邊走邊淋雨", values=[True]))
            label = f"走路族 + 降雨 {rain:.0f}% → 防潑水外套 + 不怕濕的鞋，水窪自己閃"
        elif hot:
            prefs.append(AttributePref("warmth", 0.2, "走路會流汗", target=0.0))
            label = f"走路族 + 體感 {feels:.0f}°C → 透氣輕薄，汗水不上身"
        return [_sig(label, prefs, design, detail)]

    if mode == "bike":
        prefs = [AttributePref("category", 0.2, "褲裝跨上車最自在", values=["bottom"]),
                 AttributePref("category", -0.2, "裙子踩踏板會走光", values=["dress"]),
                 AttributePref("style", 0.2, "運動休閒", values=["sporty", "streetwear"])]
        design = {"athletic_style": 1.0, "relaxed_fit": -1.0}
        label = "Ubike 族 → 褲裝 + 運動休閒，踩踏板不卡卡"
        if rainy:
            prefs.append(AttributePref("water_repellent", 0.4, "單車淋雨沒處躲", values=[True]))
            label = f"Ubike 族 + 降雨 {rain:.0f}% → 防潑水優先，褲裝好騎"
        elif cold:
            prefs.append(AttributePref("warmth", 0.2, "迎風更冷", target=2.0))
        return [_sig(label, prefs, design, detail)]

    if mode == "car":
        prefs = [AttributePref("boldness", 0.2, "開車不怕風雨，放膽穿", target=2.0),
                 AttributePref("style", 0.1, "有型出場", values=["classic", "edgy", "avant_garde", "romantic"])]
        design = {"structured_shoulders": 1.0, "bold_pattern": 1.0}
        return [_sig("開車族 → 風吹不到雨淋不到，今天可以大膽一點", prefs, design, detail)]

    return []
