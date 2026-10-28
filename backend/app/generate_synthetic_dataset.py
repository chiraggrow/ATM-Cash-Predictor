from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "generated" / "atm_cash_10k.csv"
SYNTHETIC_DATA_SOURCE = "synthetic_simulation"
LOCATION_PROFILES = (
    ("Muscat-CBD-01", "Bank Branch", 1.28),
    ("Muscat-Mall-02", "Mall", 1.35),
    ("Muscat-Fuel-03", "Gas Station", 1.10),
    ("Seeb-Market-04", "Supermarket", 1.16),
    ("Bawshar-Standalone-05", "Standalone", 0.88),
    ("Muttrah-CBD-06", "Bank Branch", 1.22),
)
COLUMNS = [
    "ATM_ID",
    "Date",
    "Day_of_Week",
    "Time_of_Day",
    "Total_Withdrawals",
    "Total_Deposits",
    "Location_Type",
    "Holiday_Flag",
    "Special_Event_Flag",
    "Previous_Day_Cash_Level",
    "Weather_Condition",
    "Nearby_Competitor_ATMs",
    "Cash_Demand_Next_Day",
    "ATM_Capacity",
    "ATM_Balance",
    "Replenishment_Amount",
    "Replenishment_Required",
    "Withdrawal_Transactions",
    "Deposit_Transactions",
    "Opening_Cash_Balance",
    "Closing_Cash_Balance",
    "Location_Name",
    "Data_Source",
]


def _simulated_demand(
    *,
    base_demand: float,
    location_multiplier: float,
    target_date: pd.Timestamp,
    atm_phase: float,
    rng: np.random.Generator,
) -> int:
    weekday_multiplier = (0.78, 0.82, 0.91, 1.02, 1.18, 1.34, 1.12)[target_date.dayofweek]
    annual_phase = 2 * np.pi * (target_date.dayofyear - 1) / 365.25
    seasonal_multiplier = 1 + 0.11 * np.sin(annual_phase + atm_phase)
    holiday = target_date.dayofyear in {1, 120, 180, 300, 360}
    event_multiplier = 1.18 if holiday else 1.0
    spike_multiplier = rng.uniform(1.35, 1.85) if rng.random() < 0.018 else 1.0
    demand = (
        base_demand
        * location_multiplier
        * weekday_multiplier
        * seasonal_multiplier
        * event_multiplier
        * spike_multiplier
        * rng.normal(1.0, 0.075)
    )
    return int(np.clip(round(demand), 4_000, 135_000))


def generate_synthetic_dataset(
    *,
    atm_count: int = 24,
    start_date: date = date(2023, 1, 1),
    end_date: date = date(2024, 12, 31),
    seed: int = 20261027,
    atm_capacities: dict[str, int] | None = None,
) -> pd.DataFrame:
    if atm_count < 2:
        raise ValueError("atm_count must be at least 2.")
    if end_date < start_date:
        raise ValueError("end_date must be on or after start_date.")
    if atm_capacities is not None:
        expected_atm_ids = {f"SYN_ATM_{index + 1:04d}" for index in range(atm_count)}
        if set(atm_capacities) != expected_atm_ids:
            raise ValueError("ATM capacities must be provided for every generated ATM ID.")
        if any(
            isinstance(capacity, bool) or not isinstance(capacity, int) or capacity <= 0
            for capacity in atm_capacities.values()
        ):
            raise ValueError("ATM capacities must be positive integers.")

    rng = np.random.default_rng(seed)
    dates = pd.date_range(start_date, end_date, freq="D")
    rows: list[dict[str, Any]] = []
    for atm_index in range(atm_count):
        atm_id = f"SYN_ATM_{atm_index + 1:04d}"
        location_name, location_type, location_multiplier = LOCATION_PROFILES[
            atm_index % len(LOCATION_PROFILES)
        ]
        location_name = f"{location_name}-{atm_index + 1:02d}"
        capacity = (
            atm_capacities[atm_id]
            if atm_capacities is not None
            else int(rng.choice([80_000, 100_000, 120_000, 150_000]))
        )
        base_demand = float(rng.uniform(29_000, 59_000))
        atm_phase = float(rng.uniform(-0.4, 0.4))
        nearby_atms = int(rng.integers(0, 6))
        opening_balance = int(rng.uniform(35_000, capacity * 0.78))
        demand_dates = dates.append(pd.DatetimeIndex([dates[-1] + pd.Timedelta(days=1)]))
        demand_series = [
            _simulated_demand(
                base_demand=base_demand,
                location_multiplier=location_multiplier,
                target_date=target_date,
                atm_phase=atm_phase,
                rng=rng,
            )
            for target_date in demand_dates
        ]

        for date_index, observed_date in enumerate(dates):
            today = observed_date
            current_demand = demand_series[date_index]
            target_stock = min(capacity, int(current_demand * 1.45))
            replenishment = (
                min(capacity - opening_balance, max(0, target_stock - opening_balance))
                if opening_balance < current_demand * 0.9
                else 0
            )
            deposit_transactions = int(rng.poisson(5.5))
            total_deposits = int(
                min(capacity * 0.08, rng.gamma(2.2, 650) * deposit_transactions)
            )
            available_cash = min(capacity, opening_balance + replenishment + total_deposits)
            actual_withdrawals = min(
                available_cash,
                int(round(current_demand * rng.normal(1.0, 0.055))),
            )
            withdrawal_transactions = max(
                1,
                int(round(actual_withdrawals / rng.uniform(950, 1_850))),
            )
            closing_balance = int(
                np.clip(available_cash - actual_withdrawals, 0, capacity)
            )
            next_day_demand = demand_series[date_index + 1]
            weather = rng.choice(
                ["Clear", "Cloudy", "Rainy"],
                p=[0.58, 0.30, 0.12],
            )
            holiday_flag = int(today.dayofyear in {1, 120, 180, 300, 360})
            event_flag = int(rng.random() < 0.025)
            rows.append(
                {
                    "ATM_ID": atm_id,
                    "Date": today.date().isoformat(),
                    "Day_of_Week": today.day_name(),
                    "Time_of_Day": "EndOfDay",
                    "Total_Withdrawals": actual_withdrawals,
                    "Total_Deposits": total_deposits,
                    "Location_Type": location_type,
                    "Holiday_Flag": holiday_flag,
                    "Special_Event_Flag": event_flag,
                    "Previous_Day_Cash_Level": opening_balance,
                    "Weather_Condition": weather,
                    "Nearby_Competitor_ATMs": nearby_atms,
                    "Cash_Demand_Next_Day": next_day_demand,
                    "ATM_Capacity": capacity,
                    "ATM_Balance": closing_balance,
                    "Replenishment_Amount": replenishment,
                    "Replenishment_Required": "Yes" if replenishment > 0 else "No",
                    "Withdrawal_Transactions": withdrawal_transactions,
                    "Deposit_Transactions": deposit_transactions,
                    "Opening_Cash_Balance": opening_balance,
                    "Closing_Cash_Balance": closing_balance,
                    "Location_Name": location_name,
                    "Data_Source": SYNTHETIC_DATA_SOURCE,
                }
            )
            opening_balance = closing_balance

    data = pd.DataFrame(rows, columns=COLUMNS)
    validate_synthetic_dataset(data)
    return data


