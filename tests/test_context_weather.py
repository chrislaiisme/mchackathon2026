"""Offline tests for engine02/context/weather.py and commute.py (network is monkeypatched out)."""

from datetime import date

import pandas as pd
import pytest

from engine02.context import commute, weather
from engine02.context.base import MAX_SIGNAL_WEIGHT, DailyForecast
from engine02.contracts import ContextInput

TODAY = date(2026, 9, 19)
REAL_FETCH = weather.fetch_forecast     # captured before the autouse stub


def fc(**kw):
    base = dict(date="2026-09-20", place="新竹", lat=24.8, lon=120.97, temp_max_c=26, temp_min_c=22,
                apparent_max_c=26, apparent_min_c=22, precip_prob_pct=10, precip_mm=0,
                wind_max_kmh=10, uv_index_max=3)
    base.update(kw)
    return DailyForecast(**base)


def prefs_of(sigs, column):
    return [p for s in sigs for p in s.prefs if p.column == column]


def all_weights_ok(sigs):
    for s in sigs:
        assert s.affects_ranking is True
        for p in s.prefs:
            assert abs(p.weight) <= MAX_SIGNAL_WEIGHT


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network must not be touched in tests")
    monkeypatch.setattr(weather, "fetch_forecast", boom)


@pytest.mark.parametrize("feels,target", [(8, 3), (12, 3), (15, 2), (18, 2), (22, 1), (25, 1), (30, 0)])
def test_warmth_target_mapping(feels, target):
    assert weather.warmth_target(feels) == target
    sigs = weather.signals(ContextInput(), TODAY, fc(apparent_max_c=feels, apparent_min_c=feels,
                                                     temp_max_c=feels, temp_min_c=feels))
    w = [p for p in prefs_of(sigs, "warmth") if p.weight == 0.3]
    assert w and w[0].target == target
    assert "體感" in sigs[0].label and sigs[0].evidence.startswith("intuition v0")
    all_weights_ok(sigs)


def test_rain_prefers_water_repellent_and_disfavours_light_colours():
    sigs = weather.signals(ContextInput(), TODAY, fc(precip_prob_pct=70, precip_mm=8))
    wr = prefs_of(sigs, "water_repellent")
    assert wr and wr[0].weight > 0 and wr[0].values == [True]
    col = [p for p in prefs_of(sigs, "color") if p.weight < 0]
    assert col and "White" in col[0].values
    assert any(p.values == ["outerwear"] and p.weight > 0 for p in prefs_of(sigs, "category"))
    assert any("降雨 70%" in s.label and "明天新竹" in s.label for s in sigs)
    all_weights_ok(sigs)


def test_dry_day_has_no_rain_signal():
    sigs = weather.signals(ContextInput(), TODAY, fc())
    assert not prefs_of(sigs, "water_repellent")


def test_wind_uv_swing_and_muggy():
    sigs = weather.signals(ContextInput(), TODAY,
                           fc(wind_max_kmh=45, uv_index_max=11, temp_max_c=34, temp_min_c=24,
                              apparent_max_c=38, apparent_min_c=30))
    labels = " ".join(s.label for s in sigs)
    assert "陣風" in labels and "紫外線" in labels and "洋蔥式" in labels and "悶熱" in labels
    wind = next(s for s in sigs if "陣風" in s.label)
    assert wind.design_steps["relaxed_fit"] < 0 and wind.design_steps["tailored_fit"] > 0
    all_weights_ok(sigs)


def test_signals_without_forecast_or_coords_is_empty():
    assert weather.signals(ContextInput(), TODAY) == []


def test_signals_fetches_when_coords_given(monkeypatch):
    seen = {}

    def fake(lat, lon, date_iso, place="", timeout=3.0):
        seen.update(lat=lat, lon=lon, date=date_iso, place=place)
        return fc(date=date_iso, place=place, precip_prob_pct=90)
    monkeypatch.setattr(weather, "fetch_forecast", fake)
    ctx = ContextInput(city="新竹", lat=24.8, lon=120.97, event_date="2026-09-21")
    sigs = weather.signals(ctx, TODAY)
    assert seen["date"] == "2026-09-21" and seen["place"] == "新竹"
    assert any("大雨" in s.label for s in sigs)


