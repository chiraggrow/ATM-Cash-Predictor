import React, { useEffect, useMemo, useState } from "react";
import {
  apiRequest,
  clearAccessToken,
  createSession,
  getAccessToken,
  saveAccessToken,
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
  if (!value) return "—";
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
    atm: <><rect x="4" y="2.8" width="16" height="18.4" rx="2" /><path d="M8 7h8M8 11h8M8 15h3M8 18h8" /></>,
    chart: <><path d="M3.5 3.5v17h17" /><path d="m6.5 15 4-4 3 2 5-6" /><path d="M15.5 7h3v3" /></>,
    refill: <><path d="M20 7v5h-5" /><path d="M4.6 9a7.5 7.5 0 0 1 12.6-2L20 12" /><path d="M4 17v-5h5" /><path d="M19.4 15a7.5 7.5 0 0 1-12.6 2L4 12" /></>,
    search: <><circle cx="10.8" cy="10.8" r="6.8" /><path d="m16 16 4.5 4.5" /></>,
    bank: <><path d="m3 9 9-6 9 6" /><path d="M5 10v8M9 10v8M15 10v8M19 10v8M3 21h18M2 18h20" /></>,
    download: <><path d="M12 3v12m0 0 4-4m-4 4-4-4" /><path d="M5 17v4h14v-4" /></>,
    logout: <><path d="M10 17l5-5-5-5" /><path d="M15 12H3" /><path d="M12 3h6a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-6" /></>,
    lock: <><rect x="4" y="10" width="16" height="11" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v3" /></>,
    alert: <><path d="m12 3 9 16H3L12 3Z" /><path d="M12 9v4m0 3h.01" /></>,
    arrow: <><path d="M7 17 17 7M7 7h10v10" /></>,
  };
  return <svg {...common}>{paths[name]}</svg>;
}

function Login({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const token = await createSession(username, password);
      const user = await apiRequest("/auth/me", { token });
      onLogin(token, user);
    } catch (requestError) {
      clearAccessToken();
      setError(requestError.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="login-screen">
      <section className="login-card">
        <div className="brand login-brand">
          <span className="brand-mark"><Icon name="bank" size={23} /></span>
          <span className="brand-name">bank muscat<span>ATM INTELLIGENCE</span></span>
        </div>
        <div className="login-intro">
          <div className="eyebrow"><span className="eyebrow-line" />CASH OPERATIONS</div>
          <h1>Welcome back</h1>
          <p>Sign in to review ATM demand insights and replenishment forecasts.</p>
        </div>
        <form className="login-form" onSubmit={submit}>
          <label htmlFor="username">Username</label>
          <input id="username" name="username" autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} required />
          <label htmlFor="password">Password</label>
          <input id="password" name="password" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required />
          {error && <div className="form-error" role="alert">{error}</div>}
          <button className="login-submit" type="submit" disabled={submitting}>
            <Icon name="lock" size={16} />{submitting ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <div className="login-footnote">Authorized banking operations staff only.</div>
      </section>
    </main>
  );
}

function Sidebar({ user, onLogout }) {
  const links = [
    { label: "Overview", icon: "grid", href: "#overview", active: true },
    { label: "ATM network", icon: "atm", href: "#network" },
    { label: "Demand patterns", icon: "chart", href: "#demand" },
    { label: "Forecast & stock", icon: "refill", href: "#forecast" },
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
          </a>
        ))}
      </nav>
      <div className="sidebar-bottom">
        <div className="help-card">
          <span className="help-icon"><Icon name="alert" size={17} /></span>
          <strong>Historical data environment</strong>
          <p>Forecasts use the latest sample in the supplied dataset, not a live ATM connection.</p>
        </div>
        <div className="profile">
          <div className="avatar">{user.username.slice(0, 2).toUpperCase()}</div>
          <div className="profile-name">{user.username}<span>{user.role} access</span></div>
          <button className="logout-button" onClick={onLogout} aria-label="Sign out" title="Sign out"><Icon name="logout" size={17} /></button>
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
  const values = data.map((item) => item.average_demand);
  if (values.length === 0) return <div className="chart-empty">No demand records in this time window.</div>;
  const min = Math.floor(Math.min(...values) / 10_000) * 10_000;
  const max = Math.ceil(Math.max(...values) / 10_000) * 10_000;
  const range = max - min || 1;
  const points = data.map((item, index) => ({
    x: padding.left + (data.length === 1 ? plotWidth / 2 : (index / (data.length - 1)) * plotWidth),
    y: padding.top + plotHeight - ((item.average_demand - min) / range) * plotHeight,
    ...item,
  }));
  const line = points.map((point) => `${point.x},${point.y}`).join(" ");
  const area = `${padding.left},${padding.top + plotHeight} ${line} ${padding.left + plotWidth},${padding.top + plotHeight}`;
  const gridValues = Array.from({ length: 4 }, (_, index) => min + (range * index) / 3);

  return (
    <div className="chart-wrap">
      <div className="chart-y-label">CASH UNITS</div>
      <svg className="demand-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Average observed next-day cash demand by month">
        <defs><linearGradient id="demand-fill" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="#d82832" stopOpacity=".17" /><stop offset="100%" stopColor="#d82832" stopOpacity="0" /></linearGradient></defs>
        {gridValues.map((value, index) => {
          const y = padding.top + plotHeight - (index / 3) * plotHeight;
          return <g key={value}><line x1={padding.left} x2={width - padding.right} y1={y} y2={y} className="chart-grid" /><text x={padding.left - 10} y={y + 4} textAnchor="end" className="chart-tick">{formatCompact(value)}</text></g>;
        })}
        <polygon points={area} fill="url(#demand-fill)" />
        <polyline points={line} className="chart-line" />
        {points.map((point) => <circle key={point.period} cx={point.x} cy={point.y} r="3" className="chart-dot"><title>{`${point.period}: ${numberFormat.format(Math.round(point.average_demand))} average observed cash units`}</title></circle>)}
        {points.filter((_, index) => index % Math.ceil(points.length / 6) === 0 || index === points.length - 1).map((point) => (
          <text key={`label-${point.period}`} x={point.x} y={height - 7} textAnchor="middle" className="chart-tick">
            {new Date(`${point.period}-01T00:00:00Z`).toLocaleDateString("en", { month: "short", year: "2-digit", timeZone: "UTC" })}
          </text>
        ))}
      </svg>
    </div>
  );
}

