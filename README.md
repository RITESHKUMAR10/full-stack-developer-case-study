# Climate Hazard Trend Analyzer (Heatwaves)

Full-stack case study for Dygnify Ventures. Pick a region and a time range, and the app shows whether
heatwaves became more frequent, longer or more intense, with statistical significance.

- **Frontend:** React + Vite, Chart.js (charts), Leaflet (map region picker)
- **Backend:** Python FastAPI
- **Database:** MongoDB (Atlas in production, in-memory `mongomock` for local dev and tests)
- **Data:** Open-Meteo Historical Weather API (ERA5 reanalysis), daily `temperature_2m_max`

- **Live app:** https://full-stack-developer-case-study.vercel.app
- **API:** https://climate-hazard-api-uku6.onrender.com (interactive docs at `/docs`)
- **Demo video:** _add link_

The API runs on Render's free tier, so the first request after an idle period can take ~50 s while the service wakes up.

## Setup

```bash
# backend
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # optional: set MONGODB_URI (Atlas)
uvicorn app.main:app --reload --port 8000
python -m pytest -q                                    # 11 tests, no network or database needed

# frontend (new terminal)
cd frontend
npm install
npm run dev                                            # http://localhost:5173 (proxies /api to :8000)
```

Without `MONGODB_URI` the backend uses an in-memory DB (cache is lost on restart). For production set
`MONGODB_URI` and `CORS_ORIGINS` on the backend, and `VITE_API_URL` (backend origin) on the frontend build.

### Deploy (as deployed)
- **Backend → Render** (Blueprint from `render.yaml`, free plan). Env: `MONGODB_URI` (MongoDB Atlas M0),
  `CORS_ORIGINS=https://full-stack-developer-case-study.vercel.app` (comma-separate to also allow `http://localhost:5173`).
- **Frontend → Vercel:** root `frontend`, preset Vite, build `npm run build`, output `dist`, env `VITE_API_URL=https://climate-hazard-api-uku6.onrender.com`.
  `VITE_*` variables are baked in at build time, so redeploy after changing them.
- Atlas Network Access allows `0.0.0.0/0` because Render's free tier has no fixed outbound IP.

## Architecture

```
React (Vite) ──GET /api/analysis──▶ FastAPI ──▶ MongoDB  analyses (computed results, 30-day TTL)
   Chart.js, Leaflet                    │  miss          raw_series (daily Tmax per 0.25° grid cell)
                                        └──▶ Open-Meteo archive API (only on cache miss)
```

1. Request is validated (ranges, box size, `hazard` enum) and rate limited.
2. The location is snapped to a 0.25° grid cell (the ERA5 resolution), which is also the cache key, so nearby clicks share data.
3. **Ingest:** if the raw daily series for that cell is not in `raw_series`, fetch it once (baseline 1991–2020 ∪ requested range) with timeout and retries, and store it.
4. **Analyse:** clean → thresholds → detect events → yearly metrics → trend tests; the result is stored in `analyses`.
5. The API response is always read back from MongoDB. Repeat requests never touch the upstream API.

### Endpoints
| Endpoint | Purpose |
|---|---|
| `GET /api/analysis?lat&lon` or `&south&north&west&east`, `start_year`, `end_year`, `hazard=heatwave`, `season=hot\|all`, `name` | JSON summary, yearly series, events, trends, insight |
| `GET /api/analysis/export.csv` / `export.pdf` | Same params; downloadable report |
| `GET /api/locations` | Preset cities/states and valid year bounds |
| `GET /api/health` | Liveness |

## Hazard logic (heatwave)

- **Threshold:** for each calendar day, the **95th percentile of daily Tmax over the 1991–2020 baseline**, pooled over a
  ±7-day window (about 450 samples per day), so thresholds are smooth and seasonally aware. Feb 29 uses Feb 28's threshold.
- **Event:** **≥ 3 consecutive days** with Tmax above that day's threshold.
- **Season (default `hot`):** only days in the region's **hottest third of the calendar** can be part of an event. The hot season is derived from the
  baseline climatology, so it is hemisphere-independent (Delhi → Apr–Jul, London → Jun–Sep, Sydney → Dec–Mar). Without this,
  a per-calendar-day percentile also flags warm *winter* spells (for Delhi, 11 of 60 events fell in January). `season=all` restores the plain, year-round version.
