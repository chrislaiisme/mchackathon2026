import itertools

import pytest

from engine02.attribute_fill import COLOR_TO_FAMILY
from engine02.context import personal, quiz
from engine02.context.base import MAX_SIGNAL_WEIGHT, ContextSignal
from engine02.contracts import ContextInput
from engine02.kansei import KanseiTable

ELEMENT_IDS = set(KanseiTable.load().element_ids)
STYLES = {"minimalist", "streetwear", "classic", "sporty", "bohemian", "romantic", "edgy",
          "vintage", "preppy", "avant_garde"}
MOODS = ["energetic", "calm", "confident", "low", "adventurous"]
SEASONS = ["spring", "summer", "autumn", "winter"]


def _check_signal(sig: ContextSignal):
    assert sig.label and sig.opt_in and sig.affects_ranking
    assert set(sig.design_steps) <= ELEMENT_IDS, set(sig.design_steps) - ELEMENT_IDS
    for p in sig.prefs:
        assert abs(p.weight) <= MAX_SIGNAL_WEIGHT
        if p.column == "color":
            bad = [c for c in p.values if c.lower() not in COLOR_TO_FAMILY]
            assert not bad, bad
        if p.column == "style":
            assert set(p.values) <= STYLES
        if p.column == "boldness":
            assert 0 <= p.target <= 3


@pytest.mark.parametrize("mood", MOODS)
def test_each_mood_yields_valid_signal(mood):
    sigs = personal.signals(ContextInput(mood=mood), None)
    assert len(sigs) == 1 and sigs[0].source == "mood"
    assert sigs[0].design_steps
    _check_signal(sigs[0])


@pytest.mark.parametrize("season", SEASONS)
def test_personal_color_palette_valid(season):
    (sig,) = personal.signals(ContextInput(personal_color=season), None)
    assert sig.source == "personal_color"
    _check_signal(sig)
    prefer, avoid = sig.prefs
    assert prefer.weight == 0.25 and avoid.weight == -0.15
    assert not set(prefer.values) & set(avoid.values)


def test_autumn_label():
    (sig,) = personal.signals({"personal_color": "autumn"})
    assert sig.label == "你是秋季型：大地色、橄欖綠最顯氣色"


def test_both_and_empty():
    assert personal.signals(ContextInput(), None) == []
    assert personal.signals(None) == []
    assert personal.signals({}) == []
    both = personal.signals(ContextInput(mood="low", personal_color="winter"))
    assert [s.source for s in both] == ["personal_color", "mood"]


def test_quiz_shape():
    assert len(quiz.QUESTIONS) == 5
    for q in quiz.QUESTIONS:
        assert q["id"] and q["question"] and len(q["options"]) >= 2
        for o in q["options"]:
            assert set(o["scores"]) <= set(SEASONS)


def test_quiz_deterministic_and_covers_all_types():
    seen = set()
    choices = [[o["id"] for o in q["options"]] for q in quiz.QUESTIONS]
    ids = [q["id"] for q in quiz.QUESTIONS]
    for combo in itertools.product(*choices):
        ans = dict(zip(ids, combo))
        r1, r2 = quiz.score_quiz(ans), quiz.score_quiz(dict(reversed(list(ans.items()))))
        assert r1 == r2
        assert r1["personal_color"] in SEASONS
        assert 0 <= r1["confidence"] <= 1 and r1["explanation_zh"]
        seen.add(r1["personal_color"])
    assert seen == set(SEASONS)


def test_quiz_archetypes():
    assert quiz.score_quiz({"vein": "green", "metal": "gold", "sun": "tan", "contrast": "deep_warm",
                            "neutral": "brown_khaki"})["personal_color"] == "autumn"
    assert quiz.score_quiz({"vein": "blue", "metal": "silver", "sun": "tan", "contrast": "high",
                            "neutral": "black_white"})["personal_color"] == "winter"
    assert quiz.score_quiz({"vein": "blue", "metal": "silver", "sun": "burn", "contrast": "soft",
                            "neutral": "grey_navy"})["personal_color"] == "summer"
    assert quiz.score_quiz({"vein": "green", "metal": "gold", "sun": "golden", "contrast": "bright",
                            "neutral": "ivory_camel"})["personal_color"] == "spring"


def test_quiz_empty():
    r = quiz.score_quiz({})
    assert r["personal_color"] is None and r["confidence"] == 0.0
    assert quiz.score_quiz({"bogus": "x"})["personal_color"] is None
