import React, { useEffect, useMemo, useState } from "react";
import { useApp } from "../AppContext.jsx";
import DemandChart, { ChartLegend } from "../components/DemandChart.jsx";
import Sparkline from "../components/Sparkline.jsx";
import {
  Badge,
  Card,
  CardHeader,
  DataNotice,
  EmptyState,
  ErrorState,
  InfoHint,
  PageHeader,
  Progress,
  Segmented,
  Skeleton,
  StatusBadge,
} from "../components/ui.jsx";
import { cashByCity, cashSummary, mergeAtmRecords, riskCounts } from "../derive.js";
import {
  clamp,
  coverageLabel,
  formatCompact,
  formatDate,
  formatDateTime,
  formatNumber,
  formatPercent,
  formatRatio,
  riskLabel,
  sourceLabel,
} from "../format.js";
import { useApi } from "../hooks.js";
import { Icon } from "../icons.jsx";

const PERIOD_OPTIONS = [
  { label: "3M", value: 3 },
  { label: "6M", value: 6 },
  { label: "12M", value: 12 },
  { label: "24M", value: 24 },
];

function accuracyTrend(points = []) {
  const predicted = points.filter(
    (point) => Number.isFinite(point.observed) && Number.isFinite(point.prediction),
  );
  if (predicted.length < 4) return [];
  const bucketSize = Math.max(4, Math.ceil(predicted.length / 10));
  const buckets = [];
  for (let index = 0; index < predicted.length; index += bucketSize) {
    const bucket = predicted.slice(index, index + bucketSize);
    const actual = bucket.reduce((total, point) => total + point.observed, 0);
    const absoluteError = bucket.reduce(
      (total, point) => total + Math.abs(point.observed - point.prediction),
      0,
    );
    if (actual > 0) buckets.push(Math.max(0, 100 - (absoluteError / actual) * 100));
  }
  return buckets;
}