- **Metrics per year:** events, heatwave days, longest event, mean duration, mean excess over threshold (intensity), peak Tmax.
  An event is assigned to the year it starts in.
- **Trend:** Mann-Kendall test and Theil-Sen slope (per decade) on yearly heatwave days and events, plus a 5-year rolling mean for the chart.
- **Insight:** compares the mean of the first and last ~10 valid years, and says explicitly when the trend is **not statistically significant** (p ≥ 0.05).

## Data handling
- Missing values (`null`) stay missing and **break a run**; we never interpolate exceedances.
- Values outside −90…60 °C are treated as sensor outliers and dropped (counted in the response).
- Years with < 90 % valid days are excluded from trend statistics and flagged.
- Units are fixed to °C in the request. The series is rebuilt on a complete daily index so gaps are explicit.
- Data-quality counts are shown in the UI.

## Security & performance
- All inputs are typed and range-checked (lat/lon, years 1950…last complete year, 8–80 year span, box ≤ 5° per side, `hazard` enum).
  Only numbers reach the upstream URL (no user-controlled hosts/paths); the free-text `name` is stripped to a safe character set.
- Per-IP rate limiting (`slowapi`, default 20/min; the Render start command trusts proxy headers so real client IPs are used); CORS allow-list, GET only; CSV export neutralises formula injection; PDF text is XML-escaped.
- Two-level cache in MongoDB (raw series + computed analysis), per-cell lock to avoid duplicate upstream calls, upstream timeouts/retries with a clean 502 on failure and a clean 503 if MongoDB is unreachable.
- Mongo queries only use server-built keys, never raw user input.

## Assumptions and limitations
- A lat-lon **box analyses its centre point** (max 5° per side); a state is represented by its centroid. Area-averaging or
  polygon masks would be more faithful.
- ERA5 is a ~25 km reanalysis, so urban heat island effects and local extremes are smoothed. Absolute temperatures can differ from station data.
- By default only the hot third of the year is analysed (see above); the UI has a *Season* switch for all-year analysis. The one-third
  cut-off is a judgement call (`HOT_SEASON_FRACTION` in `config.py`).
- Headlines quote a % change only when the starting level is at least 1 heatwave day/year; otherwise absolute numbers are shown, to avoid "+900%" claims from tiny bases.
- The 1991–2020 baseline is fixed, so earlier years are compared against a warmer reference; the trend is therefore about
  "how often the modern 95th-percentile is exceeded". It is not a fixed physical temperature.
- Mann-Kendall assumes serially independent years; no autocorrelation correction is applied. Results for 30 years of data from a
  single cell can legitimately be "no significant trend", and the app reports that rather than forcing a story.
- Years must be complete calendar years (up to last year).

## What I would improve with more time
- Area-averaged boxes / polygon regions and a geocoder for any city name.
- Hamed-Rao autocorrelation-corrected Mann-Kendall, and station-data cross-checks (NOAA GHCN).
- Heat-index/humidity or Tmin-based (warm night) definitions, and a data-driven (not fixed one-third) hot-season cut-off.
- Redis for shared rate limiting across instances, background ingestion jobs, frontend tests (Vitest/Playwright), CI.
- Drought and heavy-rainfall hazards behind the same pipeline (`hazard` is already an enum in the API).

## AI tools used
- **Claude Code (Claude Sonnet)**, used as a pair-programmer. It scaffolded the FastAPI backend, heatwave detection,
  trend/insight code, tests, React UI and a first draft of this README.
- **What I did myself:** chose the hazard definition and its parameters (95th percentile, 3+ days, 1991-2020 baseline),
  reviewed the detection and trend logic, ran the tests, checked results against live Open-Meteo data, debugged
  integration problems (for example, a stale backend returning a different response shape than the frontend expected),
  and handled the MongoDB Atlas and Render deployment.
- I can walk through and modify any part of the code in the interview.