def test_commute_scooter_rain_stronger_than_dry():
    ctx = ContextInput(commute="scooter")
    dry = commute.signals(ctx, TODAY, fc())
    wet = commute.signals(ctx, TODAY, fc(precip_prob_pct=85))
    w_dry = prefs_of(dry, "water_repellent")[0].weight
    w_wet = prefs_of(wet, "water_repellent")[0].weight
    assert w_wet > w_dry > 0
    assert "騎車族 + 下雨" in wet[0].label
    assert any(p.values == ["dress"] and p.weight < 0 for p in prefs_of(wet, "category"))
    all_weights_ok(dry + wet)


@pytest.mark.parametrize("mode", ["scooter", "mrt", "car", "walk", "bike"])
def test_commute_every_mode(mode):
    for f in (None, fc(), fc(precip_prob_pct=80, apparent_max_c=10, apparent_min_c=8)):
        sigs = commute.signals(ContextInput(commute=mode), TODAY, f)
        assert len(sigs) == 1 and sigs[0].source == "commute" and sigs[0].label
        all_weights_ok(sigs)


def test_commute_none_is_empty():
    assert commute.signals(ContextInput(), TODAY, fc()) == []


def test_derive_warmth_and_water_repellent():
    kagl = pd.DataFrame({
        "title": ["Men Black Puffer Jacket", "Women Linen Shorts", "Grey Wool Sweater", "Basic Tee",
                  "Rain Jacket", "Leather Belt"],
        "subcategory": ["Jackets", "Shorts", "Sweaters", "Tshirts", "Jackets", "Belts"],
        "category": ["outerwear", "bottom", "top", "top", "outerwear", "accessory"]})
    assert weather.derive_warmth(kagl).tolist() == [3, 0, 2, 1, 2, 1]
    assert weather.derive_water_repellent(kagl).tolist() == [False, False, False, False, True, False]

    hm = pd.DataFrame({"prod_name": ["Shell parka", "Strappy top"],
                       "product_type_name": ["Jacket", "Vest top"],
                       "detail_desc": ["Padded parka in water-repellent fabric", "Sleeveless mesh top"]})
    assert weather.derive_warmth(hm).tolist() == [3, 0]
    assert weather.derive_water_repellent(hm).tolist() == [True, False]


def test_derive_missing_columns_defaults():
    df = pd.DataFrame({"price": [1, 2]})
    assert weather.derive_warmth(df).tolist() == [1, 1]
    assert weather.derive_water_repellent(df).tolist() == [False, False]


def test_fetch_forecast_returns_none_on_network_error(monkeypatch, tmp_path):
    import requests
    monkeypatch.setattr(weather, "CACHE_DIR", tmp_path)

    def down(*a, **k):
        raise requests.ConnectionError("offline")
    monkeypatch.setattr(requests, "get", down)
    assert REAL_FETCH(24.8, 120.97, "2026-09-20") is None


def test_fetch_forecast_parses_and_caches(monkeypatch, tmp_path):
    import requests
    monkeypatch.setattr(weather, "CACHE_DIR", tmp_path)

    class R:
        def raise_for_status(self):
            pass

        def json(self):
            return {"daily": {"time": ["2026-09-20"], "temperature_2m_max": [30.1],
                              "temperature_2m_min": [24.0], "apparent_temperature_max": [34.0],
                              "apparent_temperature_min": [26.0], "precipitation_probability_max": [65],
                              "precipitation_sum": [3.2], "wind_speed_10m_max": [18.0],
                              "uv_index_max": [8.1]}}
    calls = []
    monkeypatch.setattr(requests, "get", lambda *a, **k: calls.append(k) or R())
    f1 = REAL_FETCH(24.8, 120.97, "2026-09-20", place="新竹")
    assert f1.precip_prob_pct == 65 and f1.apparent_max_c == 34.0
    assert calls[0]["params"]["timezone"] == "Asia/Taipei"
    f2 = REAL_FETCH(24.8, 120.97, "2026-09-20", place="新竹")   # served from cache
    assert len(calls) == 1 and f2.uv_index_max == 8.1
