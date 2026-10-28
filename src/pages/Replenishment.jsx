import React, { useEffect, useMemo, useRef, useState } from "react";
import { useApp } from "../AppContext.jsx";
import {
  Badge,
  Card,
  CardHeader,
  DataNotice,
  EmptyState,
  ErrorState,
  PageHeader,
  Skeleton,
  StatusBadge,
} from "../components/ui.jsx";
import {
  classNames,
  coverageLabel,
  formatDate,
  formatNumber,
  formatPercent,
} from "../format.js";
import { useApi } from "../hooks.js";
import { Icon } from "../icons.jsx";
import { apiRequest } from "../data.js";

const CAPACITY_PRESETS = [100_000, 250_000, 500_000];

function riskCopy(risk, recommended) {
  if (risk === "critical") return "Stockout risk imminent";
  if (risk === "watch") return "Urgent refill required";
  if (recommended > 0) return "Planned refill";
  return "No refill needed";
}

export default function Replenishment() {
  const { token, core, coreLoading, refreshCore, navigate } = useApp();
  const [selected, setSelected] = useState([]);
  const [tripCapacity, setTripCapacity] = useState(150_000);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState("");
  const initialized = useRef("");

  const scenario = useApi("/forecasts/scenario", {
    token,
    method: "POST",
    body: {},
    enabled: Boolean(core.summary),
  });
  const history = useApi("/forecasts?limit=8", {
    token,
    enabled: Boolean(core.summary),
  });

  const items = scenario.data?.items || [];
  const recommendations = useMemo(
    () => items
      .filter((item) => item.recommended_replenishment > 0)
      .sort((a, b) => {
        const order = { critical: 0, watch: 1, healthy: 2 };
        return (order[a.risk_level] ?? 3) - (order[b.risk_level] ?? 3)
          || (a.cash_cover_days ?? 999) - (b.cash_cover_days ?? 999);
      }),
    [items],
  );

  useEffect(() => {
    const key = recommendations.map((item) => item.atm_id).join(",");
    if (!key || initialized.current === key) return;
    initialized.current = key;
    setSelected(
      recommendations
        .filter((item) => item.risk_level === "critical")
        .map((item) => item.atm_id),
    );
  }, [recommendations]);

  useEffect(() => {
    setSelected((current) => current.filter((atmId) => items.some((item) => item.atm_id === atmId)));
  }, [items]);

  const selectedSet = useMemo(() => new Set(selected), [selected]);
  const selectedItems = useMemo(
    () => recommendations.filter((item) => selectedSet.has(item.atm_id)),
    [recommendations, selectedSet],
  );
  const totals = useMemo(
    () => selectedItems.reduce(
      (accumulator, item) => {
        accumulator.refill += item.recommended_replenishment;
        accumulator.balance += item.current_balance;
        accumulator.critical += item.risk_level === "critical" ? 1 : 0;
        return accumulator;
      },
      { refill: 0, balance: 0, critical: 0 },
    ),
    [selectedItems],
  );

  const capacity = Number.isFinite(tripCapacity) && tripCapacity > 0 ? tripCapacity : 0;
  const trips = capacity > 0 && totals.refill > 0 ? Math.ceil(totals.refill / capacity) : 0;
  const lastTripLoad = trips > 0 ? totals.refill - (trips - 1) * capacity : 0;
  const utilization = capacity > 0 && totals.refill > 0
    ? Math.min(100, (totals.refill / (trips * capacity)) * 100)
    : 0;

  const suggestedIds = recommendations
    .filter((item) => item.risk_level === "critical" || item.risk_level === "watch")
    .map((item) => item.atm_id);

  function toggle(atmId) {
    setSelected((current) => (current.includes(atmId)
      ? current.filter((value) => value !== atmId)
      : [...current, atmId]));
  }

  function selectSuggested() {
    setSelected(suggestedIds);
  }

  async function exportPlan() {
    setExportError("");
    setExporting(true);
    try {
      await apiRequest("/auth/me", { token });
      const header = [
        "atm_id",
        "location",
        "risk_level",
        "base_forecast",
        "current_balance",
        "cash_cover_days",
        "recommended_replenishment",
        "forecast_date",
        "simulation",
      ];
      const lines = selectedItems.map((item) => [
        item.atm_id,
        `"${String(item.location_name || item.location_type).replaceAll("\"", "\"\"")}"`,
        item.risk_level,
        item.base_forecast,
        item.current_balance,
        item.cash_cover_days ?? "",
        item.recommended_replenishment,
        item.forecast_date,
        "simulation",
      ].join(","));
      const csv = [header.join(","), ...lines].join("\n");
      const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `cashcast-simulated-replenishment-${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (error) {
      setExportError(error?.message || "The plan could not be exported.");
    } finally {
      setExporting(false);
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="OPERATIONS"
        title="Replenishment plan"
        subtitle="Recommendations and simulated dispatches supplied by the API."
        meta={(
          <>
            <span className="meta-chip"><Icon name="calendar" size={13} />Observation {formatDate(items[0]?.source_data_as_of || core.summary?.latest_dataset_date)}</span>
            <span className="meta-chip"><Icon name="truck" size={13} />{recommendations.length} recommended refills</span>
            <Badge tone="warning" dot>Simulated dispatch</Badge>
          </>
        )}
        actions={(
          <button
            type="button"
            className="button button-quiet"
            onClick={() => setSelected([])}
            disabled={!selected.length}
          >
            <Icon name="x" size={15} />Clear selections
          </button>
        )}
      />

      {scenario.error && (
        <ErrorState
          message={scenario.error}
          onRetry={() => { refreshCore(); scenario.reload(); }}
        />
      )}

      <section className="replenishment-grid">
        <Card className="replenish-list-card">
          <CardHeader
            title="ATMs to replenish"
            subtitle={scenario.data
              ? `${recommendations.length} of ${items.length} ATMs have a positive refill recommendation`
              : "Loading recommendations from the scenario API"}
            action={(
              <div className="header-actions">
                <button
                  type="button"
                  className="button button-quiet button-small"
                  onClick={selectSuggested}
                  disabled={!suggestedIds.length}
                >
                  <Icon name="check" size={14} />Select suggested
                </button>
                <span className="selection-pill">{selected.length} selected</span>
              </div>
            )}
          />

          <div className="replenish-list">
            {!scenario.data && (scenario.loading || coreLoading) ? (
              Array.from({ length: 6 }).map((_, index) => (
                <div className="replenish-row is-skeleton" key={`replenish-skeleton-${index}`}>
                  <Skeleton style={{ height: 44 }} />
                </div>
              ))
            ) : recommendations.length ? (
              recommendations.map((item) => {
                const checked = selectedSet.has(item.atm_id);
                return (
                  <label
                    key={item.atm_id}
                    className={classNames("replenish-row", checked && "is-selected")}
                  >
                    <input
                      type="checkbox"
                      className="row-checkbox"
                      checked={checked}
                      onChange={() => toggle(item.atm_id)}
                      aria-label={`Select ${item.atm_id} for replenishment`}
                    />
                    <span className="replenish-copy">
                      <span className="replenish-title">
                        <strong>{item.atm_id}</strong>
                        <StatusBadge risk={item.risk_level} label={riskCopy(item.risk_level, item.recommended_replenishment)} />
                      </span>
                      <span className="replenish-sub">{item.location_name || item.location_type}</span>
                      <span className="replenish-metrics">
                        <span>Cash <strong>{formatNumber(item.current_balance)}</strong></span>
                        <span>Refill <strong>{formatNumber(item.recommended_replenishment)}</strong></span>
                        <span>Cover <strong>{coverageLabel(item.cash_cover_days)}</strong></span>
                      </span>
                    </span>
                    <span className="replenish-amount">
                      +{formatNumber(item.recommended_replenishment)}
                      <small>cash units</small>
                    </span>
                  </label>
                );
              })
            ) : scenario.data ? (
              <EmptyState
                icon="shield"
                title="No refills recommended"
                message="Every ATM in scope has enough modelled cash cover for the next-day estimate."
              />
            ) : (
              <EmptyState
                icon="truck"
                title="Recommendations unavailable"
                message="Scenario estimates could not be loaded from the API."
              />
            )}
          </div>

          <div className="list-foot">
            <span>
              Refill = modelled upper bound − current balance, capped by ATM capacity
            </span>
            <button type="button" className="text-link" onClick={() => navigate("whatif")}>
              Adjust scenario <Icon name="arrowRight" size={13} />
            </button>
          </div>
        </Card>

        <div className="replenish-side">
          <Card className="dispatch-card">
            <CardHeader
              title="Dispatch estimate"
              subtitle="Simulation only · no delivery has been scheduled"
              action={<Badge tone="warning">Draft</Badge>}
            />

            <div className="field-group">
              <label className="field-label" htmlFor="trip-capacity">Cash per trip (vehicle capacity)</label>
              <div className="number-shell">
                <Icon name="truck" size={15} />
                <input
                  id="trip-capacity"
                  type="number"
                  min={1}
                  step={10_000}
                  inputMode="numeric"
                  value={Number.isFinite(tripCapacity) ? tripCapacity : ""}
                  onChange={(event) => setTripCapacity(event.target.value === "" ? 0 : Number(event.target.value))}
                />
                <span>units</span>
              </div>
              <div className="quick-steps">
                {CAPACITY_PRESETS.map((preset) => (
                  <button
                    type="button"
                    key={preset}
                    className={classNames("chip-button", tripCapacity === preset && "is-selected")}
                    aria-pressed={tripCapacity === preset}
                    onClick={() => setTripCapacity(preset)}
                  >
                    {formatNumber(preset)}
                  </button>
                ))}
              </div>
            </div>

            <div className="dispatch-stats">
              <div>
                <span>Selected ATMs</span>
                <strong>{selectedItems.length}</strong>
              </div>
              <div>
                <span>Refill total</span>
                <strong>{formatNumber(totals.refill)}</strong>
                <small>cash units</small>
              </div>
              <div className="is-highlight">
                <span>Estimated trips</span>
                <strong>{capacity > 0 ? trips : "—"}</strong>
                <small>{capacity > 0 && trips > 0 ? `${formatPercent(utilization, 0)} average load` : "set a capacity"}</small>
              </div>
            </div>

            <div className="trip-load">
              <div className="trip-load-head">
                <span>Trip load</span>
                <span>{capacity > 0 ? `${formatNumber(lastTripLoad)} on the final trip` : "—"}</span>
              </div>
              <div className="trip-load-track" aria-hidden="true">
                <span style={{ width: `${capacity > 0 ? Math.min(100, (lastTripLoad / capacity) * 100) : 0}%` }} />
              </div>
              <p className="field-help">
                Based on {formatNumber(totals.refill)} units across {selectedItems.length} ATMs
                {totals.critical ? `, including ${totals.critical} critical` : ""}.
              </p>
            </div>

            <div className="dispatch-actions">
              <button
                type="button"
                className="button button-primary"
                onClick={exportPlan}
                disabled={!selectedItems.length || exporting}
              >
                {exporting
                  ? <span className="spinner spinner-on-dark" aria-hidden="true" />
                  : <Icon name="download" size={15} />}
                {exporting ? "Preparing…" : "Export plan (CSV)"}
              </button>
              <button
                type="button"
                className="button button-quiet"
                onClick={selectSuggested}
                disabled={!suggestedIds.length}
              >
                <Icon name="check" size={15} />Select suggested
              </button>
            </div>
            {exportError && <div className="form-error" role="alert">{exportError}</div>}

            <DataNotice tone="warning" icon="info">
              Dispatch execution is not persisted by this backend. Exporting produces a simulated
              planning file only — no vehicle has been routed and no cash has been released.
            </DataNotice>
          </Card>

          <Card className="dispatch-history-card">
            <CardHeader
              title="Recent forecast audit"
              subtitle="Persisted forecast records · not dispatch records"
              action={(
                <button
                  type="button"
                  className="icon-button"
                  aria-label="Refresh forecast audit"
                  onClick={history.reload}
                  disabled={history.loading}
                >
                  <Icon name="refresh" size={15} />
                </button>
              )}
            />

            {history.error ? (
              <ErrorState message={history.error} onRetry={history.reload} compact />
            ) : history.loading && !history.data ? (
              <div className="history-skeletons">
                <Skeleton style={{ height: 16 }} />
                <Skeleton style={{ height: 16 }} />
                <Skeleton style={{ height: 16 }} />
              </div>
            ) : history.data?.items?.length ? (
              <ul className="history-list">
                {history.data.items.slice(0, 6).map((record) => (
                  <li key={record.id}>
                    <span className="history-date">{formatDate(record.forecast_date)}</span>
                    <span className="history-copy">
                      <strong>{record.atm_id}</strong>
                      <small>{formatNumber(record.predicted_demand)} predicted units</small>
                    </span>
                    <StatusBadge risk={record.risk_level} />
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState
                icon="receipt"
                title="No forecast records"
                message="The forecast audit log is empty for this database."
              />
            )}
            <div className="history-foot">
              <span>{history.data ? `${formatNumber(history.data.total)} records stored` : "—"}</span>
              <span className="muted">Forecast audit only</span>
            </div>
          </Card>
        </div>
      </section>

      <DataNotice tone="warning" title="Simulated replenishment planning">
        Refill amounts and trip counts are derived from labelled simulation estimates. They are not
        approved cash orders, and the backend does not store acknowledgements, dispatches or
        delivery outcomes.
      </DataNotice>
    </>
  );
}
