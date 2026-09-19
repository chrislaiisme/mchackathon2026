"""Forecasting with a backtest attached, because a forecast without one is a guess with a chart.

The point of this module is not the models — they are deliberately simple and dependency-free. The
point is the protocol: rolling-origin evaluation against a seasonal-naive baseline, scored with
MASE (Hyndman & Koehler, IJF 2006), so every number we show can be compared to "just repeat last
season" and be found better or worse.

  * MASE < 1  the model beats seasonal naive on this series
  * MASE = 1  it is seasonal naive
  * MASE > 1  it is worse, and we say so

The M4 competition's own conclusion is the reason this is built baseline-first: simple statistical
methods and their combinations beat most machine learning entries, and the winners were hybrids
anchored on classical components. A fashion demo that shows a curve without this comparison is
showing a drawing.

Nothing here touches the ranking. Trend terms were measured entering the score in 28 configurations
and all 28 were worse (§3.15); this produces a panel number, with its own error bar.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


# ---------------------------------------------------------------------------------------------
# models: each takes history and returns `h` future points
# ---------------------------------------------------------------------------------------------
def naive(y: np.ndarray, h: int, m: int = 52) -> np.ndarray:
    return np.repeat(y[-1], h)


def seasonal_naive(y: np.ndarray, h: int, m: int = 52) -> np.ndarray:
    """Repeat the value from one season ago — the baseline everything is scored against."""
    if len(y) < m:
        return naive(y, h)
    idx = [len(y) - m + (i % m) for i in range(h)]
    return y[idx]


def drift(y: np.ndarray, h: int, m: int = 52) -> np.ndarray:
    if len(y) < 2:
        return naive(y, h)
    slope = (y[-1] - y[0]) / (len(y) - 1)
    return y[-1] + slope * np.arange(1, h + 1)


def ses(y: np.ndarray, h: int, m: int = 52, alpha: float | None = None) -> np.ndarray:
    """Simple exponential smoothing; alpha fitted on a small grid by in-sample SSE."""
    if len(y) == 0:
        return np.zeros(h)
    if alpha is None:
        best, best_sse = 0.3, np.inf
        for a in np.linspace(0.05, 0.95, 19):
            level, sse = y[0], 0.0
            for t in range(1, len(y)):
                sse += (y[t] - level) ** 2
                level = a * y[t] + (1 - a) * level
            if sse < best_sse:
                best, best_sse = a, sse
        alpha = best
    level = y[0]
    for t in range(1, len(y)):
        level = alpha * y[t] + (1 - alpha) * level
    return np.repeat(level, h)


def theta(y: np.ndarray, h: int, m: int = 52) -> np.ndarray:
    """The Theta method (Assimakopoulos & Nikolopoulos, IJF 2000), the M3 winner.

    Theta-2 line (double the local curvature) forecast by SES, plus half the linear trend of the
    Theta-0 line. Equivalent to SES with drift; kept explicit so the two halves stay readable.
    """
    n = len(y)
    if n < 4:
        return naive(y, h)
    t = np.arange(n)
    b, a = np.polyfit(t, y, 1)          # slope, intercept of the theta-0 (linear) line
    smoothed = ses(y, h, m)             # level from SES on the raw series
    return smoothed + 0.5 * b * np.arange(1, h + 1)


def seasonal_theta(y: np.ndarray, h: int, m: int = 52) -> np.ndarray:
    """Theta on the seasonally-adjusted series, then the seasonal profile added back.

    Fashion attention is strongly annual (coats in November, linen in June), so the seasonal part
    is usually most of the signal; this separates it from the trend instead of hoping one model
    catches both.
    """
    if len(y) < 2 * m:
        return theta(y, h, m)
    # classical additive seasonality: average deviation from the centred moving average
    season = np.zeros(m)
    counts = np.zeros(m)
    trend = np.convolve(y, np.ones(m) / m, mode="same")
    for i, v in enumerate(y - trend):
        season[i % m] += v
        counts[i % m] += 1
    season = np.where(counts > 0, season / np.maximum(counts, 1), 0.0)
    season -= season.mean()
    deseasonalised = y - season[np.arange(len(y)) % m]
    base = theta(deseasonalised, h, m)
    future_idx = (np.arange(len(y), len(y) + h)) % m
    return base + season[future_idx]


def combination(y: np.ndarray, h: int, m: int = 52) -> np.ndarray:
    """The simple average of SES, Theta and seasonal Theta.

    The M4 competition's headline finding was that combinations of simple methods beat both their
    own components and most standalone machine learning entries, so a combination is the thing to
    beat rather than an afterthought.
    """
    parts = [ses(y, h, m), theta(y, h, m), seasonal_theta(y, h, m)]
    return np.mean(np.vstack(parts), axis=0)


MODELS = {
    "naive": naive,
    "seasonal_naive": seasonal_naive,
    "drift": drift,
    "ses": ses,
    "theta": theta,
    "seasonal_theta": seasonal_theta,
    "combination": combination,
}


# ---------------------------------------------------------------------------------------------
# evaluation
# ---------------------------------------------------------------------------------------------
def mase(actual: np.ndarray, pred: np.ndarray, insample: np.ndarray, m: int) -> float:
    """Mean absolute scaled error: the model's MAE over the in-sample seasonal-naive MAE.

    Scale-free, so 20 series with wildly different pageview counts can be averaged, and it has a
    meaning rather than a range: 1.0 is exactly as good as repeating last season.
    """
    if len(insample) <= m:
        denom = np.mean(np.abs(np.diff(insample))) if len(insample) > 1 else np.nan
    else:
        denom = np.mean(np.abs(insample[m:] - insample[:-m]))
    if not np.isfinite(denom) or denom == 0:
        return float("nan")
    return float(np.mean(np.abs(actual - pred)) / denom)


@dataclass
class BacktestResult:
    series: str
    m: int
    h: int
    n_windows: int
    mase: dict[str, float] = field(default_factory=dict)
    per_window: dict[str, list[float]] = field(default_factory=dict)
    note: str = ""


def backtest(y: np.ndarray, *, m: int = 52, h: int = 8, n_windows: int = 8,
             models: dict | None = None, min_train: int | None = None) -> BacktestResult:
    """Rolling-origin evaluation: fit on everything up to t, predict the next h, step forward.

    Every window is a forecast the model made without seeing the answer. A single train/test split
    would let one lucky window carry the whole claim.
    """
    models = models or MODELS
    y = np.asarray(y, dtype=np.float64)
    min_train = min_train or max(2 * m, 2 * h)
    res = BacktestResult(series="", m=m, h=h, n_windows=0)
    if len(y) < min_train + h:
        res.note = (f"序列只有 {len(y)} 點，至少需要 {min_train + h} 點才能回測 "
                    f"(min_train={min_train}, h={h})")
        return res

    starts = np.linspace(min_train, len(y) - h, n_windows).astype(int)
    starts = sorted(set(starts.tolist()))
    scores: dict[str, list[float]] = {k: [] for k in models}
    for cut in starts:
        train, test = y[:cut], y[cut:cut + h]
        if len(test) < h:
            continue
        for name, fn in models.items():
            pred = np.asarray(fn(train, h, m), dtype=np.float64)
            scores[name].append(mase(test, pred, train, m))
    res.n_windows = len(starts)
    res.per_window = scores
    res.mase = {k: float(np.nanmean(v)) if v else float("nan") for k, v in scores.items()}
    return res


def forecast_with_interval(y: np.ndarray, *, model: str = "seasonal_theta", m: int = 52, h: int = 8,
                           level: float = 0.8, n_windows: int = 8) -> dict:
    """A forecast that arrives with its own error bar, measured rather than assumed.

    The interval is the empirical quantile of this model's backtest errors at each horizon — no
    normality assumption, and it widens honestly for a series the model handles badly.
    """
    y = np.asarray(y, dtype=np.float64)
    fn = MODELS[model]
    point = np.asarray(fn(y, h, m), dtype=np.float64)

    errs: list[np.ndarray] = []
    min_train = max(2 * m, 2 * h)
    if len(y) >= min_train + h:
        for cut in sorted(set(np.linspace(min_train, len(y) - h, n_windows).astype(int).tolist())):
            train, test = y[:cut], y[cut:cut + h]
            if len(test) == h:
                errs.append(test - np.asarray(fn(train, h, m), dtype=np.float64))
    raw = point.copy()
    if errs:
        e = np.vstack(errs)
        # the backtest's median error per horizon IS the model's bias on this series; correcting it
        # is the whole reason to run a backtest, and the size of the correction is worth showing
        bias = np.median(e, axis=0)
        point = point + bias
        centred = e - bias
        lo_q, hi_q = (1 - level) / 2, 1 - (1 - level) / 2
        lo = point + np.quantile(centred, lo_q, axis=0)
        hi = point + np.quantile(centred, hi_q, axis=0)
        coverage_n = len(errs)
    else:
        bias = np.zeros(h)
        lo = hi = np.full(h, np.nan)
        coverage_n = 0
    return {
        "model": model, "h": h, "m": m, "level": level,
        "point": [float(v) for v in point],
        "point_uncorrected": [float(v) for v in raw],
        "bias_correction": [float(v) for v in bias],
        "lower": [float(v) for v in lo], "upper": [float(v) for v in hi],
        "interval_from_n_windows": coverage_n,
        "note": ("點估計已用回測量到的中位誤差做偏誤修正（bias_correction 就是修正量，"
                 "未修正的值留在 point_uncorrected）；區間是去偏後誤差的分位數，不是常態假設。"
                 "回測視窗不足時區間會是 NaN，這時不要畫區間"),
    }
