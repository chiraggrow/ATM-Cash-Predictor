import { cityFromLocation, isFiniteNumber } from "./format.js";

export function mergeAtmRecords(atms = [], metadata = []) {
  const locations = new Map(metadata.map((item) => [item.atm_id, item]));
  return atms.map((atm) => {
    const meta = locations.get(atm.atm_id);
    const locationName = atm.location_name || meta?.location_name || atm.location_type;
    return {
      ...atm,
      location_name: locationName,
      city: cityFromLocation(locationName),
      location_type: atm.location_type || meta?.location_type,
    };
  });
}

export function scenarioIndex(scenario) {
  return new Map((scenario?.items || []).map((item) => [item.atm_id, item]));
}

export function riskCounts(rows = []) {
  return rows.reduce(
    (counts, row) => {
      const risk = row.statusRisk || row.risk_level;
      if (risk === "critical") counts.critical += 1;
      else if (risk === "watch") counts.watch += 1;
      else counts.healthy += 1;
      return counts;
    },
    { critical: 0, watch: 0, healthy: 0, total: rows.length },
  );
}

export function cashSummary(rows = []) {
  const totals = rows.reduce(
    (accumulator, row) => {
      accumulator.balance += Number(row.balance) || 0;
      accumulator.capacity += Number(row.capacity) || 0;
      accumulator.demand += Number(row.demand) || 0;
      return accumulator;
    },
    { balance: 0, capacity: 0, demand: 0 },
  );
  return {
    ...totals,
    utilization: totals.capacity > 0 ? totals.balance / totals.capacity : null,
    coverage: totals.demand > 0 ? totals.balance / totals.demand : null,
  };
}

export function cashByCity(rows = []) {
  const groups = new Map();
  for (const row of rows) {
    const city = row.city || "Unassigned";
    const current = groups.get(city) || { city, balance: 0, capacity: 0, atms: 0 };
    current.balance += Number(row.balance) || 0;
    current.capacity += Number(row.capacity) || 0;
    current.atms += 1;
    groups.set(city, current);
  }
  return [...groups.values()].sort((a, b) => b.balance - a.balance);
}

export function locationTypes(rows = []) {
  return [...new Set(rows.map((row) => row.location_type).filter(Boolean))].sort();
}

export function buildAlerts(rows = [], scenarios = null) {
  const scenario = scenarios instanceof Map ? scenarios : scenarioIndex(scenarios);
  return rows
    .map((row) => {
      const item = scenario.get(row.atm_id);
      return {
        id: `${row.atm_id}:${row.last_observed_at}`,
        atm_id: row.atm_id,
        location_name: row.location_name,
        location_type: row.location_type,
        city: row.city,
        severity: (item?.risk_level || row.risk_level) === "critical" ? "Critical" : "High",
        risk_level: item?.risk_level || row.risk_level,
        coverage: item?.cash_cover_days ?? row.coverage_ratio,
        cash: row.balance,
        demand: item?.base_forecast ?? row.demand,
        suggested_refill: item?.recommended_replenishment ?? null,
        last_observed_at: row.last_observed_at,
      };
    })
    .filter((alert) => alert.risk_level === "critical" || alert.risk_level === "watch")
    .sort((a, b) => {
      const order = { critical: 0, watch: 1 };
      return order[a.risk_level] - order[b.risk_level]
        || (isFiniteNumber(a.coverage) ? a.coverage : 99)
        - (isFiniteNumber(b.coverage) ? b.coverage : 99);
    });
}
