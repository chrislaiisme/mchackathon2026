"""engine02/context/auto.py: ENGINE 02 fills in date, hour and city itself; the caller always wins."""

from datetime import datetime
from pathlib import Path

import pytest

from engine02.context.auto import TAIWAN, auto_context
from engine02.contracts import ContextInput

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "catalog" / "kagl" / "items.parquet"
NOW = datetime(2026, 9, 20, 14, 30, tzinfo=TAIWAN)


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setenv("ENGINE02_AUTO_CONTEXT", "1")


def test_nothing_sent_means_today_this_hour_and_hsinchu():
    ctx, filled = auto_context(None, NOW)
    assert filled == {"event_date": "2026-09-20", "event_time": "14:00", "city": "新竹市",
                      "lat": 24.8138, "lon": 120.9675}
    assert ctx.city == "新竹市" and ctx.event_time == "14:00"


def test_overnight_the_current_hour_is_not_the_hour_to_dress_for():
    _, filled = auto_context(None, datetime(2026, 9, 20, 1, 5, tzinfo=TAIWAN))
    assert "event_time" not in filled and filled["event_date"] == "2026-09-20"


def test_the_callers_fields_always_win_and_a_future_trip_gets_no_current_hour():
    _, filled = auto_context(ContextInput(city="札幌", event_date="2026-11-03"), NOW)
    assert filled == {}
    _, filled = auto_context(ContextInput(commute="scooter"), NOW)
    assert set(filled) == {"event_date", "event_time", "city", "lat", "lon"}
    _, filled = auto_context(ContextInput(lat=25.0, lon=121.5), NOW)
    assert "city" not in filled                     # coordinates given: no city assumed


def test_default_city_and_switch_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("ENGINE02_DEFAULT_CITY", "台中市")
    monkeypatch.setenv("ENGINE02_DEFAULT_LAT", "24.14")
    monkeypatch.setenv("ENGINE02_DEFAULT_LON", "120.68")
    assert auto_context(None, NOW)[1]["city"] == "台中市"
    monkeypatch.setenv("ENGINE02_AUTO_CONTEXT", "0")
    assert auto_context(None, NOW) == (None, {})


@pytest.mark.skipif(not CATALOG.exists(), reason="needs data/catalog/kagl")
def test_rank_reports_what_it_filled_in(monkeypatch):
    monkeypatch.setenv("ENGINE02_ENCODER", "hash")
    monkeypatch.setenv("ENGINE02_LLM", "none")
    monkeypatch.setenv("ENGINE02_DEMO", "1")            # no network: the weather may be missing,
    from fastapi.testclient import TestClient           # which must be reported, not crash

    from engine02.api import app

    with TestClient(app) as c:
        r = c.post("/rank", json={"session_id": "auto", "retrieval_text": "white shirt", "options": {"top_k": 3}}).json()
        used = r["context_used"]
        assert used["auto_filled"]["city"] == "新竹市" and used["auto_filled"]["event_date"]
        assert isinstance(used["signals"], list) and isinstance(used["problems"], list)
        given = c.post("/rank", json={"session_id": "auto2", "retrieval_text": "white shirt",
                                      "context": {"city": "札幌", "event_date": "2026-11-03"},
                                      "options": {"top_k": 3}}).json()
        assert "auto_filled" not in given["context_used"]
        ir = c.post("/intent/rank", json={"session_id": "auto3", "intent": {"item_type": "洋裝"}, "top_k": 2}).json()
        assert ir["engine02"]["context_used"]["auto_filled"]["city"] == "新竹市"      # ENGINE 01's path too
