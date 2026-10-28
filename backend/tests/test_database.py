from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import Base, build_engine
from app.generate_synthetic_dataset import generate_synthetic_dataset
from app.models import ATM, ATMObservation
from app.seed_database import seed_dataset


def _write_generated_dataset(path: Path) -> int:
    data = generate_synthetic_dataset()
    data.to_csv(path, index=False)
    return len(data)


def test_synthetic_dataset_is_valid_and_reproducible() -> None:
    first = generate_synthetic_dataset()
    second = generate_synthetic_dataset()

    assert len(first) == 17_544
    assert first.equals(second)
    assert first["ATM_ID"].nunique() == 24
    assert first["Date"].min() == "2023-01-01"
    assert first["Date"].max() == "2024-12-31"
    assert not first[["ATM_ID", "Date"]].duplicated().any()
    assert first["Data_Source"].eq("synthetic_simulation").all()


def test_synthetic_extension_preserves_existing_atm_capacities() -> None:
    baseline = generate_synthetic_dataset()
    capacities = (
        baseline.groupby("ATM_ID", sort=True)["ATM_Capacity"]
        .first()
        .astype(int)
        .to_dict()
    )
    extension = generate_synthetic_dataset(
        start_date=pd.Timestamp("2025-01-01").date(),
        end_date=pd.Timestamp("2026-02-28").date(),
        seed=20261027,
        atm_capacities=capacities,
    )

    assert extension["Date"].min() == "2025-01-01"
    assert extension["Date"].max() == "2026-02-28"
    date_gaps = (
        extension.assign(Date=pd.to_datetime(extension["Date"]))
        .sort_values(["ATM_ID", "Date"])
        .groupby("ATM_ID")["Date"]
        .diff()
        .dropna()
        .dt.days
    )
    assert date_gaps.eq(1).all()
    assert len(extension) == 24 * 424
    assert extension.groupby("ATM_ID")["ATM_Capacity"].first().astype(int).to_dict() == capacities
    assert (extension["Closing_Cash_Balance"] <= extension["ATM_Capacity"]).all()
    assert extension["Data_Source"].eq("synthetic_simulation").all()
    assert not extension[["ATM_ID", "Date"]].duplicated().any()


def test_database_seed_is_idempotent_and_preserves_unique_grain(tmp_path: Path) -> None:
    dataset_path = tmp_path / "synthetic.csv"
    dataset_rows = _write_generated_dataset(dataset_path)
    engine = build_engine(f"sqlite:///{tmp_path / 'seed.db'}")
    Base.metadata.create_all(bind=engine)
    try:
        first = seed_dataset(engine, dataset_path)
        second = seed_dataset(engine, dataset_path)

        assert first["observations"] == dataset_rows
        assert first["inserted_observations"] == dataset_rows
        assert second["inserted_observations"] == 0
        assert second["skipped_existing_observations"] == dataset_rows
        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(ATM)) == 24
            assert (
                session.scalar(select(func.count()).select_from(ATMObservation))
                == dataset_rows
            )
    finally:
        engine.dispose()


def test_seed_refuses_to_mix_data_sources_on_existing_atm_ids(tmp_path: Path) -> None:
    dataset_path = tmp_path / "synthetic.csv"
    _write_generated_dataset(dataset_path)
    engine = build_engine(f"sqlite:///{tmp_path / 'source-conflict.db'}")
    Base.metadata.create_all(bind=engine)
    try:
        with Session(engine) as session:
            session.add(
                ATM(
                    atm_id="SYN_ATM_0001",
                    location_name="Existing historical source",
                    location_type="Unknown",
                    capacity=100_000,
                    data_source="historical_csv",
                )
            )
            session.commit()

        with pytest.raises(ValueError, match="different data source"):
            seed_dataset(engine, dataset_path)

        with Session(engine) as session:
            assert session.get(ATM, "SYN_ATM_0001").data_source == "historical_csv"
            assert session.scalar(select(func.count()).select_from(ATMObservation)) == 0
    finally:
        engine.dispose()


