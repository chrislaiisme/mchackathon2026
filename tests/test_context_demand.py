"""情境需求雷達: weather + festivals -> demand shifts a manufacturer can act on (intuition v0)."""

from datetime import date, timedelta

import pandas as pd

from engine02.context.base import DailyForecast
from engine02.context.demand import demand_outlook, lead_time_note

START = date(2027, 1, 20)


def fc(i, tmin=20.0, tmax=26.0, rain=10.0, mm=0.0, wind=10.0):
    return DailyForecast(date=(START + timedelta(days=i)).isoformat(), place="新竹", lat=24.8, lon=121.0,
                         temp_min_c=tmin, temp_max_c=tmax, apparent_min_c=tmin, apparent_max_c=tmax,
                         precip_prob_pct=rain, precip_mm=mm, wind_max_kmh=wind)


def find(out, attr, value):
    return next((s for s in out["shifts"] if s["attribute"] == attr and s["value"] == value), None)


def test_cold_spell_raises_warmth_3():
    days = [fc(i, tmin=10.0, tmax=15.0) if i < 4 else fc(i) for i in range(7)]
    out = demand_outlook(days, [], horizon_days=7)
    s = find(out, "warmth", 3)
    assert s and s["direction"] == "up" and 0 < s["strength"] <= 1
    assert any("寒流" in d for d in s["drivers_zh"])
    assert "啟發式" in s["lead_time_note_zh"]
    assert find(out, "warmth", 0)["direction"] == "down"
    assert out["evidence"].startswith("intuition v0")


def test_rain_days_raise_water_repellent():
    days = [fc(i, rain=80.0, mm=12.0) if i % 2 == 0 else fc(i) for i in range(6)]
    out = demand_outlook(days, [], horizon_days=6)
    s = find(out, "water_repellent", True)
    assert s and s["direction"] == "up"
    assert "3/6" in s["drivers_zh"][0]


def test_lunar_new_year_in_window_raises_red_and_gold():
    fests = [{"name_zh": "春節", "date": (START + timedelta(days=5)).isoformat(), "kind": "national"}]
    out = demand_outlook([], fests, horizon_days=14, today=START)
    assert find(out, "color", "Red")["direction"] == "up"
    assert find(out, "color", "Gold")["direction"] == "up"
    assert "春節" in out["window"]["festivals_in_window"]
    assert find(out, "color", "Red")["starts_in_days"] == 5


def test_festival_ranges_and_prep_calendar():
    fests = [{"name_zh": "尾牙季", "start": (START - timedelta(days=3)).isoformat(),
              "end": (START + timedelta(days=10)).isoformat(), "kind": "work"},
             {"name_zh": "萬聖節", "date": (START + timedelta(days=60)).isoformat(), "kind": "western"}]
    out = demand_outlook([], fests, horizon_days=14, today=START)
    assert find(out, "occasion", "Formal")["direction"] == "up"
    assert find(out, "color", "Black") is None               # Halloween is outside the window ...
    prep = out["prep_calendar"]
    assert prep and prep[0]["festival"] == "萬聖節" and prep[0]["days_ahead"] == 60  # ... but on the prep list
    assert "面料" in prep[0]["lead_time_note_zh"]


def test_supply_gap_when_items_given():
    days = [fc(i, tmin=9.0, tmax=13.0) for i in range(4)] + [fc(i) for i in range(4, 7)]
    items = pd.DataFrame({
        "warmth": [3] + [1] * 11,
        "water_repellent": [False] * 12,
        "color": ["Red"] * 2 + ["Blue"] * 10,
    })
    fests = [{"name_zh": "春節", "date": (START + timedelta(days=2)).isoformat(), "kind": "national"}]
    out = demand_outlook(days, fests, items=items, horizon_days=7)
    g = next(g for g in out["supply_gap"] if g["attribute"] == "warmth" and g["value"] == 3)
    assert g["catalog_count"] == 1 and g["catalog_total"] == 12
    assert abs(g["catalog_share"] - 1 / 12) < 1e-3
    assert g["under_supplied"] and "保暖 3 級只佔商品 8%" in g["message_zh"]
    assert "4 天體感 < 14°C" in g["message_zh"]
    red = next(g for g in out["supply_gap"] if g["attribute"] == "color" and g["value"] == "Red")
    assert red["catalog_count"] == 2
    assert "缺口" in out["headline_zh"]


def test_no_items_no_gap_and_missing_column_ignored():
    days = [fc(i, rain=90.0) for i in range(3)]
    assert demand_outlook(days, [], horizon_days=3)["supply_gap"] == []
    items = pd.DataFrame({"color": ["Black"]})             # no water_repellent column: skipped, no error
    assert demand_outlook(days, [], items=items, horizon_days=3)["supply_gap"] == []


def test_empty_inputs_give_empty_shifts():
    out = demand_outlook([], [], horizon_days=14, today="2027-01-01")
    assert out["shifts"] == [] and out["supply_gap"] == [] and out["prep_calendar"] == []
    assert out["headline_zh"]
    out = demand_outlook([], [], items=pd.DataFrame(), horizon_days=14)
    assert out["shifts"] == []


def test_mild_weather_gives_no_shift():
    out = demand_outlook([fc(i) for i in range(7)], [], horizon_days=7)
    assert out["shifts"] == []


def test_lead_time_note_levers():
    assert "面料" in lead_time_note(60)
    assert "快反" in lead_time_note(30)
    assert "調撥" in lead_time_note(5)
    assert "排序" in lead_time_note(1)
