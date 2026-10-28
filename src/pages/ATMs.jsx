import React, { useEffect, useMemo, useState } from "react";
import { useApp } from "../AppContext.jsx";
import {
  Badge,
  Card,
  DataNotice,
  EmptyState,
  ErrorState,
  PageHeader,
  Progress,
  SearchField,
  Skeleton,
  StatusBadge,
} from "../components/ui.jsx";
import {
  locationTypes,
  mergeAtmRecords,
  riskCounts,
  scenarioIndex,
} from "../derive.js";
import {
  classNames,
  coverageLabel,
  formatCompact,
  formatDate,
  formatNumber,
  formatPercent,
} from "../format.js";
import { useApi } from "../hooks.js";
import { Icon } from "../icons.jsx";

const SORTABLE = [
  { key: "atm", label: "ATM / Location" },
  { key: "capacity", label: "Capacity", numeric: true },
  { key: "balance", label: "Cash", numeric: true },
  { key: "fill", label: "Fill", numeric: true },
  { key: "forecast", label: "Forecast", numeric: true },
  { key: "cover", label: "Cover", numeric: true },
  { key: "accuracy", label: "Accuracy", numeric: true },
  { key: "risk", label: "Status" },
];

function sortValue(row, key) {
  if (key === "atm") return row.atm_id;
  if (key === "fill") return row.fill;
  if (key === "forecast") return row.forecast ?? -1;
  if (key === "cover") return row.cover ?? 999;
  if (key === "accuracy") return -1;
  if (key === "risk") return { critical: 0, watch: 1, healthy: 2 }[row.statusRisk] ?? 3;
  return Number(row[key]) || 0;
}

