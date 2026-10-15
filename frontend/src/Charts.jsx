import {
  BarElement, CategoryScale, Chart as ChartJS, Filler, Legend, LineElement, LinearScale, PointElement, Tooltip,
} from "chart.js";
import { Bar, Line } from "react-chartjs-2";

ChartJS.register(BarElement, CategoryScale, Filler, Legend, LineElement, LinearScale, PointElement, Tooltip);

const ORANGE = "#c2410c";
const BLUE = "#1d4ed8";
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const axis = (title) => ({ title: { display: true, text: title }, beginAtZero: true });
const base = { responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false } };

export function FrequencyChart({ yearly }) {
  const labels = yearly.map((r) => r.year);
  return (
    <Bar
      data={{
        labels,
        datasets: [
          { type: "line", label: "5-yr rolling avg (days)", data: yearly.map((r) => r.heatwave_days_rolling5),
            borderColor: BLUE, backgroundColor: BLUE, tension: 0.3, pointRadius: 0, yAxisID: "y" },
          { label: "Heatwave days", data: yearly.map((r) => (r.valid ? r.heatwave_days : null)),
            backgroundColor: ORANGE, yAxisID: "y" },
          { label: "Heatwave events", data: yearly.map((r) => (r.valid ? r.events : null)),
            backgroundColor: "#fdba74", yAxisID: "y" },
        ],
      }}
      options={{ ...base, scales: { y: axis("Days / events per year"), x: { title: { display: true, text: "Year" } } } }}
    />
  );
}

export function IntensityChart({ yearly }) {
  const labels = yearly.map((r) => r.year);
  return (
    <Line
      data={{
        labels,
        datasets: [
          { label: "Longest event (days)", data: yearly.map((r) => (r.valid ? r.max_duration : null)),
            borderColor: ORANGE, backgroundColor: ORANGE, yAxisID: "y", tension: 0.2 },
          { label: "Mean excess over P95 (°C)", data: yearly.map((r) => (r.valid && r.events ? r.mean_excess : null)),
            borderColor: BLUE, backgroundColor: BLUE, yAxisID: "y1", tension: 0.2, spanGaps: true },
        ],
      }}
      options={{
        ...base,
        scales: {
          y: axis("Longest event (days)"),
          y1: { ...axis("Mean excess (°C)"), position: "right", grid: { drawOnChartArea: false } },
        },
      }}
    />
  );
}

export function ThresholdChart({ thresholds }) {
  // 365-day non-leap calendar; label each month start.
  const starts = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334];
  const labels = Array.from({ length: 365 }, (_, i) => {
    const m = starts.filter((s) => s <= i).length - 1;
    return i === starts[m] ? MONTHS[m] : "";
  });
  return (
    <Line
      data={{ labels, datasets: [{ label: "95th percentile Tmax (°C)", data: thresholds, borderColor: ORANGE,
        pointRadius: 0, fill: true, backgroundColor: "rgba(194,65,12,0.12)" }] }}
      options={{ ...base, scales: { y: { title: { display: true, text: "°C" } }, x: { ticks: { autoSkip: false, maxRotation: 0 } } } }}
    />
  );
}
