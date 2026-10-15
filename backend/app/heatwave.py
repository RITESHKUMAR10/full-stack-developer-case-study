"""Pure heatwave-detection logic (no I/O) so it is easy to unit test.

Definition used (documented in README):
  * threshold(d) = 95th percentile of daily Tmax over the 1991-2020 baseline,
    computed per calendar day using a +/-7 day window (15 days x 30 yrs = ~450 samples/day)
  * heatwave = >= 3 consecutive days with Tmax > threshold(d)
  * a missing day breaks a run (conservative: we never invent exceedances)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config

# Reference non-leap calendar: (month, day) -> index 0..364. Feb 29 maps to Feb 28.
_REF = pd.date_range("2001-01-01", "2001-12-31")
_MD_INDEX = {(d.month, d.day): i for i, d in enumerate(_REF)}
_MD_INDEX[(2, 29)] = _MD_INDEX[(2, 28)]


def day_index(idx: pd.DatetimeIndex) -> np.ndarray:
    return np.fromiter((_MD_INDEX[(d.month, d.day)] for d in idx), dtype=int, count=len(idx))


def clean_series(start: str, values: list) -> tuple[pd.Series, dict]:
    """Daily series on a complete date index. Bad / implausible values become NaN."""
    arr = pd.to_numeric(pd.Series(values, dtype="object"), errors="coerce").to_numpy(dtype=float)
    s = pd.Series(arr, index=pd.date_range(start, periods=len(arr), freq="D"))
    lo, hi = config.VALID_TMAX_RANGE
    bad = ((s < lo) | (s > hi)) & s.notna()
    s[bad] = np.nan
    info = {
        "days_total": int(len(s)),
        "days_missing": int(s.isna().sum()),
        "days_outlier_removed": int(bad.sum()),
    }
    return s, info


def percentile_thresholds(series: pd.Series, base_start: int, base_end: int,
                          pct: float = config.PERCENTILE, window: int = config.WINDOW_DAYS) -> np.ndarray:
    """365 per-calendar-day thresholds from the baseline period (NaN where too little data)."""
    base = series[(series.index.year >= base_start) & (series.index.year <= base_end)]
    base = base[~((base.index.month == 2) & (base.index.day == 29))]
    years = list(base.index.year.unique())
    mat = np.full((len(years), 365), np.nan)
    yidx = {y: i for i, y in enumerate(years)}
    di = day_index(base.index)
    for y, d, v in zip(base.index.year, di, base.to_numpy()):
        mat[yidx[y], d] = v
    half = window // 2
    thr = np.full(365, np.nan)
    for d in range(365):
        cols = [(d + k) % 365 for k in range(-half, half + 1)]
        vals = mat[:, cols].ravel()
        vals = vals[~np.isnan(vals)]
        if len(vals) >= 0.5 * len(years) * window:  # need >=50% of the expected samples
            thr[d] = np.percentile(vals, pct)
    return thr


def hot_season_mask(series: pd.Series, base_start: int, base_end: int,
                     fraction: float = config.HOT_SEASON_FRACTION) -> np.ndarray:
    """Boolean[365]: the warmest `fraction` of calendar days (by smoothed baseline mean Tmax).

    Data-driven so it works in either hemisphere (Delhi ~ Apr-Aug, Sydney ~ Nov-Mar)."""
    base = series[(series.index.year >= base_start) & (series.index.year <= base_end)]
    base = base[~((base.index.month == 2) & (base.index.day == 29))]
    di = day_index(base.index)
    sums, counts = np.zeros(365), np.zeros(365)
    ok = ~np.isnan(base.to_numpy())
    np.add.at(sums, di[ok], base.to_numpy()[ok])
    np.add.at(counts, di[ok], 1)
    clim = np.where(counts > 0, sums / np.maximum(counts, 1), np.nan)
    if np.isnan(clim).all():
        return np.ones(365, dtype=bool)
    clim = np.where(np.isnan(clim), np.nanmean(clim), clim)
    k = 15  # circular +/-15 day smoothing
    smooth = np.array([clim[[(d + j) % 365 for j in range(-k, k + 1)]].mean() for d in range(365)])
    cutoff = np.quantile(smooth, 1 - fraction)
    return smooth >= cutoff


def season_months(mask365: np.ndarray) -> list[int]:
    """Months (1-12) in which at least half the days belong to the mask (for display)."""
    out = []
    for m in range(1, 13):
        idx = [_MD_INDEX[(m, d)] for d in range(1, 29)]
        if mask365[idx].mean() >= 0.5:
            out.append(m)
    return out


def detect_events(series: pd.Series, thr365: np.ndarray, min_days: int = config.MIN_EVENT_DAYS,
                  mask365: np.ndarray | None = None) -> list[dict]:
    di = day_index(series.index)
    thr = thr365[di]
    vals = series.to_numpy()
    with np.errstate(invalid="ignore"):
        exceed = vals > thr  # NaN compares False -> breaks runs
    if mask365 is not None:
        exceed = exceed & mask365[di]  # only days inside the hot season can be part of an event
    events, i, n = [], 0, len(exceed)
    while i < n:
        if not exceed[i]:
            i += 1
            continue
        j = i
        while j < n and exceed[j]:
            j += 1
        if j - i >= min_days:
            excess = vals[i:j] - thr[i:j]
            events.append({
                "start": series.index[i].strftime("%Y-%m-%d"),
                "end": series.index[j - 1].strftime("%Y-%m-%d"),
                "year": int(series.index[i].year),
                "duration": int(j - i),
                "peak_tmax": round(float(vals[i:j].max()), 1),
                "mean_excess": round(float(excess.mean()), 2),
            })
        i = j
    return events


def yearly_metrics(series: pd.Series, events: list[dict], start_year: int, end_year: int) -> list[dict]:
    rows = []
    for y in range(start_year, end_year + 1):
        ys = series[series.index.year == y]
        n_days = len(ys)
        coverage = float(ys.notna().sum() / n_days) if n_days else 0.0
        ev = [e for e in events if e["year"] == y]
        durs = [e["duration"] for e in ev]
        rows.append({
            "year": y,
            "coverage": round(coverage, 3),
            "valid": coverage >= config.MIN_COVERAGE,
            "events": len(ev),
            "heatwave_days": int(sum(durs)),
            "max_duration": int(max(durs)) if durs else 0,
            "mean_duration": round(float(np.mean(durs)), 2) if durs else 0.0,
            "mean_excess": round(float(np.mean([e["mean_excess"] for e in ev])), 2) if ev else 0.0,
            "max_tmax": round(float(ys.max()), 1) if ys.notna().any() else None,
        })
    return rows