function MetricCard({ label, value, caption, tag, icon, iconClass, tagClass = "" }) {
  return (
    <article className="metric-card">
      <div className="metric-top">
        <span className={`metric-icon ${iconClass}`}><Icon name={icon} size={18} /></span>
        <span className="metric-label">{label}</span>
      </div>
      <div className="metric-value">{value}</div>
      <div className="metric-foot"><span className="metric-caption">{caption}</span><span className={`metric-tag ${tagClass}`}>{tag}</span></div>
    </article>
  );
}

function ForecastPanel({ atms, token, onForecast }) {
  const [atmId, setAtmId] = useState("");
  const [forecast, setForecast] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (atms.length && !atms.some((atm) => atm.atm_id === atmId)) setAtmId(atms[0].atm_id);
  }, [atms, atmId]);

  async function runForecast(event) {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      const result = await apiRequest("/forecasts", {
        token,
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ atm_id: atmId }),
      });
      setForecast(result);
      onForecast(result);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="panel forecast-panel" id="forecast">
      <div className="panel-heading">
        <div><h2>Next-day cash forecast</h2><p>One-step forecast using the latest available ATM observation</p></div>
        <span className="forecast-model-tag">TIME-BASED MODEL</span>
      </div>
      <form className="forecast-form" onSubmit={runForecast}>
        <label htmlFor="forecast-atm">ATM to forecast</label>
        <select id="forecast-atm" value={atmId} onChange={(event) => { setAtmId(event.target.value); setForecast(null); }} required disabled={!atms.length}>
          {atms.map((atm) => <option key={atm.atm_id} value={atm.atm_id}>{atm.atm_id} · {atm.location_type}</option>)}
        </select>
        <button className="forecast-button" type="submit" disabled={loading || !atmId}>{loading ? "Forecasting…" : "Generate forecast"}</button>
      </form>
      {error && <div className="form-error" role="alert">{error}</div>}
      {forecast ? (
        <div className="forecast-result" aria-live="polite">
          <div className="forecast-result-heading"><span className={`status-pill ${forecast.risk_level}`}><i />{forecast.risk_level}</span><span>Forecast for {formatDate(forecast.forecast_date)}</span><span>Input data through {formatDate(forecast.source_data_as_of)}</span></div>
          <div className="forecast-result-grid">
            <div><span>Expected demand</span><strong>{numberFormat.format(forecast.predicted_demand)}</strong><small>cash units · point estimate</small></div>
            <div><span>Empirical interval</span><strong>{formatCompact(forecast.lower_bound)}–{formatCompact(forecast.upper_bound)}</strong><small>holdout residual P90 range</small></div>
            <div><span>Replenishment suggested</span><strong>{numberFormat.format(forecast.recommended_replenishment)}</strong><small>cash units · capacity-aware</small></div>
          </div>
          {forecast.capacity_constrained && <div className="capacity-warning"><Icon name="alert" size={15} />The upper demand estimate exceeds this ATM's recorded capacity.</div>}
        </div>
      ) : (
        <div className="forecast-placeholder"><span className="forecast-placeholder-icon"><Icon name="chart" size={18} /></span><span>Select an ATM to create a forecast and record a replenishment recommendation.</span></div>
      )}
      <div className="forecast-disclaimer">A historical backtest example only. Validate with current ATM telemetry and cash operations before operational use.</div>
    </section>
  );
}

