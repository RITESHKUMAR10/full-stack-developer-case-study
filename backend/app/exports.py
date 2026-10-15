"""CSV / PDF export of an analysis document."""
from __future__ import annotations

import csv
import io
from xml.sax.saxutils import escape

_COLS = ["year", "events", "heatwave_days", "max_duration", "mean_duration", "mean_excess",
         "max_tmax", "heatwave_days_rolling5", "coverage", "valid"]


def _safe_cell(v):
    """Neutralise CSV/Excel formula injection for any text cell."""
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@"):
        return "'" + v
    return v


def to_csv(doc: dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    loc = doc["location"]
    w.writerow(["# Heatwave analysis", _safe_cell(loc.get("name") or ""), f"lat={loc['lat']}", f"lon={loc['lon']}"])
    w.writerow(["# Definition", f">= {doc['definition']['min_consecutive_days']} consecutive days Tmax > "
                f"P{doc['definition']['percentile']} (baseline {doc['definition']['baseline'][0]}-{doc['definition']['baseline'][1]}); "
                f"season={doc['definition']['season']}"])
    w.writerow(_COLS)
    for r in doc["yearly"]:
        w.writerow([_safe_cell(r.get(c)) for c in _COLS])
    return buf.getvalue()


def to_pdf(doc: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    ss = getSampleStyleSheet()
    out = io.BytesIO()
    pdf = SimpleDocTemplate(out, pagesize=A4, title="Heatwave trend report")
    loc, ins, d = doc["location"], doc["insight"], doc["definition"]
    story = [
        Paragraph("Heatwave Trend Report", ss["Title"]),
        Paragraph(escape(f"{loc.get('name') or 'Selected region'} ({loc['lat']}, {loc['lon']}) - "
                         f"{doc['range']['start_year']} to {doc['range']['end_year']}"), ss["Heading3"]),
        Spacer(1, 8), Paragraph(escape(ins["headline"]), ss["BodyText"]),
        Paragraph(escape(ins["detail"]), ss["BodyText"]), Spacer(1, 8),
        Paragraph(escape(f"Definition: >= {d['min_consecutive_days']} consecutive days with Tmax above the "
                         f"{d['percentile']}th percentile of {d['baseline'][0]}-{d['baseline'][1]} "
                         f"(per calendar day, +/-{d['window_days'] // 2} day window), "
                         f"{'hot season only' if d['season'] == 'hot' else 'all year'}. Source: {d['source']}."), ss["BodyText"]),
        Spacer(1, 10),
    ]
    data = [["Year", "Events", "HW days", "Max dur.", "Mean excess C", "Max Tmax C"]]
    for r in doc["yearly"]:
        data.append([r["year"], r["events"], r["heatwave_days"], r["max_duration"], r["mean_excess"], r["max_tmax"]])
    t = Table(data, repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                           ("GRID", (0, 0), (-1, -1), 0.25, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 8)]))
    story.append(t)
    pdf.build(story)
    return out.getvalue()
