import { useEffect, useRef, useState } from "react";
import { buildQuery, exportUrl, fetchAnalysis, fetchLocations } from "./api";
import { FrequencyChart, IntensityChart, ThresholdChart } from "./Charts";
import MapPicker from "./MapPicker";

const wrapLon = (x) => ((((x + 180) % 360) + 360) % 360) - 180;
const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DEFAULT = { id: "delhi", name: "Delhi, India", lat: 28.61, lon: 77.21 };

export default function App() {
  const [locations, setLocations] = useState([]);
  const [bounds, setBounds] = useState({ min: 1950, max: 2024 });
  const [region, setRegion] = useState(DEFAULT);
  const [mode, setMode] = useState("preset"); // preset | point | box
  const [startYear, setStartYear] = useState(1990);
  const [endYear, setEndYear] = useState(2020);
  const [season, setSeason] = useState("hot");
  const [data, setData] = useState(null);
  const [qs, setQs] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const abort = useRef(null);

  useEffect(() => {
    fetchLocations().then((r) => {
      setLocations(r.locations);
      setBounds({ min: r.min_year, max: r.max_year });
      setEndYear((y) => Math.min(y, r.max_year));
    }).catch(() => setError("Cannot reach the API. Is the backend running?"));
  }, []);

  async function analyse(r = region) {
    setError("");
    const sy = Number(startYear), ey = Number(endYear);
    if (!(sy <= ey) || sy < bounds.min || ey > bounds.max) return setError(`Choose years between ${bounds.min} and ${bounds.max}, start before end.`);
    if (ey - sy + 1 < 8) return setError("Select at least 8 years for a meaningful trend.");
    abort.current?.abort();
    abort.current = new AbortController();
    const q = buildQuery(r, sy, ey, season);
    setLoading(true);
    try {
      setData(await fetchAnalysis(q, abort.current.signal));
      setQs(q);
    } catch (e) {
      if (e.name !== "AbortError") setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { analyse(); /* initial load */ }, []); // eslint-disable-line

  const pickPreset = (id) => {
    const l = locations.find((x) => x.id === id);
    if (l) setRegion({ id: l.id, name: l.name, lat: l.lat, lon: l.lon });
  };
  const setPoint = (lat, lon) => setRegion({ name: "Custom point", lat: +lat.toFixed(4), lon: +wrapLon(lon).toFixed(4) });
  const setBox = (raw) => {
    const shift = wrapLon((raw.west + raw.east) / 2) - (raw.west + raw.east) / 2; // keep box width, wrap its position
    const b = { ...raw, west: raw.west + shift, east: raw.east + shift };
    setRegion({ name: "Custom box", box: b, lat: (b.south + b.north) / 2, lon: (b.west + b.east) / 2 });
  };

  const t = data?.trends?.heatwave_days;
  const tiles = data && [
    ["Total heatwave events", data.yearly.reduce((a, r) => a + r.events, 0)],
    ["Total heatwave days", data.yearly.reduce((a, r) => a + r.heatwave_days, 0)],
    ["Longest event (days)", Math.max(...data.yearly.map((r) => r.max_duration))],
    ["Linear trend (days/decade)", t?.linear_slope_per_decade != null ? `${t.linear_slope_per_decade > 0 ? "+" : ""}${t.linear_slope_per_decade.toFixed(2)}` : "n/a"],
  ];

  return (
    <div className="app">
      <header>
        <h1>Climate Hazard Trend Analyzer</h1>
        <p>Historical heatwave frequency, duration and intensity trends, from ERA5 reanalysis via Open-Meteo.</p>
      </header>

      <section className="panel controls">
        <label>Hazard
          <select value="heatwave" onChange={() => {}}>
            <option value="heatwave">Heatwave</option>
            <option disabled>Drought (coming soon)</option>
            <option disabled>Heavy rainfall (coming soon)</option>
          </select>
        </label>

        <label>Region type
          <select value={mode} onChange={(e) => { setMode(e.target.value); if (e.target.value === "preset") setRegion(locations.find((l) => l.id === "delhi") || DEFAULT); }}>
            <option value="preset">City / State</option>
            <option value="point">Custom point (map)</option>
            <option value="box">Custom lat-lon box (map)</option>
          </select>
        </label>

        {mode === "preset" && (
          <label>City / State
            <select value={region.id || ""} onChange={(e) => pickPreset(e.target.value)}>
              {locations.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
            </select>
          </label>
        )}

        <label>Season
          <select value={season} onChange={(e) => setSeason(e.target.value)}>
            <option value="hot">Hot season only</option>
            <option value="all">All year</option>
          </select>
        </label>

        <label>From
          <input type="number" value={startYear} min={bounds.min} max={bounds.max} onChange={(e) => setStartYear(e.target.value)} />
        </label>
        <label>To
          <input type="number" value={endYear} min={bounds.min} max={bounds.max} onChange={(e) => setEndYear(e.target.value)} />
        </label>
        <button onClick={() => analyse()} disabled={loading}>{loading ? "Analysing…" : "Analyse"}</button>
      </section>

      {mode !== "preset" && (
        <p className="hint">
          {mode === "point" ? "Click the map to choose a point." : "Click two opposite corners on the map to draw a box (max 5° per side). The box centre is analysed."}
        </p>
      )}
      <MapPicker region={region} mode={mode === "box" ? "box" : "point"}
                 onPoint={(la, lo) => mode !== "preset" && setPoint(la, lo)}
                 onBox={(b) => mode === "box" && setBox(b)} />
      <p className="hint">Selected: <b>{region.name}</b> ({region.lat.toFixed?.(2) ?? region.lat}, {region.lon.toFixed?.(2) ?? region.lon})</p>

      {error && <div className="error" role="alert">{error}</div>}
      {loading && !data && <p>Loading data (first request for a new place can take a few seconds)…</p>}

      {data && (
        <div className={loading ? "results stale" : "results"}>
          <section className={`insight ${data.insight.confidence}`}>
            <h2>{data.insight.headline}</h2>
            <p>{data.insight.detail}</p>
          </section>

          <div className="tiles">
            {tiles.map(([k, v]) => <div className="tile" key={k}><span>{v}</span>{k}</div>)}
          </div>

          <section className="panel"><h3>Heatwave frequency per year</h3>
            <div className="chart"><FrequencyChart yearly={data.yearly} /></div></section>
          <section className="panel"><h3>Duration and intensity</h3>
            <div className="chart"><IntensityChart yearly={data.yearly} /></div></section>
          <section className="panel"><h3>Heatwave threshold by calendar day (baseline {data.definition.baseline.join("–")})</h3>
            <div className="chart short"><ThresholdChart thresholds={data.thresholds_by_day} /></div></section>

          <section className="panel">
            <h3>Data quality &amp; method</h3>
            <ul>
              <li>Heatwave = ≥ {data.definition.min_consecutive_days} consecutive days with Tmax above the {data.definition.percentile}th percentile of the same calendar day in {data.definition.baseline.join("–")} (±{data.definition.window_days >> 1}-day window). {data.definition.season === "hot" ? `Only the hottest third of the year counts (months: ${data.definition.season_months.map((m) => MONTH_NAMES[m - 1]).join(", ")}).` : "All days of the year are considered."}</li>
              <li>{data.quality.days_missing} missing day(s) ({data.quality.missing_pct}%), {data.quality.days_outlier_removed} implausible value(s) removed; years with &lt;90% coverage are excluded{data.quality.years_excluded.length ? ` (${data.quality.years_excluded.join(", ")})` : ""}.</li>
              <li>Grid cell analysed: {data.location.lat}, {data.location.lon}. {data.cached ? "Served from database cache." : "Freshly ingested and stored."}</li>
            </ul>
            <div className="exports">
              <a href={exportUrl("csv", qs)}>Download CSV</a>
              <a href={exportUrl("pdf", qs)}>Download PDF</a>
            </div>
          </section>

          <section className="panel">
            <h3>Longest events</h3>
            <table>
              <thead><tr><th>Start</th><th>End</th><th>Days</th><th>Peak Tmax °C</th><th>Mean excess °C</th></tr></thead>
              <tbody>
                {data.events.slice(0, 10).map((e) => (
                  <tr key={e.start}><td>{e.start}</td><td>{e.end}</td><td>{e.duration}</td><td>{e.peak_tmax}</td><td>{e.mean_excess}</td></tr>
                ))}
              </tbody>
            </table>
          </section>
        </div>
      )}
    </div>
  );
}
