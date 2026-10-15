"""Ingest -> analyse -> store -> read pipeline."""
from __future__ import annotations

import threading
from collections import defaultdict
from datetime import datetime, timezone

from . import config, db, heatwave, openmeteo, trends

_locks: dict = defaultdict(threading.Lock)


def grid_key(lat: float, lon: float) -> tuple[str, float, float]:
    s = config.GRID_STEP
    glat, glon = round(round(lat / s) * s, 4), round(round(lon / s) * s, 4)
    return f"{glat:.2f}_{glon:.2f}", glat, glon


def _ensure_raw(key: str, glat: float, glon: float, need_start: int, need_end: int) -> dict:
    """Return cached raw series covering [need_start, need_end]; fetch (and cache) if missing."""
    col = db.get_db().raw_series
    doc = col.find_one({"key": key})
    if doc and doc["start_year"] <= need_start and doc["end_year"] >= need_end:
        return doc
    start = min(need_start, doc["start_year"]) if doc else need_start
    end = max(need_end, doc["end_year"]) if doc else need_end
    first, values = openmeteo.fetch_daily_tmax(glat, glon, start, end)
    doc = {"key": key, "lat": glat, "lon": glon, "start_year": start, "end_year": end,
           "first_date": first, "tmax": values, "fetched_at": datetime.now(timezone.utc)}
    col.replace_one({"key": key}, doc, upsert=True)
    return doc


def ingest_and_analyse(lat: float, lon: float, start_year: int, end_year: int, place: str, season: str = "hot") -> dict:
    key, glat, glon = grid_key(lat, lon)
    analysis_id = f"v{config.ANALYSIS_VERSION}|{key}|{start_year}|{end_year}|{season}"
    with _locks[key]:  # avoid duplicate upstream fetches for the same cell
        raw = _ensure_raw(key, glat, glon,
                          min(start_year, config.BASELINE_START), max(end_year, config.BASELINE_END))
        series, quality = heatwave.clean_series(raw["first_date"], raw["tmax"])
        thr = heatwave.percentile_thresholds(series, config.BASELINE_START, config.BASELINE_END)
        window = series[(series.index.year >= start_year) & (series.index.year <= end_year)]
        mask = heatwave.hot_season_mask(series, config.BASELINE_START, config.BASELINE_END) if season == "hot" else None
        events = heatwave.detect_events(window, thr, mask365=mask)
        rows = heatwave.yearly_metrics(window, events, start_year, end_year)
        v = [r for r in rows if r["valid"]]
        mk_days = trends.mann_kendall([r["heatwave_days"] for r in v])
        mk_events = trends.mann_kendall([r["events"] for r in v])
        mk_excess = trends.mann_kendall([r["max_duration"] for r in v])
        days_series = [r["heatwave_days"] if r["valid"] else None for r in rows]
        for r, rm in zip(rows, trends.rolling_mean(days_series, 5)):
            r["heatwave_days_rolling5"] = rm
        doc = {
            "_id": analysis_id, "key": key, "hazard": "heatwave",
            "location": {"lat": glat, "lon": glon, "requested_lat": lat, "requested_lon": lon, "name": place},
            "range": {"start_year": start_year, "end_year": end_year},
            "definition": {
                "metric": "Tmax (2 m, daily, deg C)", "percentile": config.PERCENTILE,
                "baseline": [config.BASELINE_START, config.BASELINE_END],
                "window_days": config.WINDOW_DAYS, "min_consecutive_days": config.MIN_EVENT_DAYS,
                "source": "Open-Meteo Historical Weather API (ERA5 reanalysis)",
                "season": season,
                "season_months": heatwave.season_months(mask) if mask is not None else list(range(1, 13)),
            },
            "quality": {**quality,
                        "years_excluded": [r["year"] for r in rows if not r["valid"]],
                        "missing_pct": round(100 * quality["days_missing"] / max(1, quality["days_total"]), 2)},
            "thresholds_by_day": [None if x != x else round(float(x), 1) for x in thr],
            "yearly": rows,
            "events": sorted(events, key=lambda e: -e["duration"])[:200],
            "trends": {"heatwave_days": mk_days, "events": mk_events, "max_duration": mk_excess},
            "insight": trends.build_insight(rows, mk_days, mk_events, "this region"),
            "computed_at": datetime.now(timezone.utc),
        }
        db.get_db().analyses.replace_one({"_id": analysis_id}, doc, upsert=True)
    return doc


def get_analysis(lat: float, lon: float, start_year: int, end_year: int, place: str, season: str = "hot") -> dict:
    """Read from DB; compute + store only when missing. Always returns the stored document."""
    key, _, _ = grid_key(lat, lon)
    analysis_id = f"v{config.ANALYSIS_VERSION}|{key}|{start_year}|{end_year}|{season}"
    doc = db.get_db().analyses.find_one({"_id": analysis_id})
    cached = doc is not None
    if not cached:
        ingest_and_analyse(lat, lon, start_year, end_year, place, season)
        doc = db.get_db().analyses.find_one({"_id": analysis_id})
    doc["location"]["name"] = place or doc["location"].get("name")
    if place:
        doc["insight"]["headline"] = doc["insight"]["headline"].replace("this region", place)
    doc["cached"] = cached
    doc.pop("_id", None)
    doc["computed_at"] = doc["computed_at"].isoformat() if hasattr(doc["computed_at"], "isoformat") else str(doc["computed_at"])
    return doc