function Dashboard({ user, token, onLogout }) {
  const [period, setPeriod] = useState(12);
  const [search, setSearch] = useState("");
  const [riskFilter, setRiskFilter] = useState("");
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [retraining, setRetraining] = useState(false);

  const query = useMemo(() => {
    const params = new URLSearchParams({ months: String(period) });
    if (search.trim()) params.set("search", search.trim());
    if (riskFilter) params.set("risk", riskFilter);
    return params.toString();
  }, [period, search, riskFilter]);

  useEffect(() => {
    let active = true;
    async function loadDashboard() {
      setError("");
      try {
        const [summary, demand, locations, atms, allAtms, history] = await Promise.all([
          apiRequest("/analytics/summary", { token }),
          apiRequest(`/analytics/demand-trend?months=${period}`, { token }),
          apiRequest(`/analytics/location-demand?months=${period}`, { token }),
          apiRequest(`/atms?${query}`, { token }),
          apiRequest("/atms?limit=100", { token }),
          apiRequest("/forecasts?limit=6", { token }),
        ]);
        if (active) setData({ summary, demand, locations, atms, allAtms, history });
      } catch (requestError) {
        if (requestError.status === 401) {
          clearAccessToken();
          onLogout();
          return;
        }
        if (active) setError(requestError.message);
      }
    }
    loadDashboard();
    return () => { active = false; };
  }, [period, query, token, onLogout]);

  async function retrainModel() {
    setRetraining(true);
    setError("");
    try {
      await apiRequest("/admin/model/retrain", { token, method: "POST" });
      const summary = await apiRequest("/analytics/summary", { token });
      setData((current) => current ? { ...current, summary } : current);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setRetraining(false);
    }
  }

  const summary = data?.summary;
  const atms = data?.atms.items ?? [];
  const maxLocationDemand = Math.max(1, ...(data?.locations.map((item) => item.average_demand) ?? []));

  return (
    <div className="app-shell">
      <Sidebar user={user} onLogout={onLogout} />
      <main className="main-content" id="overview">
        <header className="topbar">
          <div className="breadcrumbs"><span>Cash operations</span><span aria-hidden="true">/</span><strong>Overview</strong></div>
          <div className="topbar-actions"><span className="data-status"><span className="status-dot" />Historical data</span><div className="topbar-avatar">{user.username.slice(0, 2).toUpperCase()}</div></div>
        </header>
        {error && <div className="load-state load-error" role="alert">{error}</div>}
        {!data && !error ? <div className="load-state" role="status">Loading protected dashboard data…</div> : data && (
          <div className="page-content">
            <section className="page-heading">
              <div><div className="eyebrow"><span className="eyebrow-line" />CASH MANAGEMENT</div><h1>ATM cash overview</h1><p>Demand, forecast evaluation and replenishment signals for the ATM network.</p></div>
              <div className="heading-tools">
                <div className="date-chip"><span className="status-dot" />Data through {formatDate(summary.latest_dataset_date)}</div>
                {user.role === "admin" && <button className="export-button" onClick={retrainModel} disabled={retraining}>{retraining ? "Evaluating…" : "Retrain & evaluate"}</button>}
                <button className="export-button" onClick={() => window.print()}><Icon name="download" size={16} />Export view</button>
              </div>
            </section>

            <section className="notice-banner" aria-label="Data source notice">
              <span className="notice-icon"><Icon name="alert" size={17} /></span>
              <p><strong>Historical dataset — not live ATM data</strong><span>Source ends {formatDate(summary.latest_dataset_date)}; {summary.changing_location_atms} ATM IDs have changing location labels. The 70% cash-out figure is a simulated balance-versus-demand proxy, not a measured incident reduction.</span></p>
              <span className="notice-period">{summary.duplicate_atm_date_groups} duplicate ATM/date groups retained</span>
            </section>

            <section className="metrics-grid" aria-label="Network and model summary">
              <MetricCard label="AVG. NEXT-DAY DEMAND" value={formatCompact(summary.average_demand)} caption={`${numberFormat.format(summary.record_count)} observations · cash units`} tag="OBSERVED" icon="chart" iconClass="demand-icon" />
              <MetricCard label="MONITORED ATMS" value={numberFormat.format(summary.atm_count)} caption="unique ATM identifiers" tag="NETWORK" icon="atm" iconClass="atm-icon" tagClass="neutral-tag" />
              <MetricCard label="HOLDOUT ACCURACY" value={`${summary.model.accuracy_pct.toFixed(1)}%`} caption={`${summary.model.wape_pct.toFixed(1)}% weighted absolute error`} tag={summary.model.target_met ? "TARGET MET" : "BELOW 85% GOAL"} icon="chart" iconClass={summary.model.target_met ? "refill-icon" : "risk-icon"} tagClass={summary.model.target_met ? "neutral-tag" : "risk-tag"} />
              <MetricCard label="SIMULATED CASH-OUT REDUCTION" value={`${summary.model.simulated_cashout_reduction_pct.toFixed(1)}%`} caption={`${summary.model.baseline_cashout_proxy_events} baseline proxy events · no incident labels`} tag={summary.model.cashout_reduction_target_met ? "SIMULATED TARGET MET" : "BELOW 70% GOAL"} icon="refill" iconClass={summary.model.cashout_reduction_target_met ? "refill-icon" : "risk-icon"} tagClass={summary.model.cashout_reduction_target_met ? "neutral-tag" : "risk-tag"} />
              <MetricCard label="ATMS BELOW DEMAND" value={numberFormat.format(summary.at_risk_atms)} caption="latest balance below observed demand" tag="REVIEW" icon="arrow" iconClass="risk-icon" tagClass="risk-tag" />
            </section>

            <section className="model-summary panel">
              <div className="model-summary-copy"><span className="model-indicator"><i /></span><div><strong>{summary.model.model_name.replaceAll("-", " ")}</strong><span>Chronological holdout · train through {formatDate(summary.model.train_end_date)} · test {formatDate(summary.model.test_start_date)}–{formatDate(summary.model.test_end_date)}</span></div></div>
              <div className="model-summary-stats"><span>MAE <strong>{formatCompact(summary.model.mae)}</strong></span><span>90% interval error <strong>{formatCompact(summary.model.interval_abs_error_p90)}</strong></span><span>Baseline WAPE <strong>{summary.model.baseline_wape_pct.toFixed(1)}%</strong></span></div>
            </section>

            <section className="analysis-grid" id="demand">
              <article className="panel demand-panel">
                <div className="panel-heading"><div><h2>Cash demand trend</h2><p>Average observed next-day demand by month</p></div><div className="period-picker" aria-label="Choose chart period">{periods.map((option) => <button key={option.value} className={period === option.value ? "selected" : ""} onClick={() => setPeriod(option.value)}>{option.label}</button>)}</div></div>
                <div className="chart-legend"><span className="legend-swatch" />Average demand <span className="legend-note">Historical observations · cash units</span></div>
                <DemandChart data={data.demand} />
                <div className="panel-footnote"><span className="footnote-dot" />Chronological dataset summary · {numberFormat.format(data.demand.reduce((total, item) => total + item.observations, 0))} records</div>
              </article>
              <article className="panel location-panel">
                <div className="panel-heading"><div><h2>Demand by location</h2><p>Average next-day cash demand</p></div><span className="small-icon-button"><Icon name="arrow" size={16} /></span></div>
                <div className="location-list">{data.locations.map((location, index) => {
                  const percentage = (location.average_demand / maxLocationDemand) * 100;
                  return <div className="location-row" key={location.location_type}><div className="location-title"><span className={`location-rank rank-${index + 1}`}>{String(index + 1).padStart(2, "0")}</span><span>{location.location_type}</span><strong>{formatCompact(location.average_demand)}</strong></div><div className="bar-track"><span style={{ width: `${percentage}%` }} /></div></div>;
                })}</div>
                <div className="location-footnote">Cash units · {period} month view</div>
              </article>
            </section>

            <ForecastPanel
              atms={data.allAtms.items}
              token={token}
              onForecast={(forecast) => setData((current) => current
                ? { ...current, history: { total: current.history.total + 1, items: [forecast, ...current.history.items].slice(0, 6) } }
                : current)}
            />

            <section className="panel network-panel" id="network">
              <div className="panel-heading network-heading">
                <div><h2>ATM replenishment watch</h2><p>Latest available observation per ATM · {formatDate(summary.latest_dataset_date)}</p></div>
                <div className="table-tools">
                  <label className="search-field"><Icon name="search" size={17} /><input aria-label="Search ATMs or locations" placeholder="Search ATM or location" value={search} onChange={(event) => setSearch(event.target.value)} /></label>
                  <select aria-label="Filter by cash status" value={riskFilter} onChange={(event) => setRiskFilter(event.target.value)}><option value="">All statuses</option><option value="critical">Below demand</option><option value="watch">Watch</option><option value="healthy">Healthy</option></select>
                </div>
              </div>
              <div className="table-scroll"><table>
                <thead><tr><th>ATM ID</th><th>LOCATION</th><th>LAST OBSERVED</th><th>DEMAND</th><th>CASH BALANCE</th><th>COVERAGE</th><th>STATUS</th></tr></thead>
                <tbody>{atms.slice(0, 8).map((atm) => (
                  <tr key={atm.atm_id}><td><span className="atm-id">{atm.atm_id}</span></td><td>{atm.location_type}</td><td className="date-cell">{formatDate(atm.last_observed_at)}</td><td className="amount-cell">{numberFormat.format(Math.round(atm.demand))}</td><td className="amount-cell">{numberFormat.format(Math.round(atm.balance))}</td><td><span className={`coverage-value ${atm.risk_level === "critical" ? "coverage-low" : ""}`}>{atm.coverage_ratio === null ? "—" : `${atm.coverage_ratio.toFixed(2)}×`}</span></td><td><span className={`status-pill ${atm.risk_level}`}><i />{atm.risk_level === "critical" ? "Below demand" : atm.risk_level === "watch" ? "Watch" : "Healthy"}</span></td></tr>
                ))}{atms.length === 0 && <tr><td className="empty-row" colSpan="7">No ATMs match your search and status filters.</td></tr>}</tbody>
              </table></div>
              <div className="table-footer"><span>Showing <strong>{Math.min(atms.length, 8)}</strong> of <strong>{data.atms.total}</strong> matching ATMs</span><span className="table-method">Coverage = observed balance ÷ next-day demand</span></div>
            </section>

            <section className="panel history-panel">
              <div className="panel-heading"><div><h2>Forecast audit history</h2><p>Saved forecasts and recommendations for traceability</p></div></div>
              {data.history.items.length ? <div className="table-scroll"><table><thead><tr><th>ATM ID</th><th>FORECAST DATE</th><th>DATA THROUGH</th><th>EST. DEMAND</th><th>REPLENISHMENT</th><th>STATUS</th></tr></thead><tbody>{data.history.items.map((item) => <tr key={item.id}><td><span className="atm-id">{item.atm_id}</span></td><td>{formatDate(item.forecast_date)}</td><td>{formatDate(item.source_data_as_of)}</td><td className="amount-cell">{numberFormat.format(item.predicted_demand)}</td><td className="amount-cell">{numberFormat.format(item.recommended_replenishment)}</td><td><span className={`status-pill ${item.risk_level}`}><i />{item.risk_level}</span></td></tr>)}</tbody></table></div> : <div className="history-empty">Forecasts generated from the panel above will appear here.</div>}
            </section>

            <footer className="page-footer"><span>ATM Cash Intelligence <span className="footer-divider">·</span> Bank Muscat</span><span><span className="status-dot" />Dataset range: 2022–2024 · cash units, not a currency measure</span></footer>
          </div>
        )}
      </main>
    </div>
  );
}

function App() {
  const [token, setToken] = useState(getAccessToken);
  const [user, setUser] = useState(null);
  const [checking, setChecking] = useState(Boolean(getAccessToken()));

  useEffect(() => {
    if (!token) {
      setUser(null);
      setChecking(false);
      return;
    }
    let active = true;
    apiRequest("/auth/me", { token })
      .then((authenticatedUser) => {
        if (active) setUser(authenticatedUser);
      })
      .catch(() => {
        clearAccessToken();
        if (active) {
          setToken(null);
          setUser(null);
        }
      })
      .finally(() => {
        if (active) setChecking(false);
      });
    return () => { active = false; };
  }, [token]);

  const logout = React.useCallback(() => {
    clearAccessToken();
    setToken(null);
    setUser(null);
  }, []);

  if (!token) return <Login onLogin={(newToken, authenticatedUser) => {
    saveAccessToken(newToken);
    setUser(authenticatedUser);
    setToken(newToken);
  }} />;
  if (checking || !user) return <div className="load-state" role="status">Verifying your session…</div>;
  return <Dashboard user={user} token={token} onLogout={logout} />;
}

export default App;
