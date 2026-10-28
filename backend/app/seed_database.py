from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import pandas as pd
from sqlalchemy import Engine, case, func, select, tuple_
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.config import Settings
from app.database import build_engine
from app.generate_synthetic_dataset import validate_synthetic_dataset
from app.models import ATM, ATMObservation

DEFAULT_DATASET = (
    Path(__file__).resolve().parents[2] / "data" / "generated" / "atm_cash_10k.csv"
)
BATCH_SIZE = 1_000


def _insert_for_engine(engine: Engine, table: type[ATM] | type[ATMObservation]):
    if engine.dialect.name == "postgresql":
        return postgresql_insert(table)
    if engine.dialect.name == "sqlite":
        return sqlite_insert(table)
    raise ValueError(f"Seeding is not supported for {engine.dialect.name!r}.")


def _count_matching_observations(
    session: Session,
    keys: list[tuple[str, date]],
    batch_size: int,
) -> int:
    count = 0
    for start in range(0, len(keys), batch_size):
        batch_keys = keys[start : start + batch_size]
        count += (
            session.scalar(
                select(func.count())
                .select_from(ATMObservation)
                .where(
                    tuple_(ATMObservation.atm_id, ATMObservation.observed_on).in_(
                        batch_keys
                    )
                )
            )
            or 0
        )
    return count


def _validate_source_compatibility(
    session: Session,
    atm_ids: list[str],
    keys: list[tuple[str, date]],
    data_source: str,
    batch_size: int,
) -> None:
    conflicting_atm = session.scalar(
        select(func.count())
        .select_from(ATM)
        .where(
            ATM.atm_id.in_(atm_ids),
            ATM.data_source.notin_([data_source, "legacy_unknown"]),
        )
    )
    if conflicting_atm:
        raise ValueError(
            "Seed data contains ATM IDs already assigned to a different data source."
        )

    for start in range(0, len(keys), batch_size):
        batch_keys = keys[start : start + batch_size]
        conflicting_observations = session.scalar(
            select(func.count())
            .select_from(ATMObservation)
            .where(
                tuple_(ATMObservation.atm_id, ATMObservation.observed_on).in_(
                    batch_keys
                ),
                ATMObservation.data_source.notin_(
                    [data_source, "legacy_unknown"]
                ),
            )
        )
        if conflicting_observations:
            raise ValueError(
                "Seed data contains ATM/date records already assigned to a different data source."
            )


