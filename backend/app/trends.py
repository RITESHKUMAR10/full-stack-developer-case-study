"""Trend statistics: Mann-Kendall + Theil-Sen, rolling means, honest plain-language insight."""
from __future__ import annotations

import numpy as np
import pymannkendall as mk


def rolling_mean(values: list, window: int = 5) -> list:
    out = []
    for i in range(len(values)):
        chunk = [v for v in values[max(0, i - window + 1): i + 1] if v is not None]
        out.append(round(float(np.mean(chunk)), 2) if len(chunk) >= max(2, window // 2 + 1) else None)
    return out


def mann_kendall(values: list) -> dict | None:
    if len(values) < 8:
        return None
    arr = np.asarray(values, dtype=float)
    r = mk.original_test(arr)
    linear = float(np.polyfit(np.arange(len(arr)), arr, 1)[0]) * 10
    return {
        "linear_slope_per_decade": round(linear, 3),
        "trend": r.trend,  # increasing / decreasing / no trend
        "p_value": round(float(r.p), 4),
        "significant": bool(r.p < 0.05),
        "tau": round(float(r.Tau), 3),
        "sen_slope_per_decade": round(float(r.slope) * 10, 3),
        "n_years": len(values),
    }


def build_insight(rows: list, mk_days: dict | None, mk_events: dict | None, place: str) -> dict:
    """Compare early vs late period means and attach significance; never overstate."""
    valid = [r for r in rows if r["valid"]]
    if len(valid) < 8 or mk_days is None:
        return {"headline": f"Not enough valid years ({len(valid)}) in {place} to estimate a trend.",
                "detail": "Choose a longer time range (at least 8-10 years).",
                "confidence": "none", "pct_change": None}
    k = max(3, min(10, len(valid) // 3))
    early, late = valid[:k], valid[-k:]
    e = float(np.mean([r["heatwave_days"] for r in early]))
    l = float(np.mean([r["heatwave_days"] for r in late]))
    # A percentage off a tiny base (e.g. 0.3 -> 3.0 days = "+900%") is misleading: report absolute numbers instead.
    pct = None if e < 1.0 else (l - e) / e * 100.0
    span = f"{early[0]['year']}-{early[-1]['year']} vs {late[0]['year']}-{late[-1]['year']}"
    if pct is None:
        change = (f"{'rose' if l > e else 'fell' if l < e else 'stayed'} from {e:.1f} to {l:.1f} heatwave days/year "
                  f"(very low starting level, so no % change is quoted)")
    else:
        change = (f"{'increased' if pct >= 0 else 'decreased'} by {abs(pct):.0f}% "
                  f"({e:.1f} -> {l:.1f} heatwave days/year)")
    y0, y1 = early[0]["year"], late[-1]["year"]
    sig = mk_days["significant"]
    if sig:
        headline = f"Heatwave days in {place} {change} between {y0} and {y1}."
        conf = f"statistically significant (Mann-Kendall p={mk_days['p_value']:.3f})"
    else:
        headline = (f"Heatwave days in {place} {change} between {y0} and {y1}, "
                    f"but the trend is not statistically significant.")
        conf = f"not statistically significant (Mann-Kendall p={mk_days['p_value']:.3f})"
    detail = (f"Compared {span}. Linear trend: {mk_days['linear_slope_per_decade']:+.2f} heatwave days per decade "
              f"(Theil-Sen median slope: {mk_days['sen_slope_per_decade']:+.2f}, which is 0 when most years have no heatwave); "
              f"{conf}. Event-frequency trend: {mk_events['trend'] if mk_events else 'n/a'}. "
              f"Based on one reanalysis grid cell; interpret with caution.")
    if (l - e) * mk_days["linear_slope_per_decade"] < 0:
        detail += (" Note: the early-vs-late comparison and the linear fit point in opposite directions, "
                   "which happens when yearly counts are noisy; treat the change as inconclusive.")
    return {"headline": headline, "detail": detail,
            "confidence": "significant" if sig else "not_significant",
            "pct_change": None if pct is None else round(pct, 1)}
