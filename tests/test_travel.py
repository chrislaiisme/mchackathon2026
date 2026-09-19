"""Offline tests for engine02/context/geo.py, context/travel.py and services/itinerary.py.

Every network entry point is monkeypatched: `requests.get` raises unless a test installs a fake.
"""

from datetime import date

import pandas as pd
import pytest
import requests

from engine02.context import geo, travel, weather
from engine02.context.base import MAX_SIGNAL_WEIGHT, DailyForecast
from engine02.contracts import ContextInput, ItineraryEvent
from engine02.kansei import KanseiTable
from engine02.services.itinerary import infer_occasion, plan_itinerary

TODAY = date(2026, 9, 19)
TPE = {"name": "台北", "lat": 25.05, "lon": 121.53, "country": "台灣", "country_code": "TW",
       "timezone": "Asia/Taipei"}
CTS = {"name": "札幌", "lat": 43.07, "lon": 141.35, "country": "日本", "country_code": "JP",
       "timezone": "Asia/Tokyo"}
TKY = {"name": "東京", "lat": 35.69, "lon": 139.69, "country": "日本", "country_code": "JP",
       "timezone": "Asia/Tokyo"}
TXG = {"name": "台中", "lat": 24.15, "lon": 120.67, "country": "台灣", "country_code": "TW",
       "timezone": "Asia/Taipei"}
PLACES = {"台北": TPE, "札幌": CTS, "東京": TKY, "台中": TXG}
ELEMENT_IDS = set(KanseiTable.load().element_ids)


def fake_geocode(name):
    return PLACES.get(name)


def day(lat, lon, date_iso, place="", today=None, **kw):
    """Hot Taipei, cold Sapporo, mild Tokyo; > 15 days ahead comes back as a climate normal."""
    far = (date.fromisoformat(date_iso) - TODAY).days > travel.FORECAST_HORIZON_DAYS
    if lat > 40:
        lo, hi, pop = -1.0, 4.0, 60.0
    elif lat > 30:
        lo, hi, pop = 12.0, 19.0, 20.0
    else:
        lo, hi, pop = 25.0, 31.0, 10.0
    return DailyForecast(date=date_iso, place=place, lat=lat, lon=lon, temp_max_c=hi, temp_min_c=lo,
                         apparent_max_c=hi - 1, apparent_min_c=lo - 2, precip_prob_pct=pop,
                         precip_mm=3.0 if pop >= 50 else 0.0, wind_max_kmh=10,
                         source=travel.NORMAL_SOURCE if far else "open-meteo")


def hourly(lat, lon, date_iso, place="", today=None, **kw):
    hours = {h: {"temp_c": 25.0, "feels_c": 25.0, "precip_prob_pct": 10.0} for h in range(24)}
    hours[19] = {"temp_c": 18.0, "feels_c": 17.0, "precip_prob_pct": 70.0}
    return {"source": "open-meteo", "hours": hours}