def seed_dataset(engine: Engine, csv_path: Path, batch_size: int = BATCH_SIZE) -> dict[str, int]:
    if batch_size < 1:
        raise ValueError("batch_size must be greater than zero.")
    if not csv_path.is_file():
        raise FileNotFoundError(f"Synthetic dataset not found: {csv_path}")

    data = pd.read_csv(csv_path)
    validate_synthetic_dataset(data)
    data["Date"] = pd.to_datetime(data["Date"], errors="raise").dt.date

    atm_rows = (
        data.groupby("ATM_ID", sort=True)
        .agg(
            Location_Name=("Location_Name", "first"),
            Location_Type=("Location_Type", "first"),
            ATM_Capacity=("ATM_Capacity", "max"),
            Data_Source=("Data_Source", "first"),
        )
        .reset_index()
    )
    observations = [
        {
            "atm_id": row.ATM_ID,
            "observed_on": row.Date,
            "total_withdrawals": int(row.Total_Withdrawals),
            "total_deposits": int(row.Total_Deposits),
            "withdrawal_transactions": int(row.Withdrawal_Transactions),
            "deposit_transactions": int(row.Deposit_Transactions),
            "opening_cash_balance": int(row.Opening_Cash_Balance),
            "closing_cash_balance": int(row.Closing_Cash_Balance),
            "replenishment_amount": int(row.Replenishment_Amount),
            "next_day_demand": int(row.Cash_Demand_Next_Day),
            "nearby_competitor_atms": int(row.Nearby_Competitor_ATMs),
            "time_of_day": str(row.Time_of_Day),
            "data_source": str(row.Data_Source),
            "holiday_flag": bool(row.Holiday_Flag),
            "special_event_flag": bool(row.Special_Event_Flag),
            "weather_condition": row.Weather_Condition,
        }
        for row in data.itertuples(index=False)
    ]
    keys = [(row["atm_id"], row["observed_on"]) for row in observations]
    data_sources = {row["data_source"] for row in observations}
    if len(data_sources) != 1:
        raise ValueError("A seed file must contain exactly one data source.")
    data_source = next(iter(data_sources))
    with Session(engine) as session:
        _validate_source_compatibility(
            session,
            atm_rows["ATM_ID"].astype(str).tolist(),
            keys,
            data_source,
            batch_size,
        )
        matching_before = _count_matching_observations(session, keys, batch_size)

    atm_insert = _insert_for_engine(engine, ATM)
    atm_statement = atm_insert.values(
        [
            {
                "atm_id": row.ATM_ID,
                "location_name": row.Location_Name,
                "location_type": row.Location_Type,
                "capacity": int(row.ATM_Capacity),
                "data_source": row.Data_Source,
            }
            for row in atm_rows.itertuples(index=False)
        ]
    )
    atm_statement = atm_statement.on_conflict_do_update(
        index_elements=[ATM.atm_id],
        set_={
            "location_name": atm_statement.excluded.location_name,
            "location_type": atm_statement.excluded.location_type,
            "capacity": atm_statement.excluded.capacity,
            "data_source": case(
                (
                    ATM.data_source == "legacy_unknown",
                    atm_statement.excluded.data_source,
                ),
                else_=ATM.data_source,
            ),
        },
    )

    with Session(engine) as session:
        with session.begin():
            session.execute(atm_statement)
            observation_insert = _insert_for_engine(engine, ATMObservation)
            for start in range(0, len(observations), batch_size):
                statement = observation_insert.values(observations[start : start + batch_size])
                statement = statement.on_conflict_do_update(
                    index_elements=[ATMObservation.atm_id, ATMObservation.observed_on],
                    set_={
                        "nearby_competitor_atms": func.coalesce(
                            ATMObservation.nearby_competitor_atms,
                            statement.excluded.nearby_competitor_atms,
                        ),
                        "time_of_day": func.coalesce(
                            ATMObservation.time_of_day,
                            statement.excluded.time_of_day,
                        ),
                        "data_source": case(
                            (
                                ATMObservation.data_source == "legacy_unknown",
                                statement.excluded.data_source,
                            ),
                            else_=ATMObservation.data_source,
                        ),
                    },
                )
                session.execute(statement)

    with Session(engine) as session:
        stored_atms = session.scalar(select(func.count()).select_from(ATM)) or 0
        matching_observations = _count_matching_observations(
            session,
            keys,
            batch_size,
        )

    if stored_atms < len(atm_rows) or matching_observations != len(data):
        raise RuntimeError(
            "Post-seed database verification did not find every supplied ATM/date observation."
        )
    inserted_observations = matching_observations - matching_before
    return {
        "dataset_rows": len(data),
        "atms": stored_atms,
        "observations": matching_observations,
        "inserted_observations": inserted_observations,
        "skipped_existing_observations": len(data) - inserted_observations,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed synthetic ATM data into the configured database.")
    parser.add_argument("--csv", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    arguments = parser.parse_args()
    settings = Settings()
    engine = build_engine(settings.database_url)
    try:
        result = seed_dataset(engine, arguments.csv, arguments.batch_size)
    finally:
        engine.dispose()
    print(
        "Seed complete: "
        f"{result['atms']} ATMs, {result['observations']} total observations, "
        f"{result['inserted_observations']} inserted in this run, "
        f"{result['skipped_existing_observations']} already present."
    )


if __name__ == "__main__":
    main()
