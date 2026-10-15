import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import config, db, heatwave, openmeteo


def synthetic(start_year=1980, end_year=2023, warming=0.04, seed=0):
    """Seasonal Tmax + noise + linear warming; includes gaps and an outlier."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(f"{start_year}-01-01", f"{end_year}-12-31")
    doy = idx.dayofyear.to_numpy()
    yrs = (idx.year - start_year).to_numpy()
    phi = 0.7                                              # day-to-day persistence, like real weather
    e = rng.normal(0, 2.5 * np.sqrt(1 - phi ** 2), len(idx))
    noise = np.empty(len(idx))
    noise[0] = e[0]
    for i in range(1, len(idx)):
        noise[i] = phi * noise[i - 1] + e[i]
    v = 25 + 8 * np.sin((doy - 100) / 365 * 2 * np.pi) + noise + warming * yrs
    v = v.astype(object)
    v[100:104] = None            # gap
    v[500] = 999.0               # sensor outlier
    return idx[0].strftime("%Y-%m-%d"), list(v)


@pytest.fixture()
def client(monkeypatch):
    db.reset_for_tests()
    calls = {"n": 0}

    def fake(lat, lon, s, e):
        calls["n"] += 1
        first, vals = synthetic(min(s, 1980), e)
        return first, vals

    monkeypatch.setattr(openmeteo, "fetch_daily_tmax", fake)
    from app.main import app
    c = TestClient(app)
    c.calls = calls
    return c


def test_clean_series_removes_outlier_and_flags_gap():
    first, vals = synthetic()
    s, info = heatwave.clean_series(first, vals)
    assert info["days_outlier_removed"] == 1
    assert info["days_missing"] >= 5


def test_detect_requires_three_consecutive_days():
    idx = pd.date_range("2000-01-01", "2000-01-10")
    s = pd.Series([10, 10, 30, 30, 10, 30, 30, 30, 10, 10], index=idx, dtype=float)
    thr = np.full(365, 20.0)
    ev = heatwave.detect_events(s, thr)
    assert len(ev) == 1 and ev[0]["duration"] == 3 and ev[0]["start"] == "2000-01-06"


def test_nan_breaks_a_run():
    idx = pd.date_range("2000-01-01", "2000-01-05")
    s = pd.Series([30, 30, np.nan, 30, 30], index=idx, dtype=float)
    assert heatwave.detect_events(s, np.full(365, 20.0)) == []


def test_thresholds_are_about_p95():
    first, vals = synthetic()
    s, _ = heatwave.clean_series(first, vals)
    thr = heatwave.percentile_thresholds(s, 1991, 2020)
    base = s[(s.index.year >= 1991) & (s.index.year <= 2020)]
    frac = (base.to_numpy() > thr[heatwave.day_index(base.index)]).mean()
    assert 0.03 < frac < 0.07


def test_analysis_detects_increase_and_caches(client):
    p = dict(lat=28.61, lon=77.21, start_year=1985, end_year=2020, name="Delhi")
    r1 = client.get("/api/analysis", params=p).json()
    r2 = client.get("/api/analysis", params=p).json()
    assert r1["cached"] is False and r2["cached"] is True
    assert client.calls["n"] == 1                       # second call served from MongoDB
    assert r1["trends"]["heatwave_days"]["trend"] == "increasing"
    pc = r1["insight"]["pct_change"]
    assert pc is None or pc > 0   # None when the early period had zero heatwave days
    assert "heatwave days" in r1["insight"]["headline"]
    assert r1["quality"]["days_outlier_removed"] == 1
    assert r1["trends"]["heatwave_days"]["linear_slope_per_decade"] > 0


def test_validation_and_box(client):
    assert client.get("/api/analysis", params=dict(lat=95, lon=0)).status_code == 422
    assert client.get("/api/analysis", params=dict(lat=10, lon=10, start_year=2000, end_year=2003)).status_code == 422
    assert client.get("/api/analysis", params=dict(lat=10, lon=10, hazard="flood")).status_code == 422
    big = dict(south=0, north=20, west=0, east=20)
    assert client.get("/api/analysis", params=big).status_code == 422
    ok = dict(south=28, north=29, west=77, east=78, start_year=1990, end_year=2020)
    assert client.get("/api/analysis", params=ok).status_code == 200


def test_exports(client):
    p = dict(lat=28.61, lon=77.21, start_year=1990, end_year=2020, name="=cmd")
    assert client.get("/api/analysis/export.csv", params=p).text.startswith("# Heatwave")
    pdf = client.get("/api/analysis/export.pdf", params=p)
    assert pdf.content[:4] == b"%PDF"


def test_hot_season_mask_is_warmest_third_and_northern_pattern():
    first, vals = synthetic()
    s, _ = heatwave.clean_series(first, vals)
    mask = heatwave.hot_season_mask(s, 1991, 2020)
    assert 110 <= mask.sum() <= 130                      # ~1/3 of the year
    months = heatwave.season_months(mask)
    assert 7 in months and 1 not in months                # synthetic peak is mid-year


def test_hot_season_excludes_off_season_events_but_all_year_keeps_them():
    idx = pd.date_range("2000-01-01", "2000-12-31")
    s = pd.Series(10.0, index=idx)
    s["2000-01-10":"2000-01-14"] = 30.0                   # warm spell in winter
    s["2000-07-10":"2000-07-14"] = 45.0                   # warm spell in summer
    thr = np.full(365, 20.0)
    mask = np.zeros(365, dtype=bool)
    mask[heatwave.day_index(pd.date_range("2001-05-01", "2001-09-30"))] = True
    assert len(heatwave.detect_events(s, thr)) == 2
    ev = heatwave.detect_events(s, thr, mask365=mask)
    assert len(ev) == 1 and ev[0]["start"] == "2000-07-10"


def test_season_param_changes_result_and_cache_key(client):
    p = dict(lat=28.61, lon=77.21, start_year=1985, end_year=2020)
    hot = client.get("/api/analysis", params={**p, "season": "hot"}).json()
    allyr = client.get("/api/analysis", params={**p, "season": "all"}).json()
    assert hot["definition"]["season"] == "hot" and allyr["definition"]["season"] == "all"
    assert len(allyr["definition"]["season_months"]) == 12
    assert sum(r["heatwave_days"] for r in hot["yearly"]) <= sum(r["heatwave_days"] for r in allyr["yearly"])
    assert client.get("/api/analysis", params={**p, "season": "winter"}).status_code == 422


def test_database_failure_returns_503_not_500(client, monkeypatch):
    from pymongo.errors import ServerSelectionTimeoutError
    from app import service

    def boom(*a, **k):
        raise ServerSelectionTimeoutError("down")

    monkeypatch.setattr(service, "get_analysis", boom)
    r = client.get("/api/analysis", params=dict(lat=1, lon=1, start_year=1990, end_year=2020))
    assert r.status_code == 503 and "Database" in r.json()["detail"]
