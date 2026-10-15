"""Central configuration. Everything is overridable through environment variables."""
import os
from datetime import date

from dotenv import load_dotenv

load_dotenv()  # reads backend/.env if present; real env vars still take precedence

MONGODB_URI = os.getenv("MONGODB_URI", "mongomock://local")  # mongomock = in-memory dev DB
MONGODB_DB = os.getenv("MONGODB_DB", "climate_hazards")
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
RATE_LIMIT = os.getenv("RATE_LIMIT", "20/minute")

OPEN_METEO_URL = "https://archive-api.open-meteo.com/v1/archive"
HTTP_TIMEOUT_S = 40
HTTP_RETRIES = 3

# Climatological baseline used for the percentile threshold (WMO standard normal period).
BASELINE_START = 1991
BASELINE_END = 2020
PERCENTILE = 95
WINDOW_DAYS = 15          # centred window around each calendar day (ETCCDI-style)
MIN_EVENT_DAYS = 3
HOT_SEASON_FRACTION = 1 / 3   # 'hot season' = warmest third of the calendar (hemisphere-independent)
MIN_YEAR = 1950
MAX_SPAN_YEARS = 80
MIN_COVERAGE = 0.90       # a year with <90% valid days is excluded from trend stats
VALID_TMAX_RANGE = (-90.0, 60.0)  # physically plausible bounds in deg C
GRID_STEP = 0.25          # cache key resolution (deg); Open-Meteo/ERA5 grid is ~0.25
ANALYSIS_VERSION = 3        # bump when detection/insight logic changes: old cached analyses are then ignored
ANALYSIS_TTL_S = 30 * 24 * 3600
MAX_BOX_DEG = 5.0         # largest accepted lat/lon box side


def last_complete_year() -> int:
    return date.today().year - 1
