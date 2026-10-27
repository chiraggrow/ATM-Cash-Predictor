import React, { useEffect, useMemo, useState } from "react";
import {
  getLatestAtmRows,
  getMonthlyDemand,
  getPeriodData,
  loadDataset,
} from "./data.js";

const periods = [
  { label: "6 months", value: 6 },
  { label: "12 months", value: 12 },
  { label: "24 months", value: 24 },
];

const numberFormat = new Intl.NumberFormat("en-US");

function formatCompact(value) {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return numberFormat.format(Math.round(value));
}

function formatDate(value) {
  return new Date(`${value}T00:00:00Z`).toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

function Icon({ name, size = 20 }) {
  const common = {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.7,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    "aria-hidden": true,
  };

  const paths = {
    grid: <><rect x="3.5" y="3.5" width="7" height="7" rx="1.5" /><rect x="13.5" y="3.5" width="7" height="7" rx="1.5" /><rect x="3.5" y="13.5" width="7" height="7" rx="1.5" /><rect x="13.5" y="13.5" width="7" height="7" rx="1.5" /></>,
    atm: <><rect x="4" y="2.8" width="16" height="18.4" rx="2" /><path d="M8 7h8M8 11h8M8 15h3M8 18h8" /><circle cx="15.5" cy="15.5" r=".5" fill="currentColor" /></>,
    chart: <><path d="M3.5 3.5v17h17" /><path d="m6.5 15 4-4 3 2 5-6" /><path d="M15.5 7h3v3" /></>,
    refill: <><path d="M20 7v5h-5" /><path d="M4.6 9a7.5 7.5 0 0 1 12.6-2L20 12" /><path d="M4 17v-5h5" /><path d="M19.4 15a7.5 7.5 0 0 1-12.6 2L4 12" /></>,
    search: <><circle cx="10.8" cy="10.8" r="6.8" /><path d="m16 16 4.5 4.5" /></>,
    bell: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" /><path d="M10 21h4" /></>,
    arrow: <><path d="M7 17 17 7M7 7h10v10" /></>,
    chevron: <path d="m9 18 6-6-6-6" />,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
    bank: <><path d="m3 9 9-6 9 6" /><path d="M5 10v8M9 10v8M15 10v8M19 10v8M3 21h18M2 18h20" /></>,
    download: <><path d="M12 3v12m0 0 4-4m-4 4-4-4" /><path d="M5 17v4h14v-4" /></>,
  };

  return <svg {...common}>{paths[name]}</svg>;
}

function Sidebar() {
  const links = [
    { label: "Overview", icon: "grid", href: "#overview", active: true },
    { label: "ATM network", icon: "atm", href: "#network" },
    { label: "Demand patterns", icon: "chart", href: "#demand" },
    { label: "Replenishment", icon: "refill", href: "#network" },
  ];

  return (
    <aside className="sidebar">
      <a className="brand" href="#overview" aria-label="Bank Muscat ATM intelligence home">
        <span className="brand-mark"><Icon name="bank" size={23} /></span>
        <span className="brand-name">bank muscat<span>ATM INTELLIGENCE</span></span>
      </a>
      <div className="nav-caption">WORKSPACE</div>
      <nav className="nav-list" aria-label="Main navigation">
        {links.map(({ label, icon, href, active }) => (
          <a className={`nav-link${active ? " active" : ""}`} href={href} key={label}>
            <Icon name={icon} size={19} /><span>{label}</span>
            {label === "Replenishment" && <span className="nav-count">!</span>}
          </a>
        ))}
      </nav>
      <div className="sidebar-bottom">
        <div className="help-card">
          <span className="help-icon"><Icon name="chart" size={17} /></span>
          <strong>Historical data view</strong>
          <p>Insights reflect the dataset period, not live ATM telemetry.</p>
        </div>
        <div className="profile">
          <div className="avatar">OM</div>
          <div className="profile-name">Operations team<span>Muscat, Oman</span></div>
          <span className="profile-dots">···</span>
        </div>
      </div>
    </aside>
  );
}

function DemandChart({ data }) {
  const width = 720;
  const height = 220;
  const padding = { top: 16, right: 12, bottom: 32, left: 48 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const values = data.map((item) => item.average);
  const min = Math.floor(Math.min(...values) / 10_000) * 10_000;
  const max = Math.ceil(Math.max(...values) / 10_000) * 10_000;
  const range = max - min || 1;
  const points = data.map((item, index) => ({
    x: padding.left + (data.length === 1 ? plotWidth / 2 : (index / (data.length - 1)) * plotWidth),
    y: padding.top + plotHeight - ((item.average - min) / range) * plotHeight,
    ...item,
  }));
  const line = points.map((point) => `${point.x},${point.y}`).join(" ");
  const area = `${padding.left},${padding.top + plotHeight} ${line} ${padding.left + plotWidth},${padding.top + plotHeight}`;
  const gridValues = Array.from({ length: 4 }, (_, index) => min + (range * index) / 3);

  return (
    <div className="chart-wrap">
      <div className="chart-y-label">CASH UNITS</div>
      <svg className="demand-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Average observed next-day cash demand by month">
        <defs>
          <linearGradient id="demand-fill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#d82832" stopOpacity=".17" />
            <stop offset="100%" stopColor="#d82832" stopOpacity="0" />
          </linearGradient>
        </defs>
        {gridValues.map((value, index) => {
          const y = padding.top + plotHeight - (index / 3) * plotHeight;
          return (
            <g key={value}>
              <line x1={padding.left} x2={width - padding.right} y1={y} y2={y} className="chart-grid" />
              <text x={padding.left - 10} y={y + 4} textAnchor="end" className="chart-tick">{formatCompact(value)}</text>
            </g>
          );
        })}
        <polygon points={area} fill="url(#demand-fill)" />
        <polyline points={line} className="chart-line" />
        {points.map((point) => (
          <circle key={point.month} cx={point.x} cy={point.y} r="3" className="chart-dot">
            <title>{`${new Date(`${point.month}-01T00:00:00Z`).toLocaleDateString("en", { month: "long", year: "numeric", timeZone: "UTC" })}: ${numberFormat.format(Math.round(point.average))} average observed cash units`}</title>
          </circle>
        ))}
        {points.filter((_, index) => index % Math.ceil(points.length / 6) === 0 || index === points.length - 1).map((point) => (
          <text key={`label-${point.month}`} x={point.x} y={height - 7} textAnchor="middle" className="chart-tick">
            {new Date(`${point.month}-01T00:00:00Z`).toLocaleDateString("en", { month: "short", year: "2-digit", timeZone: "UTC" })}
          </text>
        ))}
      </svg>
    </div>
  );
}

function App() {
  const [period, setPeriod] = useState(12);
  const [search, setSearch] = useState("");
  const [riskFilter, setRiskFilter] = useState("all");
  const [dataset, setDataset] = useState(null);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    loadDataset()
      .then(setDataset)
      .catch((error) => setLoadError(error.message));
  }, []);

  const periodData = useMemo(
    () => dataset ? getPeriodData(dataset.observations, dataset.latestDatasetDate, period) : [],
    [dataset, period],
  );
  const monthlyData = useMemo(() => getMonthlyDemand(periodData), [periodData]);
  const latestRows = useMemo(
    () => dataset ? getLatestAtmRows(dataset.observations) : [],
    [dataset],
  );
  const averageDemand = periodData.length
    ? periodData.reduce((sum, row) => sum + row.demand, 0) / periodData.length
    : 0;
  const atmCount = dataset?.atmCount ?? 0;
  const replenishCount = latestRows.filter((row) => row.replenishmentRequired).length;
  const atRiskCount = latestRows.filter((row) => row.risk === "critical").length;
  const locationRows = useMemo(() => {
    const locations = new Map();
    for (const row of periodData) {
      const current = locations.get(row.Location_Type) ?? { name: row.Location_Type, total: 0, count: 0 };
      current.total += row.demand;
      current.count += 1;
      locations.set(row.Location_Type, current);
    }
    return [...locations.values()]
      .map((item) => ({ ...item, average: item.total / item.count }))
      .sort((a, b) => b.average - a.average);
  }, [periodData]);

  const filteredRows = latestRows
    .filter((row) => row.ATM_ID.toLowerCase().includes(search.toLowerCase()) || row.Location_Type.toLowerCase().includes(search.toLowerCase()))
    .filter((row) => riskFilter === "all" || row.risk === riskFilter)
    .sort((a, b) => {
      const severity = { critical: 0, watch: 1, healthy: 2 };
      return severity[a.risk] - severity[b.risk] || b.demand - a.demand;
    });

  return (
    <div className="app-shell">
      <Sidebar />
      <main className="main-content" id="overview">
        <header className="topbar">
          <div className="breadcrumbs"><span>Cash operations</span><Icon name="chevron" size={15} /><strong>Overview</strong></div>
          <div className="topbar-actions">
            <span className="data-status"><span className="status-dot" />Historical data</span>
            <button className="icon-button notification-button" aria-label="Notifications"><Icon name="bell" size={19} /><i /></button>
            <div className="topbar-avatar">AK</div>
          </div>
        </header>

        {loadError ? (
          <div className="load-state load-error" role="alert">Unable to load the ATM dataset: {loadError}</div>
        ) : !dataset ? (
          <div className="load-state" role="status">Loading historical ATM data…</div>
        ) : (
        <div className="page-content">
          <section className="page-heading">
            <div>
              <div className="eyebrow"><span className="eyebrow-line" />CASH MANAGEMENT</div>
              <h1>ATM cash overview</h1>
              <p>Historical demand and replenishment signals across your ATM network.</p>
            </div>
            <div className="heading-tools">
              <div className="date-chip"><Icon name="clock" size={16} /><span>Data through {formatDate(dataset.latestDatasetDate)}</span></div>
              <button className="export-button" onClick={() => window.print()}><Icon name="download" size={16} />Export view</button>
            </div>
          </section>

          <section className="notice-banner" aria-label="Data source notice">
            <span className="notice-icon"><Icon name="clock" size={17} /></span>
            <p><strong>Historical dataset view</strong><span>Metrics below summarize the supplied ATM records. No live feed or trained forecasting model is connected.</span></p>
            <span className="notice-period">2022 — 2024</span>
          </section>

          <section className="metrics-grid" aria-label="Network summary">
            <article className="metric-card">
              <div className="metric-top"><span className="metric-icon demand-icon"><Icon name="chart" size={18} /></span><span className="metric-label">AVG. NEXT-DAY DEMAND</span><span className="metric-info" title="Average observed Cash_Demand_Next_Day in the selected dataset period">i</span></div>
              <div className="metric-value">{formatCompact(averageDemand)}</div>
              <div className="metric-foot"><span className="metric-caption">cash units per observation</span><span className="metric-tag">OBSERVED</span></div>
            </article>
            <article className="metric-card">
              <div className="metric-top"><span className="metric-icon atm-icon"><Icon name="atm" size={18} /></span><span className="metric-label">MONITORED ATMS</span><span className="metric-info" title="Unique ATM identifiers found in the supplied dataset">i</span></div>
              <div className="metric-value">{numberFormat.format(atmCount)}</div>
              <div className="metric-foot"><span className="metric-caption">unique ATM identifiers</span><span className="metric-tag neutral-tag">NETWORK</span></div>
            </article>
            <article className="metric-card">
              <div className="metric-top"><span className="metric-icon refill-icon"><Icon name="refill" size={18} /></span><span className="metric-label">REPLENISHMENT FLAGS</span><span className="metric-info" title="Latest recorded observation per ATM marked as requiring replenishment">i</span></div>
              <div className="metric-value">{numberFormat.format(replenishCount)}<span className="metric-total"> / {numberFormat.format(atmCount)}</span></div>
              <div className="metric-foot"><span className="metric-caption">latest observation per ATM</span><span className="metric-tag neutral-tag">RECORDED</span></div>
            </article>
            <article className="metric-card">
              <div className="metric-top"><span className="metric-icon risk-icon"><Icon name="arrow" size={18} /></span><span className="metric-label">BELOW DEMAND</span><span className="metric-info" title="Latest recorded balance is lower than the next-day cash demand value">i</span></div>
              <div className="metric-value">{numberFormat.format(atRiskCount)}<span className="metric-total"> / {numberFormat.format(atmCount)}</span></div>
              <div className="metric-foot"><span className="metric-caption">balance below observed demand</span><span className="metric-tag risk-tag">REVIEW</span></div>
            </article>
          </section>

          <section className="analysis-grid" id="demand">
            <article className="panel demand-panel">
              <div className="panel-heading">
                <div><h2>Cash demand trend</h2><p>Average observed next-day demand by month</p></div>
                <div className="period-picker" aria-label="Choose chart period">
                  {periods.map((option) => <button key={option.value} className={period === option.value ? "selected" : ""} onClick={() => setPeriod(option.value)}>{option.label}</button>)}
                </div>
              </div>
              <div className="chart-legend"><span className="legend-swatch" />Average demand <span className="legend-note">Historical observations</span></div>
              <DemandChart data={monthlyData} />
              <div className="panel-footnote"><span className="footnote-dot" />Monthly mean of <strong>{numberFormat.format(periodData.length)}</strong> records in the selected period</div>
            </article>

            <article className="panel location-panel">
              <div className="panel-heading">
                <div><h2>Demand by location</h2><p>Average next-day cash demand</p></div>
                <span className="small-icon-button"><Icon name="arrow" size={16} /></span>
              </div>
              <div className="location-list">
                {locationRows.map((location, index) => {
                  const percentage = (location.average / Math.max(...locationRows.map((item) => item.average))) * 100;
                  return (
                    <div className="location-row" key={location.name}>
                      <div className="location-title"><span className={`location-rank rank-${index + 1}`}>{String(index + 1).padStart(2, "0")}</span><span>{location.name}</span><strong>{formatCompact(location.average)}</strong></div>
                      <div className="bar-track"><span style={{ width: `${percentage}%` }} /></div>
                    </div>
                  );
                })}
              </div>
              <div className="location-footnote">Cash units · selected time period</div>
            </article>
          </section>

          <section className="panel network-panel" id="network">
            <div className="panel-heading network-heading">
              <div><h2>ATM replenishment watch</h2><p>Latest available record for each ATM · {formatDate(dataset.latestDatasetDate)}</p></div>
              <div className="table-tools">
                <label className="search-field"><Icon name="search" size={17} /><input aria-label="Search ATMs or locations" placeholder="Search ATM or location" value={search} onChange={(event) => setSearch(event.target.value)} /></label>
                <select aria-label="Filter by cash status" value={riskFilter} onChange={(event) => setRiskFilter(event.target.value)}>
                  <option value="all">All statuses</option><option value="critical">Below demand</option><option value="watch">Watch</option><option value="healthy">Healthy</option>
                </select>
              </div>
            </div>
            <div className="table-scroll">
              <table>
                <thead><tr><th>ATM ID</th><th>LOCATION</th><th>LAST OBSERVED</th><th>DEMAND</th><th>CASH BALANCE</th><th>COVERAGE</th><th>STATUS</th></tr></thead>
                <tbody>
                  {filteredRows.slice(0, 8).map((row) => (
                    <tr key={row.ATM_ID}>
                      <td><span className="atm-id">{row.ATM_ID}</span></td>
                      <td>{row.Location_Type}</td>
                      <td className="date-cell">{formatDate(row.date)}</td>
                      <td className="amount-cell">{numberFormat.format(row.demand)}</td>
                      <td className="amount-cell">{numberFormat.format(row.balance)}</td>
                      <td><span className={`coverage-value ${row.risk === "critical" ? "coverage-low" : ""}`}>{Number.isFinite(row.coverage) ? `${row.coverage.toFixed(2)}×` : "—"}</span></td>
                      <td><span className={`status-pill ${row.risk}`}><i />{row.risk === "critical" ? "Below demand" : row.risk === "watch" ? "Watch" : "Healthy"}</span></td>
                    </tr>
                  ))}
                  {filteredRows.length === 0 && <tr><td className="empty-row" colSpan="7">No ATMs match your search and status filters.</td></tr>}
                </tbody>
              </table>
            </div>
            <div className="table-footer"><span>Showing <strong>{Math.min(filteredRows.length, 8)}</strong> of <strong>{filteredRows.length}</strong> matching ATMs</span><span className="table-method">Coverage = balance ÷ observed next-day demand</span></div>
          </section>

          <footer className="page-footer"><span>ATM Cash Intelligence <span className="footer-divider">·</span> Bank Muscat</span><span><span className="status-dot" />Dataset range: Jan 2022 – Jan 2024</span></footer>
        </div>
        )}
      </main>
    </div>
  );
}

export default App;
