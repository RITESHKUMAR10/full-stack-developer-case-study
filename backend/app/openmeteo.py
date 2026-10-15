"""Open-Meteo historical archive client. Only numeric, validated params ever reach the URL."""
from __future__ import annotations

import time

import httpx

from . import config


class UpstreamError(RuntimeError):
    pass


def fetch_daily_tmax(lat: float, lon: float, start_year: int, end_year: int) -> tuple[str, list]:
    """Return (first_date_iso, values) for a contiguous daily Tmax (deg C) series."""
    params = {
        "latitude": f"{lat:.4f}", "longitude": f"{lon:.4f}",
        "start_date": f"{start_year}-01-01", "end_date": f"{end_year}-12-31",
        "daily": "temperature_2m_max", "timezone": "UTC", "temperature_unit": "celsius",
    }
    last = None
    for attempt in range(config.HTTP_RETRIES):
        try:
            r = httpx.get(config.OPEN_METEO_URL, params=params, timeout=config.HTTP_TIMEOUT_S)
            if r.status_code == 429 or r.status_code >= 500:
                raise UpstreamError(f"upstream status {r.status_code}")
            r.raise_for_status()
            daily = r.json()["daily"]
            times, vals = daily["time"], daily["temperature_2m_max"]
            if not times or len(times) != len(vals):
                raise UpstreamError("malformed upstream payload")
            return times[0], vals
        except (httpx.HTTPError, KeyError, ValueError, UpstreamError) as e:
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise UpstreamError(f"Open-Meteo unavailable: {last}")
