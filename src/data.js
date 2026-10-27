import csvUrl from "../atm_cash.csv?url";

export async function loadDataset() {
  const response = await fetch(csvUrl);
  if (!response.ok) throw new Error(`Could not load ATM data (${response.status}).`);

  const [headerLine, ...dataLines] = (await response.text()).trim().split(/\r?\n/);
  const headers = headerLine.split(",");
  const observations = dataLines.map((line) => {
    const values = line.split(",");
    const row = Object.fromEntries(headers.map((header, index) => [header, values[index]]));

    return {
      ...row,
      date: row.Date,
      demand: Number(row.Cash_Demand_Next_Day),
      balance: Number(row.ATM_Balance),
      withdrawals: Number(row.Total_Withdrawals),
      replenishment: Number(row.Replenishment_Amount),
      replenishmentRequired: row.Replenishment_Required === "Yes",
      capacity: Number(row.ATM_Capacity),
    };
  });
  const latestDatasetDate = observations.reduce(
    (latest, row) => (row.date > latest ? row.date : latest),
    "",
  );

  return {
    observations,
    atmCount: new Set(observations.map((row) => row.ATM_ID)).size,
    latestDatasetDate,
  };
}

export function getPeriodData(observations, latestDatasetDate, monthCount) {
  const latest = new Date(`${latestDatasetDate}T00:00:00Z`);
  const cutoff = new Date(Date.UTC(latest.getUTCFullYear(), latest.getUTCMonth() - monthCount + 1, 1));
  const cutoffDate = cutoff.toISOString().slice(0, 10);
  return observations.filter((row) => row.date >= cutoffDate);
}

export function getLatestAtmRows(observations) {
  const latestRows = new Map();

  for (const row of observations) {
    const previous = latestRows.get(row.ATM_ID);
    if (!previous || row.date > previous.date) latestRows.set(row.ATM_ID, row);
  }

  return [...latestRows.values()].map((row) => {
    const coverage = row.demand > 0 ? row.balance / row.demand : Infinity;
    const risk = coverage < 1 ? "critical" : coverage < 1.25 ? "watch" : "healthy";
    return { ...row, coverage, risk };
  });
}

export function getMonthlyDemand(rows) {
  const buckets = new Map();

  for (const row of rows) {
    const month = row.date.slice(0, 7);
    const bucket = buckets.get(month) ?? { month, total: 0, count: 0 };
    bucket.total += row.demand;
    bucket.count += 1;
    buckets.set(month, bucket);
  }

  return [...buckets.values()]
    .sort((a, b) => a.month.localeCompare(b.month))
    .map((bucket) => ({ ...bucket, average: bucket.total / bucket.count }));
}