def validate_synthetic_dataset(data: pd.DataFrame) -> None:
    if data.empty:
        raise ValueError("Generated dataset contains no rows.")
    if len(data) < 10_000:
        raise ValueError(f"Generated dataset must have at least 10,000 rows; found {len(data)}.")
    missing_columns = sorted(set(COLUMNS).difference(data.columns))
    if missing_columns:
        raise ValueError(f"Generated dataset is missing columns: {', '.join(missing_columns)}")
    dates = pd.to_datetime(data["Date"], errors="coerce")
    if dates.isna().any():
        raise ValueError("Generated dataset contains invalid dates.")
    if data[["ATM_ID", "Date"]].duplicated().any():
        raise ValueError("Generated dataset contains duplicate ATM/date observations.")
    numeric_columns = [
        "Total_Withdrawals",
        "Total_Deposits",
        "Cash_Demand_Next_Day",
        "ATM_Capacity",
        "ATM_Balance",
        "Replenishment_Amount",
        "Withdrawal_Transactions",
        "Deposit_Transactions",
        "Opening_Cash_Balance",
        "Closing_Cash_Balance",
    ]
    if data[numeric_columns].isna().any().any():
        raise ValueError("Generated dataset contains missing numeric values.")
    if (data[numeric_columns] < 0).any().any():
        raise ValueError("Generated dataset contains prohibited negative values.")
    if not data["Data_Source"].eq(SYNTHETIC_DATA_SOURCE).all():
        raise ValueError("All generated rows must be labelled as synthetic.")
    if not (data["Closing_Cash_Balance"] <= data["ATM_Capacity"]).all():
        raise ValueError("Generated closing balance exceeds ATM capacity.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deterministic synthetic ATM observations.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--atms", type=int, default=24)
    parser.add_argument("--start-date", type=date.fromisoformat, default=date(2023, 1, 1))
    parser.add_argument("--end-date", type=date.fromisoformat, default=date(2024, 12, 31))
    parser.add_argument("--seed", type=int, default=20261027)
    parser.add_argument(
        "--atm-capacities-json",
        type=Path,
        help="Optional JSON object mapping every generated ATM ID to its existing capacity.",
    )
    arguments = parser.parse_args()
    atm_capacities = None
    if arguments.atm_capacities_json is not None:
        profile_data: object = json.loads(
            arguments.atm_capacities_json.read_text(encoding="utf-8")
        )
        if not isinstance(profile_data, dict) or any(
            not isinstance(atm_id, str)
            or isinstance(capacity, bool)
            or not isinstance(capacity, int)
            for atm_id, capacity in profile_data.items()
        ):
            raise ValueError("ATM capacity JSON must map ATM IDs to integer capacities.")
        atm_capacities = profile_data
    data = generate_synthetic_dataset(
        atm_count=arguments.atms,
        start_date=arguments.start_date,
        end_date=arguments.end_date,
        seed=arguments.seed,
        atm_capacities=atm_capacities,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(arguments.output, index=False)
    print(
        f"Generated {len(data):,} synthetic observations across "
        f"{data['ATM_ID'].nunique()} ATMs ({data['Date'].min()} to {data['Date'].max()}) "
        f"at {arguments.output.resolve()}."
    )


if __name__ == "__main__":
    main()
