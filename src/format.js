const fullNumber = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const decimalNumber = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

export function isFiniteNumber(value) {
  return typeof value === "number" && Number.isFinite(value);
}

export function formatCompact(value, { decimals = 1 } = {}) {
  if (!isFiniteNumber(value)) return "—";
  const absolute = Math.abs(value);
  if (absolute >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(decimals)}B`;
  if (absolute >= 1_000_000) return `${(value / 1_000_000).toFixed(decimals)}M`;
  if (absolute >= 10_000) return `${(value / 1_000).toFixed(decimals)}K`;
  if (absolute >= 1_000) return `${(value / 1_000).toFixed(decimals)}K`;
  return fullNumber.format(Math.round(value));
}

export function formatNumber(value) {
  if (!isFiniteNumber(value)) return "—";
  return fullNumber.format(Math.round(value));
}

export function formatUnits(value, { compact = true } = {}) {
  if (!isFiniteNumber(value)) return "—";
  return compact ? formatCompact(value) : formatNumber(value);
}

export function formatPercent(value, digits = 1) {
  if (!isFiniteNumber(value)) return "—";
  return `${value.toFixed(digits)}%`;
}

export function formatDecimal(value, digits = 1) {
  if (!isFiniteNumber(value)) return "—";
  return value.toFixed(digits);
}

export function formatRatio(value) {
  if (!isFiniteNumber(value)) return "—";
  return `${value.toFixed(2)}×`;
}

export function formatDate(value, { withYear = true, short = false } = {}) {
  if (!value) return "—";
  const date = new Date(`${String(value).slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleDateString("en-GB", {
    day: short ? undefined : "2-digit",
    month: "short",
    year: withYear ? "numeric" : undefined,
    timeZone: "UTC",
  });
}

export function formatChartDate(value, { withYear = false } = {}) {
  if (!value) return "";
  const date = new Date(`${String(value).slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: withYear ? "2-digit" : undefined,
    timeZone: "UTC",
  });
}

export function formatDateTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function clamp(value, minimum, maximum) {
  return Math.min(maximum, Math.max(minimum, value));
}

export function classNames(...values) {
  return values.filter(Boolean).join(" ");
}

export function riskLabel(risk, { long = false } = {}) {
  if (risk === "critical") return long ? "Critical" : "Critical";
  if (risk === "watch") return long ? "Warning" : "Warning";
  if (risk === "healthy") return long ? "Normal" : "Normal";
  return "Unknown";
}

export function riskTone(risk) {
  if (risk === "critical") return "critical";
  if (risk === "watch") return "warning";
  if (risk === "healthy") return "positive";
  return "neutral";
}

export function coverageLabel(value) {
  if (!isFiniteNumber(value)) return "—";
  if (value < 1) return `${value.toFixed(2)} days`;
  if (value < 10) return `${value.toFixed(1)} days`;
  return `${Math.round(value)} days`;
}

export function sourceLabel(source) {
  if (!source) return "Unknown source";
  if (source === "synthetic_simulation") return "Synthetic demonstration data";
  if (source === "test_fixture") return "Test fixture data";
  if (source === "forecast_dataset") return "Forecast dataset";
  return String(source).replaceAll("_", " ");
}

export function cityFromLocation(locationName, fallback = "Unassigned") {
  if (!locationName) return fallback;
  const [city] = String(locationName).split("-");
  return city || fallback;
}

export { decimalNumber };
