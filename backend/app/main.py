"""FastAPI app: validated inputs, rate limiting, CORS allow-list, DB-backed responses."""
from __future__ import annotations

import logging
from typing import Literal, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from . import config, exports, service
from .locations import LOCATIONS
from pymongo.errors import PyMongoError

from .openmeteo import UpstreamError

log = logging.getLogger("hazards")
limiter = Limiter(key_func=get_remote_address, default_limits=[config.RATE_LIMIT])
app = FastAPI(title="Climate Hazard Trend Analyzer", version="1.0.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["GET"], allow_headers=["*"])


class Query_:
    """Validated query params shared by the analysis + export endpoints."""

    def __init__(
        self,
        lat: Optional[float] = Query(None, ge=-90, le=90),
        lon: Optional[float] = Query(None, ge=-180, le=180),
        south: Optional[float] = Query(None, ge=-90, le=90),
        north: Optional[float] = Query(None, ge=-90, le=90),
        west: Optional[float] = Query(None, ge=-180, le=180),
        east: Optional[float] = Query(None, ge=-180, le=180),
        start_year: int = Query(1990),
        end_year: int = Query(2020),
        hazard: Literal["heatwave"] = "heatwave",
        season: Literal["hot", "all"] = "hot",
        name: str = Query("", max_length=80),
    ):
        box = (south, north, west, east)
        if all(v is not None for v in box):
            if south >= north or west >= east:
                raise HTTPException(422, "Invalid box: need south<north and west<east.")
            if (north - south) > config.MAX_BOX_DEG or (east - west) > config.MAX_BOX_DEG:
                raise HTTPException(422, f"Box too large (max {config.MAX_BOX_DEG} degrees per side).")
            lat, lon = (south + north) / 2, (west + east) / 2
        elif any(v is not None for v in box):
            raise HTTPException(422, "Provide all of south, north, west, east, or use lat/lon.")
        if lat is None or lon is None:
            raise HTTPException(422, "Provide lat & lon, or a south/north/west/east box.")
        last = config.last_complete_year()
        if not (config.MIN_YEAR <= start_year <= end_year <= last):
            raise HTTPException(422, f"Years must satisfy {config.MIN_YEAR} <= start <= end <= {last}.")
        if end_year - start_year + 1 < 8:
            raise HTTPException(422, "Time range must span at least 8 years for a meaningful trend.")
        if end_year - start_year + 1 > config.MAX_SPAN_YEARS:
            raise HTTPException(422, f"Time range too long (max {config.MAX_SPAN_YEARS} years).")
        self.lat, self.lon, self.start_year, self.end_year, self.season = lat, lon, start_year, end_year, season
        # keep only printable, non-markup characters from the free-text label
        self.name = "".join(c for c in name if c.isalnum() or c in " ,.-()'").strip()


def _analysis(q: Query_) -> dict:
    try:
        return service.get_analysis(q.lat, q.lon, q.start_year, q.end_year, q.name, q.season)
    except UpstreamError as e:
        log.warning("upstream failure: %s", e)
        raise HTTPException(502, "Weather data provider is unavailable, please retry shortly.")


@app.exception_handler(PyMongoError)
async def mongo_error(_request: Request, exc: PyMongoError):
    log.error("database error: %s", type(exc).__name__)
    return JSONResponse({"detail": "Database temporarily unavailable, please retry shortly."}, status_code=503)


@app.get("/", include_in_schema=False)
def root():
    return {"service": "Climate Hazard Trend Analyzer API", "docs": "/docs", "health": "/api/health"}


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/locations")
def locations():
    return {"locations": LOCATIONS, "max_year": config.last_complete_year(), "min_year": config.MIN_YEAR}


@app.get("/api/analysis")
@limiter.limit(config.RATE_LIMIT)
def analysis(request: Request, q: Query_ = Depends()):
    return _analysis(q)


@app.get("/api/analysis/export.csv")
@limiter.limit(config.RATE_LIMIT)
def export_csv(request: Request, q: Query_ = Depends()):
    body = exports.to_csv(_analysis(q))
    return Response(body, media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="heatwave_analysis.csv"'})


@app.get("/api/analysis/export.pdf")
@limiter.limit(config.RATE_LIMIT)
def export_pdf(request: Request, q: Query_ = Depends()):
    body = exports.to_pdf(_analysis(q))
    return Response(body, media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="heatwave_report.pdf"'})
