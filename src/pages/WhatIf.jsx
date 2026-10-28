import React, { useEffect, useMemo, useState } from "react";
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
  StatusBadge,
} from "../components/ui.jsx";
import { mergeAtmRecords } from "../derive.js";
import {
  classNames,
  coverageLabel,
  formatDate,
  formatNumber,
  formatPercent,
} from "../format.js";
import { useApi, useDebouncedValue } from "../hooks.js";
import { Icon } from "../icons.jsx";

const SLIDER_MIN = -30;
const SLIDER_MAX = 30;
const QUICK_STEPS = [-20, -10, 0, 10, 20];

function Toggle({ checked, onChange, label, description, id }) {
  return (
    <label className="toggle-row" htmlFor={id}>
      <span className="toggle-copy">
        <strong>{label}</strong>
        <span>{description}</span>
      </span>
      <input
        id={id}
        type="checkbox"
        className="toggle-input"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span className="toggle-track" aria-hidden="true"><i /></span>
    </label>
  );
}

function riskCopy(risk) {
  if (risk === "critical") return "Stockout risk imminent";
  if (risk === "watch") return "Urgent refill required";
  return "Cover sufficient";
}

export default function WhatIf() {
  const { token, core, coreLoading, refreshCore, prefs, params, navigate } = useApp();
  const records = useMemo(
    () => mergeAtmRecords(core.atms, core.metadata),
    [core.atms, core.metadata],
  );

  const [festival, setFestival] = useState(false);
  const [holiday, setHoliday] = useState(false);
  const [adjustment, setAdjustment] = useState(0);
  const [atmFilter, setAtmFilter] = useState(params.atm_id || "");
  const [sortKey, setSortKey] = useState("impact");

  useEffect(() => {
    setAtmFilter(params.atm_id || "");
  }, [params.atm_id]);

  useEffect(() => {
    if (atmFilter && !records.some((record) => record.atm_id === atmFilter)) {
      setAtmFilter("");
    }
  }, [records, atmFilter]);

  const debouncedAdjustment = useDebouncedValue(adjustment, 320);
  const body = useMemo(
    () => ({
      festival,
      holiday,
      adjustment_pct: debouncedAdjustment,
      atm_ids: atmFilter ? [atmFilter] : null,
    }),
    [festival, holiday, debouncedAdjustment, atmFilter],
  );

  const scenario = useApi("/forecasts/scenario", {
    token,
    method: "POST",
    body,
    enabled: Boolean(core.summary),
  });

  const pending = adjustment !== debouncedAdjustment
    || scenario.loading
    || (scenario.data && (
      scenario.data.festival !== festival
      || scenario.data.holiday !== holiday
    ));

  const items = scenario.data?.items || [];
  const totals = useMemo(() => {
    return items.reduce(
      (accumulator, item) => {
        accumulator.base += item.base_forecast;
        accumulator.adjusted += item.adjusted_forecast;
        accumulator.balance += item.current_balance;
        accumulator.refill += item.recommended_replenishment;
        if (item.risk_level === "critical") accumulator.critical += 1;
        else if (item.risk_level === "watch") accumulator.watch += 1;
        return accumulator;
      },
      { base: 0, adjusted: 0, balance: 0, refill: 0, critical: 0, watch: 0 },
    );
  }, [items]);

  const rows = useMemo(() => {
    const sorted = [...items];
    sorted.sort((a, b) => {
      if (sortKey === "cover") {
        return (a.cash_cover_days ?? 999) - (b.cash_cover_days ?? 999);
      }
      if (sortKey === "risk") {
        const order = { critical: 0, watch: 1, healthy: 2 };
        return (order[a.risk_level] ?? 3) - (order[b.risk_level] ?? 3);
      }
      return b.adjusted_forecast - b.base_forecast - (a.adjusted_forecast - a.base_forecast);
    });
    return sorted;
  }, [items, sortKey]);

  const delta = totals.adjusted - totals.base;
  const deltaPercent = totals.base > 0 ? (delta / totals.base) * 100 : 0;
  const source = scenario.data?.data_source || core.status?.data_source;
  const forecastDate = items[0]?.forecast_date;

  function reset() {
    setFestival(false);
    setHoliday(false);
    setAdjustment(0);
    setAtmFilter("");
    if (params.atm_id) navigate("whatif");
  }

  const assumptionsActive = festival || holiday || adjustment !== 0 || Boolean(atmFilter);

  return (
    <>
      <PageHeader
        eyebrow="SCENARIO LAB"
        title="What-if forecast"
        subtitle="Model estimates from the API with your selected calendar assumptions."
        meta={(
          <>
            <span className="meta-chip"><Icon name="calendar" size={13} />Estimate date {formatDate(forecastDate)}</span>
            <span className="meta-chip"><Icon name="cpu" size={13} />{scenario.data?.forecast_mode || core.status?.forecast_mode || "—"} mode</span>
            <Badge tone="warning" dot>Simulation</Badge>
          </>
        )}
        actions={(
          <button
            type="button"
            className="button button-quiet"
            onClick={reset}
            disabled={!assumptionsActive}
          >
            <Icon name="refresh" size={15} />Reset assumptions
          </button>
        )}
      />

      {scenario.error && !scenario.data && (
        <ErrorState
          message={scenario.error}
          onRetry={() => { refreshCore(); scenario.reload(); }}
        />
      )}

      <section className="whatif-grid">
        <Card className="assumptions-card">
          <CardHeader
            eyebrow="ASSUMPTIONS"
            title="Scenario inputs"
            subtitle="Calendar flags are applied to the model inputs; the percentage is applied after inference."
          />

          <div className="assumption-block">
            <span className="field-label">Calendar assumptions</span>
            <Toggle
              id="scenario-festival"
              checked={festival}
              onChange={setFestival}
              label="Festival tomorrow"
              description="Sets the model's festival input."
            />
            <Toggle
              id="scenario-holiday"
              checked={holiday}
              onChange={setHoliday}
              label="Public holiday"
              description="Sets the model's holiday input."
            />
          </div>

          <div className="assumption-block">
            <div className="slider-head">
              <span className="field-label" id="adjustment-label">Demand adjustment</span>
              <output
                className={classNames("slider-value", adjustment > 0 && "is-up", adjustment < 0 && "is-down")}
                htmlFor="demand-adjustment"
              >
                {adjustment > 0 ? "+" : ""}{adjustment}%
              </output>
            </div>
            <input
              id="demand-adjustment"
              className="range-input"
              type="range"
              min={SLIDER_MIN}
              max={SLIDER_MAX}
              step={1}
              value={adjustment}
              aria-labelledby="adjustment-label"
              aria-valuetext={`${adjustment} percent`}
              onChange={(event) => setAdjustment(Number(event.target.value))}
              style={{
                "--range-progress": `${((adjustment - SLIDER_MIN) / (SLIDER_MAX - SLIDER_MIN)) * 100}%`,
              }}
            />
            <div className="range-scale" aria-hidden="true">
              <span>−30%</span>
              <span>0%</span>
              <span>+30%</span>
            </div>
            <div className="quick-steps" role="group" aria-label="Adjustment presets">
              {QUICK_STEPS.map((step) => (
                <button
                  type="button"
                  key={step}
                  className={classNames("chip-button", adjustment === step && "is-selected")}
                  aria-pressed={adjustment === step}
                  onClick={() => setAdjustment(step)}
                >
                  {step > 0 ? "+" : ""}{step}%
                </button>
              ))}
            </div>
          </div>

          <div className="assumption-block">
            <label className="field-label" htmlFor="scenario-atm-filter">ATM scope</label>
            <div className="select-shell">
              <Icon name="atm" size={15} />
              <select
                id="scenario-atm-filter"
                value={atmFilter}
                onChange={(event) => setAtmFilter(event.target.value)}
              >
                <option value="">All ATMs ({records.length})</option>
                {records.map((record) => (
                  <option key={record.atm_id} value={record.atm_id}>
                    {record.atm_id} · {record.location_name}
                  </option>
                ))}
              </select>
            </div>
            <p className="field-help">
              Applies the same assumptions to every ATM in scope and refreshes the estimates below.
            </p>
          </div>

          <div className={classNames("scenario-result", pending && "is-pending")} aria-live="polite">
            <div className="scenario-result-head">
              <span>Scenario demand</span>
              {pending ? (
                <span className="inline-status"><span className="spinner" aria-hidden="true" />Estimating</span>
              ) : (
                <span className="inline-status is-ready"><Icon name="check" size={12} />Updated</span>
              )}
            </div>
            <strong>{scenario.data ? formatNumber(totals.adjusted) : "—"}</strong>
            <div className="scenario-result-foot">
              <span>Base {scenario.data ? formatNumber(totals.base) : "—"}</span>
              <span className={classNames(delta > 0 && "is-up", delta < 0 && "is-down")}>
                {delta > 0 ? "+" : ""}{scenario.data ? formatNumber(delta) : "—"}
                {scenario.data ? ` (${deltaPercent > 0 ? "+" : ""}${formatPercent(deltaPercent)})` : ""}
              </span>
            </div>
          </div>

          {scenario.data && (festival || holiday) && delta === 0 && (
            <p className="field-help" role="status">
              The calendar flags were applied to the model inputs, but this model produced no
              measurable change for the current dataset. The flags are still included in the
              scenario request.
            </p>
          )}

          <DataNotice tone="warning" icon="info">
            Scenario outputs are estimates, labeled as simulation. The percentage adjustment is
            applied after model inference and is not an observed demand change.
          </DataNotice>
        </Card>

        <Card className="scenario-table-card">
          <CardHeader
            title="Adjusted ATM demand"
            subtitle={(
              <>
                {scenario.data ? `${items.length} ATMs` : "Awaiting scenario"}
                {atmFilter ? ` · ${atmFilter}` : " · network"}
                {forecastDate ? ` · estimate for ${formatDate(forecastDate)}` : ""}
              </>
            )}
            action={(
              <Segmented
                label="Sort scenario rows"
                value={sortKey}
                onChange={setSortKey}
                options={[
                  { value: "impact", label: "Impact" },
                  { value: "cover", label: "Cover" },
                  { value: "risk", label: "Risk" },
                ]}
              />
            )}
          />

          <div className="scenario-stats">
            <div><span>Base forecast</span><strong>{scenario.data ? formatNumber(totals.base) : "—"}</strong></div>
            <div><span>Scenario forecast</span><strong>{scenario.data ? formatNumber(totals.adjusted) : "—"}</strong></div>
            <div><span>Cash balance</span><strong>{scenario.data ? formatNumber(totals.balance) : "—"}</strong></div>
            <div><span>At risk</span><strong className="is-risk">{scenario.data ? totals.critical + totals.watch : "—"}</strong></div>
          </div>

          <div className="table-scroll">
            <table className="data-table scenario-table">
              <thead>
                <tr>
                  <th>ATM</th>
                  <th className="is-numeric">Base forecast</th>
                  <th className="is-numeric">Scenario forecast</th>
                  <th className="is-numeric">Cash cover</th>
                </tr>
              </thead>
              <tbody>
                {!scenario.data && (scenario.loading || coreLoading) ? (
                  Array.from({ length: 7 }).map((_, index) => (
                    <tr key={`scenario-skeleton-${index}`}>
                      <td colSpan={4}><Skeleton style={{ height: 18 }} /></td>
                    </tr>
                  ))
                ) : rows.length ? (
                  rows.map((item) => {
                    const change = item.adjusted_forecast - item.base_forecast;
                    return (
                      <tr key={item.atm_id}>
                        <td>
                          <div className="atm-cell">
                            <strong>{item.atm_id}</strong>
                            <span>{item.location_name || item.location_type}</span>
                          </div>
                        </td>
                        <td className="is-numeric">{formatNumber(item.base_forecast)}</td>
                        <td className="is-numeric">
                          <span className="scenario-value">
                            {formatNumber(item.adjusted_forecast)}
                            {change !== 0 && (
                              <small className={change > 0 ? "is-up" : "is-down"}>
                                {change > 0 ? "+" : ""}{formatNumber(change)}
                              </small>
                            )}
                          </span>
                        </td>
                        <td className="is-numeric">
                          <span className={classNames(
                            "cover-value",
                            (item.cash_cover_days ?? 99) < 1 && "is-critical",
                            (item.cash_cover_days ?? 99) >= 1 && (item.cash_cover_days ?? 99) < 1.25 && "is-warning",
                          )}>
                            {coverageLabel(item.cash_cover_days)}
                          </span>
                          <span className="cell-sub">
                            <StatusBadge risk={item.risk_level} label={riskCopy(item.risk_level)} />
                          </span>
                        </td>
                      </tr>
                    );
                  })
                ) : (
                  <tr>
                    <td colSpan={4}>
                      <EmptyState
                        icon="activity"
                        title="No scenario estimates"
                        message="The backend returned no ATMs for this scope. Choose a different ATM or assumptions."
                      />
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="scenario-footer">
            <span>
              <Icon name="cpu" size={14} />
              {scenario.data?.model_name || core.status?.model_name || "Model not loaded"}
            </span>
            <span>
              <Icon name="database" size={14} />
              {source ? String(source).replaceAll("_", " ") : "—"}
            </span>
            <span>
              <Icon name="clock" size={14} />
              Generated {scenario.data ? new Date(scenario.data.generated_at).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }) : "—"}
            </span>
          </div>
        </Card>
      </section>

      <DataNotice tone="warning" title="Simulation, not an operational instruction">
        Scenario estimates use the latest observation per ATM and the trained model. They do not
        account for live cash-out events, delivery schedules or confirmed festival calendars, and
        must not be treated as approved replenishment orders.
      </DataNotice>
    </>
  );
}