export default function Overview() {
  const {
    token,
    core,
    coreLoading,
    refreshCore,
    prefs,
    navigate,
  } = useApp();
  const [months, setMonths] = useState(prefs.defaultMonths || 12);
  const [scope, setScope] = useState("network");
  const [selectedAtm, setSelectedAtm] = useState("");
  const [cumulative, setCumulative] = useState(false);

  const records = useMemo(
    () => mergeAtmRecords(core.atms, core.metadata),
    [core.atms, core.metadata],
  );
  const summary = core.summary;
  const status = core.status;
  const model = summary?.model;

  useEffect(() => {
    if (!records.length) {
      if (selectedAtm) setSelectedAtm("");
      return;
    }
    if (!selectedAtm || !records.some((record) => record.atm_id === selectedAtm)) {
      const preferred = [...records].sort(
        (a, b) => (a.coverage_ratio ?? 99) - (b.coverage_ratio ?? 99),
      )[0];
      setSelectedAtm(preferred?.atm_id || records[0].atm_id);
    }
  }, [records, selectedAtm]);

  const seriesPath = scope === "atm" && selectedAtm
    ? `/analytics/demand-series?months=${months}&atm_id=${encodeURIComponent(selectedAtm)}`
    : `/analytics/demand-series?months=${months}`;
  const series = useApi(seriesPath, {
    token,
    enabled: Boolean(summary) && (scope === "network" || Boolean(selectedAtm)),
  });

  const points = series.data?.points || [];
  const nextForecast = series.data?.next_forecast || null;
  const accuracySeries = useMemo(() => accuracyTrend(points), [points]);
  const counts = useMemo(() => riskCounts(records), [records]);
  const networkCash = useMemo(() => cashSummary(records), [records]);
  const cities = useMemo(() => cashByCity(records), [records]);
  const selectedRecord = records.find((record) => record.atm_id === selectedAtm) || null;

  const scopeRecords = scope === "atm" && selectedRecord ? [selectedRecord] : records;
  const scopeCash = scope === "atm" ? cashSummary(scopeRecords) : networkCash;
  const topCities = cities.slice(0, 4);
  const units = (value) => (prefs.compactNumbers ? formatCompact(value) : formatNumber(value));
  const targetMet = model?.target_met;

  if (!summary && coreLoading) {
    return (
      <>
        <PageHeader
          eyebrow="CASH INTELLIGENCE"
          title="Cash Demand Overview"
          subtitle="Loading the latest forecast evaluation and ATM observations."
        />
        <div className="overview-skeleton-grid">
          <Skeleton style={{ height: 166 }} />
          <Skeleton style={{ height: 166 }} />
          <Skeleton style={{ height: 166 }} />
        </div>
        <Skeleton style={{ height: 430 }} />
      </>
    );
  }

  if (!summary) {
    return (
      <>
        <PageHeader
          eyebrow="CASH INTELLIGENCE"
          title="Cash Demand Overview"
          subtitle="Demand forecasting, cash planning and ATM operations."
        />
        <ErrorState
          message="The overview could not be loaded from the API."
          onRetry={refreshCore}
        />
      </>
    );
  }

  return (
    <>
      <PageHeader
        eyebrow="CASH INTELLIGENCE"
        title="Cash Demand Overview"
        subtitle="Demand forecasting, cash planning and ATM operations for the monitored network."
        meta={(
          <>
            <span className="meta-chip"><Icon name="calendar" size={13} />Data through {formatDate(summary.latest_dataset_date)}</span>
            <span className="meta-chip"><Icon name="database" size={13} />{formatDate(status?.dataset_start_date)} – {formatDate(status?.dataset_end_date)}</span>
            <Badge tone={status?.data_source === "synthetic_simulation" ? "warning" : "neutral"} dot>
              {sourceLabel(status?.data_source)}
            </Badge>
          </>
        )}
        actions={(
          <button
            type="button"
            className="button button-quiet"
            onClick={() => { refreshCore(); series.reload(); }}
          >
            <Icon name="refresh" size={15} />Refresh
          </button>
        )}
      />

      <section className="scope-bar" aria-label="Overview scope">
        <div className="scope-controls">
          <Segmented
            label="Analytics scope"
            value={scope}
            onChange={setScope}
            options={[{ value: "network", label: "Network" }, { value: "atm", label: "Selected ATM" }]}
          />
          {scope === "atm" && (
            <label className="select-shell">
              <Icon name="atm" size={15} />
              <select
                aria-label="Select ATM"
                value={selectedAtm}
                onChange={(event) => setSelectedAtm(event.target.value)}
              >
                {records.map((record) => (
                  <option key={record.atm_id} value={record.atm_id}>
                    {record.atm_id} · {record.location_name}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
        <div className="scope-note">
          <span className="status-dot is-live" />
          {scope === "network" ? `${records.length} ATMs in scope` : "Single-ATM demand view"}
          <span className="scope-divider" />
          Cash amounts are generic dataset units
        </div>
      </section>

      <section className="kpi-grid" aria-label="Key performance indicators">
        <Card className="kpi-card">
          <div className="kpi-top">
            <span className="kpi-icon is-blue"><Icon name="gauge" size={17} /></span>
            <span>Forecast accuracy</span>
            <InfoHint text="100 minus weighted absolute percentage error (WAPE) on the chronological holdout test window. Target is configured by the backend." />
          </div>
          <div className="kpi-value-row">
            <strong className="kpi-value">{formatPercent(model.accuracy_pct)}</strong>
            <span className="kpi-target">Target {formatPercent(model.target_accuracy_pct, 0)}</span>
          </div>
          <div className="kpi-visual">
            {accuracySeries.length > 1 ? (
              <Sparkline
                values={accuracySeries}
                tone={targetMet ? "positive" : "warning"}
                width={220}
                height={42}
                label="Rolling holdout accuracy trend"
              />
            ) : (
              <span className="chart-placeholder-note">Rolling accuracy appears when holdout predictions cover this window.</span>
            )}
          </div>
          <div className="kpi-foot">
            <span>100 − WAPE · chronological holdout</span>
            <Badge tone={targetMet ? "positive" : "warning"}>
              {targetMet === null || targetMet === undefined ? "Not evaluated" : targetMet ? "Target met" : "Below target"}
            </Badge>
          </div>
          <Progress
            value={clamp(model.accuracy_pct ?? 0, 0, 100)}
            tone={targetMet ? "positive" : "warning"}
            label="Forecast accuracy against 100 percent"
          />
        </Card>

        <Card className="kpi-card">
          <div className="kpi-top">
            <span className="kpi-icon is-amber"><Icon name="wallet" size={17} /></span>
            <span>Cash-out reduction</span>
            <InfoHint text="No cash-out backtesting endpoint or confirmed cash-out outcomes exist in the current backend, so this value is intentionally not estimated." />
          </div>
          <div className="kpi-value-row">
            <strong className="kpi-value is-muted">Not measured</strong>
            <span className="kpi-target">Target not configured</span>
          </div>
          <div className="kpi-visual kpi-visual-empty">
            <div className="unavailable-track">
              <span /><span /><span /><span /><span />
            </div>
            <span>Requires confirmed cash-out events and a backtesting service.</span>
          </div>
          <div className="kpi-foot">
            <span>No day-by-day backtest in this API</span>
            <Badge tone="warning" icon="alert">Unavailable</Badge>
          </div>
          <Progress value={0} tone="neutral" label="Cash-out reduction unavailable" />
        </Card>

        <Card className="kpi-card">
          <div className="kpi-top">
            <span className="kpi-icon is-red"><Icon name="alert" size={17} /></span>
            <span>ATMs at risk</span>
            <InfoHint text="Critical ATMs are flagged by the backend when observed cash balance is below the latest observed next-day demand." />
          </div>
          <div className="kpi-value-row">
            <strong className="kpi-value">{formatNumber(summary.at_risk_atms)}</strong>
            <span className="kpi-target">of {formatNumber(summary.atm_count)} ATMs</span>
          </div>
          <div className="risk-split" aria-hidden="true">
            <span className="is-critical" style={{ flex: Math.max(counts.critical, 0.001) }} />
            <span className="is-warning" style={{ flex: Math.max(counts.watch, 0.001) }} />
            <span className="is-positive" style={{ flex: Math.max(counts.healthy, 0.001) }} />
          </div>
          <div className="risk-legend">
            <span><i className="is-critical" />{counts.critical} critical</span>
            <span><i className="is-warning" />{counts.watch} warning</span>
            <span><i className="is-positive" />{counts.healthy} normal</span>
          </div>
          <div className="kpi-foot">
            <span>Backend risk rule · latest observation</span>
            <button type="button" className="text-link" onClick={() => navigate("alerts")}>
              Review alerts <Icon name="arrowRight" size={13} />
            </button>
          </div>
        </Card>
      </section>

      <Card className="model-strip">
        <div className="model-strip-main">
          <span className="model-pulse"><i /></span>
          <div>
            <strong>{String(model.model_name).replaceAll("-", " ")}</strong>
            <span>
              Holdout {formatDate(model.test_start_date)}–{formatDate(model.test_end_date)}
              {" · "}Trained {formatDateTime(model.trained_at)}
            </span>
          </div>
        </div>
        <div className="model-strip-stats">
          <span>MAE <strong>{units(model.mae)}</strong></span>
          <span>WAPE <strong>{formatPercent(model.wape_pct)}</strong></span>
          <span>Baseline WAPE <strong>{formatPercent(model.baseline_wape_pct)}</strong></span>
          <span>Train rows <strong>{formatNumber(model.training_rows)}</strong></span>
        </div>
        <Badge tone={status?.model_data_current ? "positive" : "warning"} dot>
          {status?.model_data_current ? "Model current" : "Retrain required"}
        </Badge>
      </Card>

      <section className="overview-grid">
        <Card className="chart-card">
          <CardHeader
            title={scope === "atm" && selectedRecord ? selectedRecord.atm_id : "All ATMs"}
            subtitle={scope === "atm" && selectedRecord
              ? `${selectedRecord.location_name} · ${selectedRecord.location_type}`
              : "Daily observed next-day demand across the monitored network"}
            action={(
              <div className="chart-actions">
                <Segmented
                  label="Chart time range"
                  value={months}
                  onChange={setMonths}
                  options={PERIOD_OPTIONS}
                />
                <Segmented
                  label="Daily or cumulative chart"
                  value={cumulative ? "cumulative" : "daily"}
                  onChange={(value) => setCumulative(value === "cumulative")}
                  options={[{ value: "daily", label: "Daily" }, { value: "cumulative", label: "Cumulative" }]}
                />
              </div>
            )}
          />

          <div className="chart-toolbar">
            <ChartLegend
              showPrediction={series.data?.prediction_available !== false}
              showForecast={Boolean(nextForecast)}
            />
            <span className="chart-unit">Cash units · {months} month window</span>
          </div>

          <div className={series.loading ? "chart-loading-wrap is-loading" : "chart-loading-wrap"}>
            {series.error && !series.data ? (
              <ErrorState message={series.error} onRetry={series.reload} compact />
            ) : series.loading && !series.data ? (
              <Skeleton className="chart-skeleton" />
            ) : (
              <DemandChart
                points={points}
                nextForecast={nextForecast}
                cumulative={cumulative}
              />
            )}
            {series.loading && series.data && (
              <span className="chart-refreshing" role="status">
                <span className="spinner" aria-hidden="true" />Updating
              </span>
            )}
          </div>

          <div className="chart-footer">
            <span><i className="footer-dot" />Observed: {formatNumber(series.data?.observations || 0)} daily records</span>
            <span>
              Predictions: {series.data?.prediction_available ? "chronological holdout" : "not available"}
            </span>
            <span>
              Next day: {nextForecast ? formatDate(nextForecast.forecast_date) : "not available"}
              {nextForecast && <Badge tone="warning" className="inline-badge">Simulation</Badge>}
            </span>
          </div>
        </Card>

        <Card className="cash-card">
          <CardHeader
            title={scope === "atm" && selectedRecord ? "ATM cash position" : "Cash on hand"}
            subtitle={scope === "atm" && selectedRecord
              ? selectedRecord.location_name
              : "Latest observation per ATM · generic cash units"}
            action={<Badge tone="neutral">Snapshot</Badge>}
          />

          {scope === "atm" && selectedRecord ? (
            <div className="cash-selected">
              <div className="cash-total">
                <span>Current cash balance</span>
                <strong>{units(scopeCash.balance)}</strong>
                <small>cash units</small>
              </div>
              <div className="cash-progress-block">
                <div className="cash-progress-labels">
                  <span>Fill level</span>
                  <strong>{formatPercent((scopeCash.utilization ?? 0) * 100, 0)}</strong>
                </div>
                <Progress value={(scopeCash.utilization ?? 0) * 100} tone={(scopeCash.utilization ?? 0) < 0.4 ? "critical" : "positive"} />
                <div className="cash-progress-labels is-subtle">
                  <span>Capacity {units(scopeCash.capacity)}</span>
                  <span>{coverageLabel(scopeCash.coverage)} cover</span>
                </div>
              </div>
              <div className="cash-mini-grid">
                <div><span>Next-day estimate</span><strong>{nextForecast ? units(nextForecast.predicted_demand) : "—"}</strong></div>
                <div><span>Observed demand</span><strong>{units(selectedRecord.demand)}</strong></div>
                <div><span>Cash cover</span><strong>{coverageLabel(selectedRecord.coverage_ratio)}</strong></div>
                <div><span>Status</span><StatusBadge risk={selectedRecord.risk_level} /></div>
              </div>
              <button type="button" className="button button-quiet cash-link" onClick={() => navigate("whatif", { atm_id: selectedRecord.atm_id })}>
                <Icon name="activity" size={14} />Open what-if scenario
              </button>
            </div>
          ) : (
            <>
              <div className="cash-total">
                <span>Total available cash</span>
                <strong>{units(networkCash.balance)}</strong>
                <small>cash units</small>
              </div>
              <div className="cash-progress-block">
                <div className="cash-progress-labels">
                  <span>Network fill level</span>
                  <strong>{formatPercent((networkCash.utilization ?? 0) * 100, 0)}</strong>
                </div>
                <Progress value={(networkCash.utilization ?? 0) * 100} tone={(networkCash.utilization ?? 0) < 0.4 ? "critical" : "positive"} />
                <div className="cash-progress-labels is-subtle">
                  <span>Capacity {units(networkCash.capacity)}</span>
                  <span>{coverageLabel(networkCash.coverage)} cover</span>
                </div>
              </div>

              <div className="cash-mini-grid">
                <div><span>ATMs</span><strong>{formatNumber(records.length)}</strong></div>
                <div><span>Total demand</span><strong>{units(networkCash.demand)}</strong></div>
                <div><span>Capacity use</span><strong>{formatRatio(networkCash.utilization)}</strong></div>
                <div><span>Source</span><strong className="is-small">{status?.data_source?.replaceAll("_", " ")}</strong></div>
              </div>

              <div className="cash-locations">
                <div className="cash-locations-head">
                  <span>Cash by city</span>
                  <span>{cities.length} locations</span>
                </div>
                {topCities.length ? topCities.map((city) => {
                  const share = networkCash.balance > 0 ? (city.balance / networkCash.balance) * 100 : 0;
                  return (
                    <div className="cash-city-row" key={city.city}>
                      <div className="cash-city-copy">
                        <span>{city.city}<small>{city.atms} ATMs</small></span>
                        <strong>{units(city.balance)}</strong>
                      </div>
                      <div className="cash-city-track"><span style={{ width: `${share}%` }} /></div>
                    </div>
                  );
                }) : <EmptyState icon="pin" title="No location records" />}
              </div>
            </>
          )}

          <div className="cash-card-foot">
            <Icon name="info" size={14} />
            <span>Cover = balance ÷ observed next-day demand. Not a currency measure.</span>
          </div>
        </Card>
      </section>

      <DataNotice
        tone={status?.data_source === "synthetic_simulation" ? "warning" : "info"}
        title={status?.data_source === "synthetic_simulation" ? "Synthetic demonstration data" : "Operational data context"}
      >
        {status?.data_source === "synthetic_simulation"
          ? "Observations, model evaluation and scenario estimates are generated from reproducible synthetic records. They are not Bank Muscat operational data and do not confirm live cash-out or delivery outcomes."
          : `Analytics are read from PostgreSQL (${status?.data_source}). Next-day estimates are labelled simulation and are not dispatch instructions.`}
      </DataNotice>
    </>
  );
}