def test_database_observation_constraints_reject_duplicate_and_unknown_atm(
    tmp_path: Path,
) -> None:
    engine = build_engine(f"sqlite:///{tmp_path / 'constraints.db'}")
    Base.metadata.create_all(bind=engine)
    try:
        with Session(engine) as session:
            session.add(
                ATM(
                    atm_id="SYN_ATM_TEST",
                    location_name="Test location",
                    location_type="Test",
                    capacity=100_000,
                    data_source="synthetic_simulation",
                )
            )
            session.commit()
            observation = ATMObservation(
                atm_id="SYN_ATM_TEST",
                observed_on=pd.Timestamp("2024-01-01").date(),
                total_withdrawals=10_000,
                total_deposits=0,
                withdrawal_transactions=10,
                deposit_transactions=0,
                opening_cash_balance=50_000,
                closing_cash_balance=40_000,
                replenishment_amount=0,
                next_day_demand=11_000,
                holiday_flag=False,
                special_event_flag=False,
                weather_condition="Clear",
            )
            session.add(observation)
            session.commit()
            session.add(
                ATMObservation(
                    atm_id=observation.atm_id,
                    observed_on=observation.observed_on,
                    total_withdrawals=10_000,
                    total_deposits=0,
                    withdrawal_transactions=10,
                    deposit_transactions=0,
                    opening_cash_balance=50_000,
                    closing_cash_balance=40_000,
                    replenishment_amount=0,
                    next_day_demand=11_000,
                    holiday_flag=False,
                    special_event_flag=False,
                    weather_condition="Clear",
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
            session.add(
                ATMObservation(
                    atm_id="UNKNOWN_ATM",
                    observed_on=pd.Timestamp("2024-01-02").date(),
                    total_withdrawals=10_000,
                    total_deposits=0,
                    withdrawal_transactions=10,
                    deposit_transactions=0,
                    opening_cash_balance=50_000,
                    closing_cash_balance=40_000,
                    replenishment_amount=0,
                    next_day_demand=11_000,
                    holiday_flag=False,
                    special_event_flag=False,
                    weather_condition="Clear",
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
    finally:
        engine.dispose()


def test_database_endpoints_read_seeded_atm_data(test_client, access_token, tmp_path: Path):
    dataset_path = tmp_path / "api-synthetic.csv"
    _write_generated_dataset(dataset_path)
    seed_dataset(test_client.app.state.engine, dataset_path)
    with Session(test_client.app.state.engine) as session:
        session.add(
            ATM(
                atm_id="LEGACY_WITHOUT_OBSERVATIONS",
                location_name="Unknown legacy forecast",
                location_type="Unknown",
                capacity=100_000,
                data_source="legacy_unknown",
            )
        )
        session.commit()
    headers = {"Authorization": f"Bearer {access_token}"}

    atms_response = test_client.get(
        "/api/v1/data/atms?observed_only=true&limit=1",
        headers=headers,
    )
    assert atms_response.status_code == 200
    atms = atms_response.json()
    assert atms["total"] == 26
    assert len(atms["items"]) == 1
    assert atms["items"][0]["data_source"] == "test_fixture"
    synthetic_atms = test_client.get(
        "/api/v1/data/atms?observed_only=true&search=SYN_ATM_0001",
        headers=headers,
    )
    assert synthetic_atms.json()["total"] == 1
    atm_id = synthetic_atms.json()["items"][0]["atm_id"]
    assert synthetic_atms.json()["items"][0]["data_source"] == "synthetic_simulation"

    summary_response = test_client.get("/api/v1/data/summary", headers=headers)
    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["atm_count"] == 27
    assert summary["observation_count"] == 17_704
    assert summary["synthetic_observation_count"] == 17_544
    assert summary["forecast_count"] == 0
    operational_status = test_client.get("/api/v1/model/status", headers=headers)
    assert operational_status.status_code == 200
    assert operational_status.json()["data_source"] == "test_fixture"
    assert operational_status.json()["dataset_rows"] == 160

    observations_response = test_client.get(
        f"/api/v1/data/atms/{atm_id}/observations?limit=2",
        headers=headers,
    )
    assert observations_response.status_code == 200
    observations = observations_response.json()
    assert observations["total"] == 731
    assert len(observations["items"]) == 2
    assert observations["items"][0]["data_source"] == "synthetic_simulation"

    empty_observations = test_client.get(
        "/api/v1/data/atms/LEGACY_WITHOUT_OBSERVATIONS/observations",
        headers=headers,
    )
    assert empty_observations.status_code == 200
    assert empty_observations.json()["total"] == 0
    assert empty_observations.json()["items"] == []

    unknown_atm = test_client.get(
        "/api/v1/data/atms/UNKNOWN_ATM/observations",
        headers=headers,
    )
    assert unknown_atm.status_code == 404


def test_observation_endpoint_rejects_reversed_dates(test_client, access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    response = test_client.get(
        "/api/v1/data/atms/UNKNOWN/observations"
        "?start_date=2024-02-01&end_date=2024-01-01",
        headers=headers,
    )
    assert response.status_code == 422