@pytest.fixture(autouse=True)
def no_network(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise AssertionError("network must not be touched in tests")
    monkeypatch.setattr(requests, "get", boom)
    monkeypatch.setattr(weather, "fetch_forecast", boom)
    monkeypatch.setattr(geo, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(travel, "CACHE_DIR", tmp_path)
    monkeypatch.delenv("ENGINE02_DEMO", raising=False)


def check_signals(sigs):
    for s in sigs:
        assert s.source == "travel" and s.evidence == "intuition v0 (not yet measured)"
        for p in s.prefs:
            assert abs(p.weight) <= MAX_SIGNAL_WEIGHT
        assert set(s.design_steps) <= ELEMENT_IDS, s.design_steps


# ----------------------------------------------------------------------------- geo

class FakeResp:
    def __init__(self, js):
        self.js = js

    def raise_for_status(self):
        pass

    def json(self):
        return self.js


def test_geocode_uses_alias_caches_and_returns_none_on_failure(monkeypatch, tmp_path):
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(params["name"])
        assert "geocoding-api.open-meteo.com" in url and params["language"] == "zh"
        if params["name"] == "Sapporo":
            return FakeResp({"results": [{"name": "札幌市", "latitude": 43.06667, "longitude": 141.35,
                                          "country": "日本", "country_code": "JP",
                                          "timezone": "Asia/Tokyo"}]})
        return FakeResp({"generationtime_ms": 0.1})

    monkeypatch.setattr(requests, "get", fake_get)
    g = geo.geocode("札幌")
    assert g and abs(g["lat"] - 43.07) < 0.01 and g["country_code"] == "JP"
    assert g["timezone"] == "Asia/Tokyo" and g["name"] == "札幌"
    assert calls == ["Sapporo"]                       # zh alias -> English search term
    assert list(tmp_path.glob("geocode_*.json"))
    # second call is served from cache: no request at all
    monkeypatch.setattr(requests, "get", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    assert geo.geocode("札幌")["lon"] == pytest.approx(141.35)
    # unknown place / network down / empty -> None, never raises
    assert geo.geocode("不存在的地方") is None
    assert geo.geocode("") is None and geo.geocode(None) is None


def test_haversine_taipei_sapporo():
    km = geo.haversine_km(25.05, 121.53, 43.07, 141.35)
    assert 2600 < km < 2800          # TPE-CTS great circle is ~2,690 km
    assert geo.haversine_km(25.0, 121.5, 25.0, 121.5) == pytest.approx(0.0)
    assert 130 < geo.haversine_km(25.05, 121.53, 24.15, 120.67) < 150      # 台北-台中


@pytest.mark.parametrize("km,oc,dc,mode", [
    (2400, "TW", "JP", "flight"), (150, "TW", "JP", "flight"), (600, "JP", "JP", "flight"),
    (140, "TW", "TW", "hsr"), (350, "台灣", "TW", "hsr"), (50, "TW", "TW", "car"),
    (10, "TW", "TW", "scooter"), (10, "JP", "JP", "mrt"), (200, "JP", "JP", "train"),
    (100, None, None, "train"),
])
def test_infer_transport(km, oc, dc, mode):
    assert geo.infer_transport(km, oc, dc) == mode


# ----------------------------------------------------------------------------- travel signals

def test_no_travel_info_no_signals():
    assert travel.signals(ContextInput(city="台北", lat=25.05, lon=121.53), TODAY,
                          geocode_fn=fake_geocode, day_fn=day, hourly_fn=hourly) == []


def test_climate_gap_route_and_long_flight():
    ctx = ContextInput(city="札幌", event_date="2026-09-25", origin_city="台北")
    sigs = travel.signals(ctx, TODAY, geocode_fn=fake_geocode, day_fn=day, hourly_fn=hourly)
    check_signals(sigs)
    labels = [s.label for s in sigs]
    route = [s for s in sigs if not s.affects_ranking]
    assert route and route[0].detail["transport"] == "flight" and route[0].detail["transport_inferred"]
    assert "台北 → 札幌" in route[0].label and "km" in route[0].label
    gap = [s for s in sigs if "落差" in s.label]
    assert gap, labels
    assert "台北 28°C → 札幌 2°C" in gap[0].label and "洋蔥式" in gap[0].label
    assert any(p.column == "warmth" and p.target == 3 for p in gap[0].prefs)
    assert any(p.column == "category" and p.values == ["outerwear"] and p.weight > 0 for p in gap[0].prefs)
    assert gap[0].design_steps.get("soft_knit", 0) > 0
    fly = [s for s in sigs if "長途飛行" in s.label]
    assert fly and fly[0].design_steps["relaxed_fit"] > 0 and "不易皺" in fly[0].label
    assert not any("往年平均" in lbl for lbl in labels)       # within forecast range


def test_hotter_destination_and_hsr_smart_casual():
    ctx = ContextInput(city="台北", event_date="2026-09-25", origin_city="札幌")
    sigs = travel.signals(ctx, TODAY, geocode_fn=fake_geocode, day_fn=day, hourly_fn=hourly)
    check_signals(sigs)
    assert any("落差" in s.label and "輕薄" in s.label for s in sigs)
    ctx = ContextInput(city="台中", event_date="2026-09-25", origin_city="台北")
    sigs = travel.signals(ctx, TODAY, geocode_fn=fake_geocode, day_fn=day, hourly_fn=hourly)
    check_signals(sigs)
    hsr = [s for s in sigs if "高鐵" in s.label and s.affects_ranking]
    assert hsr and hsr[0].prefs[0].values == ["Smart Casual"]


def test_scooter_signal_skipped_when_commute_is_set():
    base = dict(city="台北", lat=25.03, lon=121.56, origin_city="台北", origin_lat=25.05,
                origin_lon=121.53, event_date="2026-09-20")
    sigs = travel.signals(ContextInput(**base), TODAY, geocode_fn=fake_geocode, day_fn=day,
                          hourly_fn=hourly)
    assert any("騎車" in s.label for s in sigs)
    sigs = travel.signals(ContextInput(**base, commute="scooter"), TODAY, geocode_fn=fake_geocode,
                          day_fn=day, hourly_fn=hourly)
    assert not any("騎車移動" in s.label for s in sigs)


def test_beyond_forecast_range_uses_climate_normals():
    ctx = ContextInput(city="札幌", event_date="2026-12-10", origin_city="台北")
    sigs = travel.signals(ctx, TODAY, geocode_fn=fake_geocode, day_fn=day, hourly_fn=hourly)
    check_signals(sigs)
    normal = [s for s in sigs if "往年平均" in s.label and "非預報" in s.label]
    assert normal, [s.label for s in sigs]
    assert normal[0].label.startswith("12 月札幌往年平均 -1～4°C（歷史平均，非預報）")
    assert any(p.column == "warmth" and p.target == 3 for p in normal[0].prefs)
    assert any(p.column == "water_repellent" for p in normal[0].prefs)       # 60% rainy days
    assert any("落差" in s.label and "（往年平均）" in s.label for s in sigs)


def test_fetch_climate_normals_averages_same_dates(monkeypatch):
    seen = []

    def fake_get(url, params=None, timeout=None):
        assert "archive-api.open-meteo.com" in url
        seen.append(params["start_date"])
        y = int(params["start_date"][:4])
        off = y - 2021                                   # 2021..2025 -> 0..4
        times = ["2025-12-07", "2025-12-08"]
        hours = [f"{params['start_date']}T{h:02d}:00" for h in range(24)]
        return FakeResp({
            "daily": {"time": times, "temperature_2m_max": [2 + off, 2 + off],
                      "temperature_2m_min": [-3 + off, -3 + off],
                      "apparent_temperature_max": [-1, -1], "apparent_temperature_min": [-7, -7],
                      "precipitation_sum": [0.0, 5.0], "wind_speed_10m_max": [20, 20]},
            "hourly": {"time": hours, "temperature_2m": [float(h) for h in range(24)],
                       "apparent_temperature": [float(h) - 3 for h in range(24)],
                       "precipitation": [0.0] * 24}})

    monkeypatch.setattr(requests, "get", fake_get)
    n = travel.fetch_climate_normals(43.07, 141.35, "2026-12-10")
    assert len(seen) == 5 and seen[0] == "2021-12-07" and seen[-1] == "2025-12-07"
    assert n["daily"]["temp_max_c"] == pytest.approx(4.0)        # mean of 2..6
    assert n["daily"]["precip_prob_pct"] == pytest.approx(50.0)
    assert n["hourly"]["19"]["feels_c"] == pytest.approx(16.0)
    fc = travel.normals_forecast(43.07, 141.35, "2026-12-10", place="札幌")
    assert fc.source == travel.NORMAL_SOURCE and fc.temp_min_c == pytest.approx(-1.0)
    # cached: a second call does not hit the network
    monkeypatch.setattr(requests, "get", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    assert travel.fetch_climate_normals(43.07, 141.35, "2026-12-10") is not None
    # day_weather: far date -> normals; the forecast fetcher is never consulted
    assert travel.day_weather(43.07, 141.35, "2026-12-10", "札幌", TODAY).source == travel.NORMAL_SOURCE


def test_event_time_hourly_signal():
    ctx = ContextInput(city="台北", lat=25.05, lon=121.53, event_date="2026-09-20", event_time="19:00")
    sigs = travel.signals(ctx, TODAY, geocode_fn=fake_geocode, day_fn=day, hourly_fn=hourly)
    check_signals(sigs)
    ev = [s for s in sigs if "點" in s.label]
    assert ev, [s.label for s in sigs]
    assert ev[0].label.startswith("晚上 7 點體感 17°C，比白天冷 8°C → 帶件外套")
    assert "降雨 70%" in ev[0].label
    cols = {p.column for p in ev[0].prefs}
    assert {"warmth", "category", "water_repellent"} <= cols
    assert ev[0].detail["hour"] == 19


@pytest.mark.parametrize("s,h", [("19:00", 19), ("7pm", 19), ("08:30", 8), ("晚上7點", 19),
                                 ("25:00", None), (None, None)])
def test_parse_hour(s, h):
    assert travel.parse_hour(s) == h


def test_hour_zh():
    assert travel.hour_zh(19) == "晚上 7 點"
    assert travel.hour_zh(12) == "中午 12 點"
    assert travel.hour_zh(0) == "凌晨 12 點"
    assert travel.hour_zh(15) == "下午 3 點"


def test_signals_never_need_network_when_nothing_resolves():
    ctx = ContextInput(city="亞特蘭提斯", origin_city="烏托邦", event_time="19:00")
    assert travel.signals(ctx, TODAY, geocode_fn=lambda n: None, day_fn=day, hourly_fn=hourly) == []


# ----------------------------------------------------------------------------- itinerary

def catalog():
    rows = []
    k = 0
    for cat, colors, warmths in [("top", ["White", "Black", "Navy Blue", "Red"], [1, 2, 0, 2]),
                                 ("bottom", ["Black", "Beige", "Grey"], [1, 2, 1]),
                                 ("shoes", ["Black", "White"], [1, 2]),
                                 ("dress", ["Black"], [1]),
                                 ("outerwear", ["Beige", "Black"], [3, 2])]:
        for c, w in zip(colors, warmths):
            k += 1
            rows.append({"item_id": f"i{k}", "title": f"{cat} {c}", "category": cat, "color": c,
                         "warmth": w, "water_repellent": cat == "outerwear" and c == "Black",
                         "price": 500.0 + 10 * k})
    return pd.DataFrame(rows)


def test_plan_itinerary_three_events():
    events = [
        {"date": "2026-09-24", "city": "台北", "time": "10:00", "note": "市集散步"},
        ItineraryEvent(date="2026-09-26", city="札幌", time="19:00", occasion="婚禮"),
        {"date": "2026-10-30", "city": "東京", "occasion": "爬山"},
    ]
    ranked_with = []

    def rank_fn(ctx):
        ranked_with.append(ctx)
        return [{"item_id": "i1"}, {"item_id": "i5"}, "i10"]

    res = plan_itinerary(events, catalog(), origin={"city": "台北"}, n_capsule=8, rank_fn=rank_fn,
                         forecast_fn=day, geocode_fn=fake_geocode, hourly_fn=hourly, today=TODAY)
    evs = res["events"]
    assert [e["city"] for e in evs] == ["台北", "札幌", "東京"]
    assert len(ranked_with) == 3 and all(isinstance(c, ContextInput) for c in ranked_with)
    for e in evs:
        assert e["top_item_ids"] == ["i1", "i5", "i10"]
        assert e["summary_zh"] and e["request_patch"]["context"]["city"] == e["city"]
        ContextInput(**e["context"])                                 # valid for POST /rank
    # the first stop is home: no origin; later stops come from the previous stop
    assert "origin_city" not in evs[0]["context"]
    assert evs[1]["context"]["origin_city"] == "台北" and evs[2]["context"]["origin_city"] == "札幌"
    assert evs[1]["occasion"] == "Formal" and evs[2]["occasion"] == "Sports"
    assert evs[1]["request_patch"]["constraints"]["occasion"]["values"] == ["Formal"]
    assert any("落差" in s for s in evs[1]["signals_zh"])
    assert any("晚上 7 點" in s for s in evs[1]["signals_zh"])
    assert evs[2]["weather_source"] == travel.NORMAL_SOURCE and "非預報" in evs[2]["summary_zh"]
    cap = res["capsule"]
    assert cap["items"] and cap["n_outfits"] >= 1 and len(cap["per_day_plan"]) == 3
    notes = res["packing_notes_zh"]
    assert notes[0].startswith("3 個城市、溫差 32°C：以洋蔥式為主，帶一件防潑水外套")
    assert any("婚禮" in n for n in notes) and any("往年平均" in n for n in notes)
    assert res["trip"]["climate_normal_days"] == 1


def test_plan_itinerary_survives_failures():
    def bad_rank(ctx):
        raise RuntimeError("ranker down")

    res = plan_itinerary([{"date": "2026-09-24", "city": "亞特蘭提斯"}], catalog(),
                         rank_fn=bad_rank, forecast_fn=day, geocode_fn=lambda n: None,
                         hourly_fn=hourly, today=TODAY)
    e = res["events"][0]
    assert e["weather"] is None and "天氣查不到" in e["summary_zh"] and "rank_error" in e
    assert any("查不到天氣" in n for n in res["packing_notes_zh"])


def test_infer_occasion():
    assert infer_occasion("婚禮") == "Formal"
    assert infer_occasion(None, "海邊晚餐") == "Smart Casual"
    assert infer_occasion("formal") == "Formal"
    assert infer_occasion("隨便") is None
