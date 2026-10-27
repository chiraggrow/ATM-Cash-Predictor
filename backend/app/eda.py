from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

TARGET_COLUMN = "Cash_Demand_Next_Day"
REQUIRED_COLUMNS = {
    "ATM_ID",
    "Date",
    "Location_Type",
    "ATM_Balance",
    "Cash_Demand_Next_Day",
    "Replenishment_Required",
}


def build_eda_summary(data: pd.DataFrame) -> dict[str, Any]:
    missing_columns = sorted(REQUIRED_COLUMNS.difference(data.columns))
    if missing_columns:
        raise ValueError(f"Dataset is missing required columns: {', '.join(missing_columns)}")
    if data.empty:
        raise ValueError("Dataset contains no observations.")

    frame = data.copy()
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
    if frame["Date"].isna().any():
        raise ValueError("Dataset contains invalid or missing dates.")
    for column in ("Cash_Demand_Next_Day", "ATM_Balance"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
        if frame[column].isna().any():
            raise ValueError(f"Dataset contains invalid or missing values in {column}.")

    duplicate_groups = int(frame.groupby(["ATM_ID", "Date"]).size().gt(1).sum())
    changing_location_atms = int(
        frame.groupby("ATM_ID")["Location_Type"].nunique().gt(1).sum()
    )
    stockout_proxy = frame["ATM_Balance"] < frame[TARGET_COLUMN]
    grouped_location = frame.groupby("Location_Type")[TARGET_COLUMN].agg(["mean", "count"])

    return {
        "observations": len(frame),
        "unique_atms": int(frame["ATM_ID"].nunique()),
        "date_start": frame["Date"].min().date().isoformat(),
        "date_end": frame["Date"].max().date().isoformat(),
        "cash_amount_unit": "dataset units; currency not specified",
        "missing_values_by_column": {
            column: int(count)
            for column, count in frame.isna().sum().items()
            if count > 0
        },
        "duplicate_atm_date_groups": duplicate_groups,
        "atms_with_changing_location_labels": changing_location_atms,
        "average_next_day_demand": float(frame[TARGET_COLUMN].mean()),
        "median_next_day_demand": float(frame[TARGET_COLUMN].median()),
        "zero_demand_observations": int((frame[TARGET_COLUMN] == 0).sum()),
        "balance_below_next_day_demand_proxy": {
            "observations": int(stockout_proxy.sum()),
            "rate_pct": float(stockout_proxy.mean() * 100),
            "is_confirmed_cashout_metric": False,
        },
        "replenishment_flagged_observations": int(
            (frame["Replenishment_Required"].astype(str).str.casefold() == "yes").sum()
        ),
        "average_demand_by_location_observation_label": {
            str(location): {
                "average": float(row["mean"]),
                "observations": int(row["count"]),
            }
            for location, row in grouped_location.iterrows()
        },
    }


def create_eda_report(input_path: Path, output_dir: Path) -> dict[str, Any]:
    if not input_path.is_file():
        raise FileNotFoundError(f"Dataset was not found: {input_path}")
    data = pd.read_csv(input_path)
    summary = build_eda_summary(data)

    output_dir.mkdir(parents=True, exist_ok=True)
    data["Date"] = pd.to_datetime(data["Date"], errors="raise")
    data[TARGET_COLUMN] = pd.to_numeric(data[TARGET_COLUMN], errors="raise")
    plt.style.use("seaborn-v0_8-whitegrid")

    monthly = (
        data.set_index("Date")[TARGET_COLUMN]
        .resample("MS")
        .mean()
        .dropna()
    )
    figure, axis = plt.subplots(figsize=(11, 5))
    axis.plot(monthly.index, monthly.values, color="#bd2835", linewidth=2)
    axis.set(title="Observed average next-day cash demand", xlabel="Month", ylabel="Cash units")
    figure.tight_layout()
    figure.savefig(output_dir / "monthly_demand.png", dpi=160)
    plt.close(figure)

    by_location = (
        data.groupby("Location_Type")[TARGET_COLUMN]
        .mean()
        .sort_values(ascending=True)
    )
    figure, axis = plt.subplots(figsize=(9, 5))
    by_location.plot.barh(ax=axis, color="#c94c55")
    axis.set(title="Average demand by location observation label", xlabel="Cash units", ylabel="")
    figure.tight_layout()
    figure.savefig(output_dir / "location_demand.png", dpi=160)
    plt.close(figure)

    figure, axis = plt.subplots(figsize=(9, 5))
    axis.hist(data[TARGET_COLUMN], bins=30, color="#bc555b", edgecolor="white")
    axis.set(title="Next-day demand distribution", xlabel="Cash units", ylabel="Observations")
    figure.tight_layout()
    figure.savefig(output_dir / "demand_distribution.png", dpi=160)
    plt.close(figure)

    summary_path = output_dir / "data_quality_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Create ATM cash demand EDA charts and data-quality summary.")
    parser.add_argument("--input", type=Path, default=Path("../atm_cash.csv"))
    parser.add_argument("--output", type=Path, default=Path("../reports"))
    arguments = parser.parse_args()
    summary = create_eda_report(arguments.input, arguments.output)
    print(
        f"Analyzed {summary['observations']:,} records across "
        f"{summary['unique_atms']} ATM IDs. Report: {arguments.output.resolve()}"
    )


if __name__ == "__main__":
    main()
