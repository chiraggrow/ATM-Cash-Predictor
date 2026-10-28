import React, { useMemo, useState } from "react";
import { useApp } from "../AppContext.jsx";
import {
  Badge,
  Card,
  CardHeader,
  DataNotice,
  EmptyState,
  ErrorState,
  PageHeader,
  Segmented,
  Skeleton,
} from "../components/ui.jsx";
import { buildAlerts, mergeAtmRecords, scenarioIndex } from "../derive.js";
import {
  classNames,
  coverageLabel,
  formatDate,
  formatNumber,
} from "../format.js";
import { useApi, useStoredSet } from "../hooks.js";
import { Icon } from "../icons.jsx";

const FILTERS = [
  { value: "open", label: "Open" },
  { value: "critical", label: "Critical" },
  { value: "high", label: "High" },
  { value: "acknowledged", label: "Acknowledged" },
  { value: "dismissed", label: "Dismissed" },
];

function SeverityIcon({ severity }) {
  return (
    <span className={classNames("alert-severity-icon", severity === "Critical" ? "is-critical" : "is-high")}>
      <Icon name={severity === "Critical" ? "alert" : "bell"} size={18} />
    </span>
  );
}

export default function Alerts() {
  const { token, core, coreLoading, refreshCore } = useApp();
  const [filter, setFilter] = useState("open");
  const acknowledged = useStoredSet("cashcast.alerts.acknowledged.v1");
  const dismissed = useStoredSet("cashcast.alerts.dismissed.v1");

  const scenario = useApi("/forecasts/scenario", {
    token,
    method: "POST",
    body: {},
    enabled: Boolean(core.summary),
  });

  const records = useMemo(
    () => mergeAtmRecords(core.atms, core.metadata),
    [core.atms, core.metadata],
  );
  const alerts = useMemo(
    () => buildAlerts(records, scenario.data),
    [records, scenario.data],
  );
  const scenarioMap = useMemo(() => scenarioIndex(scenario.data), [scenario.data]);

  const annotated = useMemo(
    () => alerts.map((alert) => ({
      ...alert,
      isAcknowledged: acknowledged.has(alert.id),
      isDismissed: dismissed.has(alert.id),
    })),
    [alerts, acknowledged, dismissed],
  );

  const counts = useMemo(() => ({
    open: annotated.filter((alert) => !alert.isAcknowledged && !alert.isDismissed).length,
    critical: annotated.filter((alert) => alert.severity === "Critical" && !alert.isDismissed).length,
    high: annotated.filter((alert) => alert.severity === "High" && !alert.isDismissed).length,
    acknowledged: annotated.filter((alert) => alert.isAcknowledged && !alert.isDismissed).length,
    dismissed: annotated.filter((alert) => alert.isDismissed).length,
  }), [annotated]);

  const visible = useMemo(() => {
    if (filter === "dismissed") return annotated.filter((alert) => alert.isDismissed);
    if (filter === "acknowledged") {
      return annotated.filter((alert) => alert.isAcknowledged && !alert.isDismissed);
    }
    if (filter === "critical") {
      return annotated.filter((alert) => alert.severity === "Critical" && !alert.isDismissed);
    }
    if (filter === "high") {
      return annotated.filter((alert) => alert.severity === "High" && !alert.isDismissed);
    }
    return annotated.filter((alert) => !alert.isDismissed);
  }, [annotated, filter]);

  const anyLocalState = acknowledged.values.length > 0 || dismissed.values.length > 0;

  return (
    <>
      <PageHeader
        eyebrow="MONITORING"
        title="Alerts"
        subtitle="API-generated cash-cover and replenishment alerts · simulation."
        meta={(
          <>
            <span className="meta-chip"><Icon name="bell" size={13} />{counts.open} open</span>
            <span className="meta-chip"><Icon name="alert" size={13} />{counts.critical} critical</span>
            <Badge tone="warning" dot>Evaluation data {formatDate(core.summary?.latest_dataset_date)}</Badge>
          </>
        )}
        actions={anyLocalState ? (
          <button
            type="button"
            className="button button-quiet"
            onClick={() => { acknowledged.setValues([]); dismissed.setValues([]); }}
          >
            <Icon name="refresh" size={15} />Reset local alert state
          </button>
        ) : null}
      />

      <div className="alert-summary-grid">
        <button
          type="button"
          className={classNames("alert-summary", "is-critical", filter === "critical" && "is-active")}
          onClick={() => setFilter("critical")}
        >
          <span>Critical</span>
          <strong>{counts.critical}</strong>
          <small>Immediate cash cover risk</small>
        </button>
        <button
          type="button"
          className={classNames("alert-summary", "is-high", filter === "high" && "is-active")}
          onClick={() => setFilter("high")}
        >
          <span>High</span>
          <strong>{counts.high}</strong>
          <small>Refill within the next cycle</small>
        </button>
        <button
          type="button"
          className={classNames("alert-summary", "is-neutral", filter === "acknowledged" && "is-active")}
          onClick={() => setFilter("acknowledged")}
          disabled={!counts.acknowledged}
        >
          <span>Acknowledged</span>
          <strong>{counts.acknowledged}</strong>
          <small>Local browser state only</small>
        </button>
        <button
          type="button"
          className={classNames("alert-summary", "is-muted", filter === "dismissed" && "is-active")}
          onClick={() => setFilter("dismissed")}
          disabled={!counts.dismissed}
        >
          <span>Dismissed</span>
          <strong>{counts.dismissed}</strong>
          <small>Recoverable locally</small>
        </button>
      </div>

      <Card className="alerts-card">
        <CardHeader
          title="Cash-cover alerts"
          subtitle="Critical = balance below the modelled lower bound · High = balance below the upper bound"
          action={(
            <div className="header-actions">
              <Segmented
                label="Alert filter"
                value={filter}
                onChange={setFilter}
                options={FILTERS}
              />
              <button
                type="button"
                className="icon-button"
                aria-label="Refresh alerts"
                onClick={() => { refreshCore(); scenario.reload(); }}
                disabled={scenario.loading}
              >
                <Icon name="refresh" size={15} />
              </button>
            </div>
          )}
        />

        {scenario.error && !scenario.data && (
          <ErrorState
            message={`Alert recommendations could not be loaded: ${scenario.error}`}
            onRetry={scenario.reload}
            compact
          />
        )}

        <div className="alert-list">
          {scenario.loading && !scenario.data ? (
            Array.from({ length: 5 }).map((_, index) => (
              <div className="alert-row is-skeleton" key={`alert-skeleton-${index}`}>
                <Skeleton style={{ height: 56 }} />
              </div>
            ))
          ) : visible.length ? (
            visible.map((alert) => {
              const estimate = scenarioMap.get(alert.atm_id);
              const refill = estimate?.recommended_replenishment ?? alert.suggested_refill;
              return (
                <article
                  key={alert.id}
                  className={classNames(
                    "alert-row",
                    alert.severity === "Critical" ? "is-critical" : "is-high",
                    alert.isAcknowledged && "is-acknowledged",
                    alert.isDismissed && "is-dismissed",
                  )}
                >
                  <SeverityIcon severity={alert.severity} />
                  <div className="alert-main">
                    <div className="alert-title-line">
                      <Badge tone={alert.severity === "Critical" ? "critical" : "warning"}>
                        {alert.severity}
                      </Badge>
                      <strong>{alert.atm_id}</strong>
                      {alert.isAcknowledged && (
                        <Badge tone="neutral" icon="check">Acknowledged</Badge>
                      )}
                      {alert.isDismissed && (
                        <Badge tone="neutral" icon="x">Dismissed</Badge>
                      )}
                    </div>
                    <p className="alert-location">
                      <Icon name="pin" size={13} />
                      {alert.location_name} · {alert.location_type}
                      {alert.city ? ` · ${alert.city}` : ""}
                    </p>
                    <div className="alert-metrics">
                      <span>
                        Cash cover
                        <strong>{coverageLabel(alert.coverage)}</strong>
                      </span>
                      <span>
                        Current cash
                        <strong>{formatNumber(alert.cash)}</strong>
                      </span>
                      <span>
                        Suggested refill
                        <strong>{refill === null || refill === undefined ? "—" : formatNumber(refill)}</strong>
                      </span>
                      <span>
                        Modelled demand
                        <strong>{formatNumber(alert.demand)}</strong>
                      </span>
                    </div>
                    {estimate && (
                      <p className="alert-estimate">
                        Scenario bounds {formatNumber(estimate.lower_bound)}–{formatNumber(estimate.upper_bound)} units
                        · estimate for {formatDate(estimate.forecast_date)}
                        <span className="badge badge-warning inline-badge">Simulation</span>
                      </p>
                    )}
                  </div>
                  <div className="alert-actions">
                    {alert.isDismissed ? (
                      <button
                        type="button"
                        className="button button-quiet button-small"
                        onClick={() => dismissed.remove(alert.id)}
                      >
                        <Icon name="refresh" size={14} />Restore
                      </button>
                    ) : (
                      <>
                        <button
                          type="button"
                          className={classNames("button", "button-small", alert.isAcknowledged ? "button-quiet" : "button-soft")}
                          aria-pressed={alert.isAcknowledged}
                          onClick={() => acknowledged.toggle(alert.id)}
                        >
                          <Icon name="check" size={14} />
                          {alert.isAcknowledged ? "Acknowledged" : "Acknowledge"}
                        </button>
                        <button
                          type="button"
                          className="icon-button alert-dismiss"
                          aria-label={`Dismiss alert for ${alert.atm_id}`}
                          title="Dismiss locally"
                          onClick={() => dismissed.add(alert.id)}
                        >
                          <Icon name="x" size={15} />
                        </button>
                      </>
                    )}
                  </div>
                </article>
              );
            })
          ) : (
            <EmptyState
              icon={filter === "dismissed" ? "x" : "shield"}
              title={filter === "dismissed" ? "No dismissed alerts" : "Nothing in this view"}
              message={filter === "acknowledged"
                ? "Acknowledged alerts appear here after you mark them in this browser."
                : "No ATMs currently match this alert filter."}
              action={filter !== "open" ? (
                <button type="button" className="button button-quiet" onClick={() => setFilter("open")}>
                  Show open alerts
                </button>
              ) : null}
            />
          )}
        </div>

        <div className="alerts-foot">
          <span>
            Alerts derived from <code>/api/v1/atms</code> risk levels and{" "}
            <code>/api/v1/forecasts/scenario</code> bounds
          </span>
          <button type="button" className="text-link" onClick={scenario.reload} disabled={scenario.loading}>
            Recalculate <Icon name="refresh" size={12} />
          </button>
        </div>
      </Card>

      <DataNotice tone="warning" title="Acknowledgement is local to this browser">
        The current backend has no alert persistence endpoints. Acknowledge and dismiss actions are
        stored in this browser only, so they will not appear for other users, other devices, or a
        cleared browser profile. Alerts themselves are derived from synthetic demonstration data.
      </DataNotice>
    </>
  );
}
