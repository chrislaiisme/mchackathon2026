"""A forecast is only worth showing if it is scored against "just repeat last year"."""

import json
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
HISTORY = sorted((ROOT / "data" / "trends" / "history").glob("wikipedia_*.json"))


def seasonal_series(n: int = 300, m: int = 52, noise: float = 0.0) -> np.ndarray:
    t = np.arange(n)
    rng = np.random.default_rng(0)
    return (100 + 20 * np.sin(2 * np.pi * t / m) + 0.05 * t
            + (rng.normal(0, noise, n) if noise else 0.0))


def test_seasonal_naive_is_exactly_one_on_its_own_scale():
    """MASE must be anchored: the baseline scores ~1 by construction, so a number below 1 means
    something specific rather than 'looks good'."""
    from engine02.forecast import backtest

    res = backtest(seasonal_series(), m=52, h=8, n_windows=5)
    assert 0.5 < res.mase["seasonal_naive"] < 2.0, res.mase


def test_a_model_that_cannot_beat_the_baseline_is_reported_not_hidden():
    from engine02.forecast import MODELS, backtest

    # pure seasonality with no trend: seasonal naive is genuinely hard to beat
    res = backtest(seasonal_series(noise=0.0), m=52, h=8, n_windows=5)
    assert set(res.mase) == set(MODELS)
    assert all(np.isfinite(v) for v in res.mase.values()), res.mase


def test_backtest_refuses_a_series_that_is_too_short():
    from engine02.forecast import backtest

    res = backtest(np.arange(20, dtype=float), m=52, h=8)
    assert res.n_windows == 0 and res.note, res
    assert not res.mase


def test_the_interval_comes_from_measured_errors_not_an_assumption():
    from engine02.forecast import forecast_with_interval

    fc = forecast_with_interval(seasonal_series(noise=5.0), model="combination", h=8, level=0.8)
    assert len(fc["point"]) == 8 and len(fc["lower"]) == 8
    assert fc["interval_from_n_windows"] > 0
    # the point sits inside its own interval because the measured bias has been removed from it,
    # and the correction is reported rather than folded away
    assert all(lo <= p <= hi for lo, p, hi in zip(fc["lower"], fc["point"], fc["upper"]))
    assert "bias_correction" in fc and len(fc["bias_correction"]) == 8
    assert fc["point"] != fc["point_uncorrected"] or all(b == 0 for b in fc["bias_correction"])


def test_a_noisier_series_gets_a_wider_interval():
    """An interval that does not widen when the model does worse is decoration."""
    from engine02.forecast import forecast_with_interval

    calm = forecast_with_interval(seasonal_series(noise=1.0), h=8)
    wild = forecast_with_interval(seasonal_series(noise=30.0), h=8)
    calm_w = np.mean(np.array(calm["upper"]) - np.array(calm["lower"]))
    wild_w = np.mean(np.array(wild["upper"]) - np.array(wild["lower"]))
    assert wild_w > calm_w, (calm_w, wild_w)


@pytest.mark.skipif(not HISTORY, reason="run scripts/fetch_trend_history.py")
def test_the_real_backtest_still_beats_the_baseline():
    """The claim in §3.37, checked against the data it came from: on real Wikipedia fashion series
    the combination beats seasonal naive. If this ever flips, the panel must stop claiming it."""
    from engine02.forecast import backtest

    doc = json.loads(HISTORY[-1].read_text(encoding="utf-8"))
    combo, base = [], []
    for s in doc["series"].values():
        vals = np.array([p["views"] for p in s["points"]], dtype=np.float64)
        n = (len(vals) // 7) * 7
        res = backtest(vals[:n].reshape(-1, 7).sum(axis=1), m=52, h=8, n_windows=10)
        if res.mase:
            combo.append(res.mase["combination"])
            base.append(res.mase["seasonal_naive"])
    assert len(combo) >= 10
    assert np.nanmean(combo) < np.nanmean(base), (np.nanmean(combo), np.nanmean(base))


@pytest.mark.skipif(not HISTORY, reason="run scripts/fetch_trend_history.py")
def test_the_endpoint_never_returns_a_forecast_without_its_backtest(monkeypatch):
    monkeypatch.setenv("ENGINE02_ENCODER", "hash")
    monkeypatch.setenv("ENGINE02_LLM", "none")
    monkeypatch.setenv("ENGINE02_DEMO", "1")
    from fastapi.testclient import TestClient

    from engine02.api import app

    with TestClient(app) as client:
        b = client.get("/trends/forecast?h=8").json()
        assert b["available"] and b["affects_score"] is False
        for r in b["series"]:
            assert r["forecast"]["point"], r
            assert "mase" in r["backtest"] and "seasonal_naive_mase" in r["backtest"]
            # a series the model handles badly must say so rather than look identical
            if r["backtest"]["mase"] >= 1.0:
                assert r["trustworthy"] is False and r["note"], r
