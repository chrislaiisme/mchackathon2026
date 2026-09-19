from datetime import date

import pytest

from engine02.attribute_fill import COLOR_TO_FAMILY
from engine02.context import festival, lucky
from engine02.context.base import MAX_SIGNAL_WEIGHT
from engine02.contracts import ContextInput


def _all_colour_values(sigs):
    for s in sigs:
        for p in s.prefs:
            if p.column == "color":
                yield from p.values


def _check_signal_shape(sigs):
    for s in sigs:
        for p in s.prefs:
            assert abs(p.weight) <= MAX_SIGNAL_WEIGHT
        for c in _all_colour_values([s]):
            assert c.lower() in COLOR_TO_FAMILY, c


# ---------------------------------------------------------------- calendar data

def test_lunar_new_year_2027_dates():
    lny = [o for o in festival.load_occasions() if o.key == "lunar_new_year"]
    assert len(lny) == 1
    assert lny[0].start == date(2027, 2, 5)        # 除夕
    import json
    raw = json.loads(festival.FESTIVALS_PATH.read_text(encoding="utf-8"))
    rec = next(o for o in raw["occasions"] if o["key"] == "lunar_new_year")
    assert rec["eve"] == "2027-02-05" and rec["day1"] == "2027-02-06"


def test_other_lunar_dates():
    by = {(o.key, o.start.year): o.start for o in festival.load_occasions()}
    assert by[("mid_autumn", 2026)] == date(2026, 9, 25)
    assert by[("mid_autumn", 2027)] == date(2027, 9, 15)
    assert by[("dragon_boat", 2027)] == date(2027, 6, 9)
    assert by[("qixi", 2027)] == date(2027, 8, 8)
    assert by[("lantern", 2027)] == date(2027, 2, 20)


def test_every_occasion_has_required_fields_and_a_rule():
    import json
    raw = json.loads(festival.FESTIVALS_PATH.read_text(encoding="utf-8"))
    for o in raw["occasions"]:
        for f in ("name_zh", "name_en", "window_days_before", "kind", "source_url"):
            assert f in o, (o, f)
        assert ("date" in o) or ("start" in o and "end" in o)
        assert o["kind"] in {"festival", "commercial", "season", "school"}
        assert o["key"] in festival.RULES


# ---------------------------------------------------------------- window logic

def test_window_logic():
    o = festival.Occasion("x", "測試節", "Test", date(2027, 2, 14), date(2027, 2, 14), 7, "festival", "")
    assert not o.covers(date(2027, 2, 6))
    assert o.covers(date(2027, 2, 7))               # first day of the window
    assert o.covers(date(2027, 2, 14))
    assert not o.covers(date(2027, 2, 15))
    assert o.days_until(date(2027, 2, 10)) == 4
    # the nudge grows as the day approaches
    early = festival.signal_for(festival.load_occasions()[0], date(2026, 9, 15))
    late = festival.signal_for(festival.load_occasions()[0], date(2026, 9, 25))
    assert early.detail["key"] == late.detail["key"] == "mid_autumn"
    assert early.prefs[0].weight < late.prefs[0].weight


def test_no_festival_on_a_quiet_day():
    assert festival.signals(ContextInput(event_date="2027-03-20"), today=date(2027, 3, 20)) == []


# ---------------------------------------------------------------- festival signals

def test_lunar_new_year_signal_prefers_red_gold():
    sigs = festival.signals(ContextInput(event_date="2027-02-04"), today=date(2026, 9, 19))
    lny = next(s for s in sigs if s.detail["key"] == "lunar_new_year")
    assert lny.source == "festival" and lny.affects_ranking and not lny.opt_in
    assert "過年穿紅" in lny.label
    colours = next(p for p in lny.prefs if p.column == "color").values
    assert "Red" in colours and "Gold" in colours
    assert lny.evidence == "intuition v0 (not yet measured)"
    _check_signal_shape(sigs)


def test_event_date_beats_today():
    sigs = festival.signals(ContextInput(event_date="2026-10-30"), today=date(2027, 2, 5))
    assert [s.detail["key"] for s in sigs] == ["halloween"]
    bold = next(p for p in sigs[0].prefs if p.column == "boldness")
    assert bold.target == 3.0


def test_today_used_when_no_event_date():
    sigs = festival.signals(ContextInput(), today=date(2026, 9, 24))
    assert sigs and sigs[0].detail["key"] == "mid_autumn"
    assert "明天就中秋節" in sigs[0].label


def test_double11_is_label_only():
    sigs = festival.signals(ContextInput(event_date="2026-11-10"))
    d11 = next(s for s in sigs if s.detail["key"] == "double11")
    assert d11.affects_ranking is False and d11.prefs == []
    assert "衝預算" in d11.label


@pytest.mark.parametrize("day", [o.start for o in festival.load_occasions()])
def test_every_occasion_day_weights_and_colours_valid(day):
    sigs = festival.signals(ContextInput(event_date=day.isoformat()))
    assert sigs
    _check_signal_shape(sigs)


# ---------------------------------------------------------------- lucky colour

def test_lucky_needs_opt_in():
    assert lucky.signals(ContextInput(), today=date(2026, 9, 19)) == []
    assert lucky.signals(None, today=date(2026, 9, 19)) == []


def test_lucky_display_only_by_default():
    sigs = lucky.signals(ContextInput(lucky={"zodiac": "leo", "birth_year": 1998}), today=date(2026, 9, 19))
    assert len(sigs) == 2
    for s in sigs:
        assert s.source == "lucky_color" and s.opt_in is True and s.affects_ranking is False
        assert s.label.startswith("今日幸運色：") and "僅供娛樂" in s.label
        assert s.evidence == "entertainment, not a style claim"
    _check_signal_shape(sigs)


def test_lucky_ranks_only_when_apply_true():
    on = lucky.signals(ContextInput(lucky={"zodiac": "天蠍座", "apply": True}), today=date(2026, 9, 19))
    assert len(on) == 1 and on[0].affects_ranking is True
    truthy = lucky.signals(ContextInput(lucky={"zodiac": "scorpio", "apply": "yes"}), today=date(2026, 9, 19))
    assert truthy[0].affects_ranking is False       # only literal True switches ranking on


def test_lucky_deterministic_and_day_pillar():
    a = lucky.signals(ContextInput(lucky={"birth_year": 1990}), today=date(2027, 2, 6))
    b = lucky.signals(ContextInput(lucky={"birth_year": 1990}), today=date(2027, 2, 6))
    assert [s.label for s in a] == [s.label for s in b]
    assert [s.prefs[0].values for s in a] == [s.prefs[0].values for s in b]
    assert lucky.day_pillar(date(2000, 1, 1)) == ("戊午", "土")
    assert lucky.year_info(1998) == ("虎", "土")        # 戊寅
    assert lucky.year_info(2026) == ("馬", "火")        # 丙午


def test_lucky_all_colours_valid_every_element():
    for colours in list(lucky.WUXING_COLORS.values()) + list(lucky.ZODIAC_COLORS.values()):
        for c in colours:
            assert c.lower() in COLOR_TO_FAMILY, c
    for sign in lucky.ZODIAC_SIGNS:
        for y in range(1990, 2002):
            sigs = lucky.signals(ContextInput(lucky={"zodiac": sign, "birth_year": y}), today=date(2026, 12, 1))
            assert len(sigs) == 2
            _check_signal_shape(sigs)
