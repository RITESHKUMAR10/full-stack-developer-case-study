// VITE_API_URL is empty in dev (Vite proxies /api) and set to the backend origin in production.
const BASE = import.meta.env.VITE_API_URL || "";

export function buildQuery(region, startYear, endYear, season = "hot") {
  const p = new URLSearchParams({ start_year: startYear, end_year: endYear, hazard: "heatwave", season });
  if (region.name) p.set("name", region.name);
  if (region.box) {
    const { south, north, west, east } = region.box;
    Object.entries({ south, north, west, east }).forEach(([k, v]) => p.set(k, v.toFixed(4)));
  } else {
    p.set("lat", region.lat);
    p.set("lon", region.lon);
  }
  return p.toString();
}

async function parse(res) {
  if (res.ok) return res;
  let msg = `Request failed (${res.status})`;
  try {
    const j = await res.json();
    if (res.status === 429) msg = "Too many requests - please wait a minute and retry.";
    else if (typeof j.detail === "string") msg = j.detail;
    else if (Array.isArray(j.detail)) msg = j.detail.map((d) => `${d.loc?.slice(-1)}: ${d.msg}`).join("; ");
  } catch { /* keep default */ }
  throw new Error(msg);
}

export const fetchLocations = () => fetch(`${BASE}/api/locations`).then(parse).then((r) => r.json());
export const fetchAnalysis = (qs, signal) => fetch(`${BASE}/api/analysis?${qs}`, { signal }).then(parse).then((r) => r.json());
export const exportUrl = (kind, qs) => `${BASE}/api/analysis/export.${kind}?${qs}`;