export default function ATMs() {
  const { token, core, coreLoading, refreshCore, prefs, navigate, params } = useApp();
  const [search, setSearch] = useState(params.q || "");
  const [riskFilter, setRiskFilter] = useState("");
  const [locationFilter, setLocationFilter] = useState("");
  const [sort, setSort] = useState({ key: "risk", direction: "asc" });

  useEffect(() => {
    if (params.q !== undefined) setSearch(params.q);
  }, [params.q]);

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
  const scenarios = useMemo(() => scenarioIndex(scenario.data), [scenario.data]);
  const locations = useMemo(() => locationTypes(records), [records]);

  const rows = useMemo(
    () => records.map((record) => {
      const estimate = scenarios.get(record.atm_id);
      const forecast = estimate?.base_forecast ?? null;
      const cover = estimate?.cash_cover_days ?? record.coverage_ratio;
      const fill = record.capacity > 0 ? record.balance / record.capacity : null;
      return {
        ...record,
        forecast,
        refill: estimate?.recommended_replenishment ?? null,
        cover,
        fill,
        statusRisk: estimate?.risk_level || record.risk_level,
        simulation: Boolean(estimate),
      };
    }),
    [records, scenarios],
  );

  const counts = useMemo(() => riskCounts(rows), [rows]);
  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    return rows.filter((row) => {
      if (riskFilter && row.statusRisk !== riskFilter) return false;
      if (locationFilter && row.location_type !== locationFilter) return false;
      if (!query) return true;
      return [
        row.atm_id,
        row.location_name,
        row.city,
        row.location_type,
      ].some((value) => String(value || "").toLowerCase().includes(query));
    });
  }, [rows, search, riskFilter, locationFilter]);

  const sorted = useMemo(() => {
    const direction = sort.direction === "asc" ? 1 : -1;
    return [...filtered].sort((a, b) => {
      const aValue = sortValue(a, sort.key);
      const bValue = sortValue(b, sort.key);
      if (typeof aValue === "string") return aValue.localeCompare(bValue) * direction;
      return (aValue - bValue) * direction;
    });
  }, [filtered, sort]);

  const units = (value) => (prefs.compactNumbers ? formatCompact(value) : formatNumber(value));
  const filtersActive = Boolean(search || riskFilter || locationFilter);

  function clearFilters() {
    setSearch("");
    setRiskFilter("");
    setLocationFilter("");
    if (params.q !== undefined) navigate("atms");
  }

  function changeSort(key) {
    setSort((current) => ({
      key,
      direction: current.key === key && current.direction === "asc" ? "desc" : "asc",
    }));
  }

  return (
    <>
      <PageHeader
        eyebrow="NETWORK MONITORING"
        title="ATM network"
        subtitle="Cash and next-day forecast from the API."
        meta={(
          <>
            <span className="meta-chip"><Icon name="calendar" size={13} />Latest observation {formatDate(core.summary?.latest_dataset_date)}</span>
            <span className="meta-chip"><Icon name="layers" size={13} />{formatNumber(rows.length)} ATMs</span>
            <Badge tone="warning" dot>{counts.critical} critical</Badge>
          </>
        )}
        actions={(
          <button
            type="button"
            className="button button-quiet"
            onClick={clearFilters}
            disabled={!filtersActive}
          >
            <Icon name="filter" size={15} />Clear filters
          </button>
        )}
      />

      <section className="atm-summary-grid">
        <div><span>Critical</span><strong>{counts.critical}</strong></div>
        <div><span>Warning</span><strong>{counts.watch}</strong></div>
        <div><span>Normal</span><strong>{counts.healthy}</strong></div>
        <div><span>Scenario estimates</span><strong>{scenario.data ? scenario.data.items.length : "—"}</strong></div>
      </section>

      {scenario.error && (
        <DataNotice
          tone="warning"
          title="Scenario estimates unavailable"
          action={(
            <button type="button" className="button button-quiet button-small" onClick={scenario.reload}>
              <Icon name="refresh" size={14} />Retry
            </button>
          )}
        >
          {scenario.error} The Forecast and Cover columns fall back to the latest observed demand
          where possible, and are not presented as model estimates.
        </DataNotice>
      )}

      <Card className="table-card">
        <div className="table-toolbar">
          <div className="table-toolbar-title">
            <h2>Cash and forecast</h2>
            <span>
              {scenario.loading ? "Refreshing scenario estimates…" : "Simulation estimates · latest observation per ATM"}
            </span>
          </div>
          <div className="table-tools">
            <SearchField
              value={search}
              onChange={setSearch}
              placeholder="ATM ID, city or type"
              label="Search ATM network"
            />
            <label className="select-shell compact">
              <Icon name="alert" size={14} />
              <select
                aria-label="Filter by status"
                value={riskFilter}
                onChange={(event) => setRiskFilter(event.target.value)}
              >
                <option value="">All statuses</option>
                <option value="critical">Critical</option>
                <option value="watch">Warning</option>
                <option value="healthy">Normal</option>
              </select>
            </label>
            <label className="select-shell compact">
              <Icon name="pin" size={14} />
              <select
                aria-label="Filter by location type"
                value={locationFilter}
                onChange={(event) => setLocationFilter(event.target.value)}
              >
                <option value="">All locations</option>
                {locations.map((location) => (
                  <option key={location} value={location}>{location}</option>
                ))}
              </select>
            </label>
          </div>
        </div>

        <div className="table-scroll">
          <table className="data-table atm-table">
            <thead>
              <tr>
                {SORTABLE.map((column) => (
                  <th
                    key={column.key}
                    className={column.numeric ? "is-numeric" : undefined}
                    aria-sort={
                      sort.key === column.key
                        ? sort.direction === "asc" ? "ascending" : "descending"
                        : "none"
                    }
                  >
                    <button type="button" className="th-sort" onClick={() => changeSort(column.key)}>
                      {column.label}
                      {column.key === "accuracy" && (
                        <span className="header-hint" title="Per-ATM holdout accuracy is not computed by the backend.">
                          <Icon name="info" size={12} />
                        </span>
                      )}
                      <Icon
                        name={sort.key === column.key && sort.direction === "desc" ? "chevronDown" : "chevronDown"}
                        size={12}
                        className={classNames(
                          "sort-icon",
                          sort.key === column.key && "is-active",
                          sort.key === column.key && sort.direction === "asc" && "is-ascending",
                        )}
                      />
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {coreLoading && !rows.length ? (
                Array.from({ length: 8 }).map((_, index) => (
                  <tr key={`skeleton-${index}`}>
                    <td colSpan={8}><Skeleton style={{ height: 20 }} /></td>
                  </tr>
                ))
              ) : sorted.length ? (
                sorted.map((row) => {
                  const fillPercent = row.fill === null ? null : Math.min(100, row.fill * 100);
                  return (
                    <tr key={row.atm_id}>
                      <td>
                        <button
                          type="button"
                          className="atm-identity"
                          onClick={() => navigate("whatif", { atm_id: row.atm_id })}
                          title="Open this ATM in the what-if forecast"
                        >
                          <strong>{row.atm_id}</strong>
                          <span>{row.location_name} · {row.location_type}</span>
                        </button>
                      </td>
                      <td className="is-numeric">{units(row.capacity)}</td>
                      <td className="is-numeric">{units(row.balance)}</td>
                      <td className="is-numeric">
                        <div className="fill-cell">
                          <span>{fillPercent === null ? "—" : formatPercent(fillPercent, 0)}</span>
                          <Progress
                            value={fillPercent ?? 0}
                            tone={(fillPercent ?? 0) < 30 ? "critical" : (fillPercent ?? 0) < 50 ? "warning" : "positive"}
                            label={`Cash fill for ${row.atm_id}`}
                          />
                        </div>
                      </td>
                      <td className="is-numeric">
                        {row.forecast === null ? (
                          <span className="muted">—</span>
                        ) : (
                          <span title="Simulation estimate from /forecasts/scenario">{units(row.forecast)}</span>
                        )}
                      </td>
                      <td className="is-numeric">
                        <span className={classNames(
                          "cover-value",
                          (row.cover ?? 99) < 1 && "is-critical",
                          (row.cover ?? 99) >= 1 && (row.cover ?? 99) < 1.25 && "is-warning",
                        )}>
                          {coverageLabel(row.cover)}
                        </span>
                      </td>
                      <td className="is-numeric">
                        <span
                          className="muted"
                          title={`Per-ATM holdout accuracy is not computed. Network accuracy: ${formatPercent(core.summary?.model?.accuracy_pct)}`}
                        >
                          —
                        </span>
                      </td>
                      <td>
                        <StatusBadge risk={row.statusRisk} />
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={8}>
                    <EmptyState
                      icon="search"
                      title="No ATMs match these filters"
                      message="Clear the search or choose a different status or location."
                      action={(
                        <button type="button" className="button button-quiet" onClick={clearFilters}>
                          Clear filters
                        </button>
                      )}
                    />
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="table-footer">
          <span>
            Showing <strong>{formatNumber(sorted.length)}</strong> of <strong>{formatNumber(rows.length)}</strong> ATMs
            {filtersActive ? " (filtered)" : ""}
          </span>
          <span className="table-method">
            Forecast = model simulation · Cover = balance ÷ forecast · Accuracy is network-level only
          </span>
        </div>
      </Card>

      <DataNotice tone="info" icon="info">
        Scenario estimates are generated from the latest observation per ATM and are labelled
        simulation. Per-ATM accuracy, confirmed cash-out events and delivery outcomes are not
        available in the current backend.
      </DataNotice>
    </>
  );
}
