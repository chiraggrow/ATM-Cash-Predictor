from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import Settings
from conftest import create_test_app
from app.models import ATMObservation


def test_protected_dashboard_and_data_quality_summary(
    test_client: TestClient,
    access_token: str,
) -> None:
    assert test_client.get("/api/v1/analytics/summary").status_code == 401

    response = test_client.get(
        "/api/v1/analytics/summary",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200
    summary = response.json()
    assert summary["record_count"] == 160
    assert summary["atm_count"] == 2
    assert summary["duplicate_atm_date_groups"] == 0
    assert summary["changing_location_atms"] == 0
    assert summary["model"]["train_end_date"] < summary["model"]["test_start_date"]
    assert summary["model"]["test_rows"] > 0
    assert summary["model"]["target_met"] == (
        summary["model"]["accuracy_pct"] >= summary["model"]["target_accuracy_pct"]
    )
    assert summary["model"]["baseline_mae"] >= 0
    assert summary["model"]["baseline_rmse"] >= 0
    assert "simulated_cashout_reduction_pct" not in summary["model"]

    status = test_client.get(
        "/api/v1/model/status",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert status.status_code == 200, status.text
    assert status.json()["loaded"] is True
    assert status.json()["forecast_mode"] == "production"
    assert status.json()["data_source"] == "test_fixture"
    assert status.json()["model_data_current"] is True
    assert status.json()["forecast_available"] is True
    assert status.json()["dataset_rows"] == summary["record_count"]
    assert status.json()["evaluation_artifacts_available"] is True


def test_forecast_is_bounded_and_saved_to_audit_history(
    test_client: TestClient,
    access_token: str,
) -> None:
    headers = {"Authorization": f"Bearer {access_token}"}
    response = test_client.post(
        "/api/v1/forecasts",
        json={"atm_id": "ATM_0001"},
        headers=headers,
    )
    assert response.status_code == 201
    forecast = response.json()
    assert forecast["forecast_date"] > forecast["source_data_as_of"]
    assert forecast["forecast_mode"] == "production"
    assert forecast["data_source"] == "test_fixture"
    assert forecast["lower_bound"] <= forecast["predicted_demand"] <= forecast["upper_bound"]
    assert forecast["recommended_replenishment"] <= (
        forecast["capacity"] - forecast["current_balance"]
    )

    history = test_client.get("/api/v1/forecasts", headers=headers)
    assert history.status_code == 200
    assert history.json()["total"] == 1
    assert history.json()["items"][0]["id"] == forecast["id"]
    assert history.json()["items"][0]["capacity"] == forecast["capacity"]
    assert history.json()["items"][0]["forecast_mode"] == "production"


def test_forecast_rejects_unknown_atm_and_invalid_credentials(
    test_client: TestClient,
    access_token: str,
) -> None:
    missing_atm = test_client.post(
        "/api/v1/forecasts",
        json={"atm_id": "ATM_9999"},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert missing_atm.status_code == 404

    bad_login = test_client.post(
        "/api/v1/auth/token",
        data={"username": "test-admin", "password": "wrong-password"},
    )
    assert bad_login.status_code == 401


def test_daily_demand_series_returns_observations_predictions_and_simulation_forecast(
    test_client: TestClient,
    access_token: str,
) -> None:
    headers = {"Authorization": f"Bearer {access_token}"}
    assert test_client.get("/api/v1/analytics/demand-series").status_code == 401

    response = test_client.get(
        "/api/v1/analytics/demand-series?months=6",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["scope"] == "network"
    assert payload["unit"] == "cash_units"
    assert payload["data_source"] == "test_fixture"
    assert payload["observations"] > 0
    assert len(payload["points"]) > 0
    assert payload["prediction_available"] is True
    assert any(point["prediction"] is not None for point in payload["points"])
    assert payload["next_forecast"]["simulation"] is True
    assert payload["next_forecast"]["data_source"] == "test_fixture"

    selected = test_client.get(
        "/api/v1/analytics/demand-series?months=6&atm_id=ATM_0001",
        headers=headers,
    )
    assert selected.status_code == 200, selected.text
    assert selected.json()["scope"] == "atm"
    assert selected.json()["atm_id"] == "ATM_0001"

    missing = test_client.get(
        "/api/v1/analytics/demand-series?atm_id=ATM_9999",
        headers=headers,
    )
    assert missing.status_code == 404


def test_scenario_forecast_is_labelled_simulation_and_applies_assumptions(
    test_client: TestClient,
    access_token: str,
) -> None:
    headers = {"Authorization": f"Bearer {access_token}"}
    baseline = test_client.post(
        "/api/v1/forecasts/scenario",
        json={},
        headers=headers,
    )
    assert baseline.status_code == 200, baseline.text
    baseline_payload = baseline.json()
    assert baseline_payload["simulation"] is True
    assert baseline_payload["items"]
    assert all(item["simulation"] is True for item in baseline_payload["items"])
    assert all(item["location_name"] for item in baseline_payload["items"])

    scenario = test_client.post(
        "/api/v1/forecasts/scenario",
        json={
            "festival": True,
            "holiday": True,
            "adjustment_pct": 10,
            "atm_ids": ["ATM_0001"],
        },
        headers=headers,
    )
    assert scenario.status_code == 200, scenario.text
    item = scenario.json()["items"][0]
    assert scenario.json()["festival"] is True
    assert scenario.json()["holiday"] is True
    assert item["adjustment_pct"] == 10
    assert item["adjusted_forecast"] == round(item["base_forecast"] * 1.1)
    assert item["recommended_replenishment"] <= item["capacity"] - item["current_balance"]

    unknown = test_client.post(
        "/api/v1/forecasts/scenario",
        json={"atm_ids": ["ATM_9999"]},
        headers=headers,
    )
    assert unknown.status_code == 404

    invalid = test_client.post(
        "/api/v1/forecasts/scenario",
        json={"adjustment_pct": 50},
        headers=headers,
    )
    assert invalid.status_code == 422


def test_atm_list_exposes_location_name_for_city_search(
    test_client: TestClient,
    access_token: str,
) -> None:
    headers = {"Authorization": f"Bearer {access_token}"}
    response = test_client.get("/api/v1/atms?search=Mall", headers=headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["atm_id"] == "ATM_0001"
    assert payload["items"][0]["location_name"] == "Mall"


def test_database_observation_changes_invalidate_model_before_forecasting(
    test_client: TestClient,
    access_token: str,
) -> None:
    with Session(test_client.app.state.engine) as session:
        observation = session.query(ATMObservation).filter_by(atm_id="ATM_0001").first()
        observation.next_day_demand += 1
        session.commit()

    headers = {"Authorization": "Bearer " + access_token}
    status_response = test_client.get("/api/v1/model/status", headers=headers)
    forecast_response = test_client.post(
        "/api/v1/forecasts",
        json={"atm_id": "ATM_0001"},
        headers=headers,
    )

    assert status_response.status_code == 200
    assert status_response.json()["model_data_current"] is False
    assert forecast_response.status_code == 409
    assert "retrain" in forecast_response.json()["detail"]


def test_database_failure_returns_service_unavailable(
    test_client: TestClient,
    access_token: str,
) -> None:
    def unavailable_database():
        raise SQLAlchemyError("database unavailable")

    test_client.app.state.forecaster.dataset_provider = unavailable_database
    response = test_client.get(
        "/api/v1/analytics/summary",
        headers={"Authorization": "Bearer " + access_token},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "The operational database is unavailable."


def test_admin_can_retrain_and_public_readiness_is_available(
    test_client: TestClient,
    access_token: str,
) -> None:
    assert test_client.get("/health/live").json() == {"status": "alive"}
    assert test_client.get("/health/ready").json() == {"status": "ready"}

    response = test_client.post(
        "/api/v1/admin/model/retrain",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200
    assert response.json()["dataset_rows"] == 160


def test_model_status_requires_authentication(test_client: TestClient) -> None:
    assert test_client.get("/api/v1/model/status").status_code == 401


def test_historical_demo_mode_cannot_be_enabled_in_production() -> None:
    settings = Settings(
        environment="production",
        forecast_mode="historical_demo",
        jwt_secret_key=SecretStr("test-secret-key-that-is-at-least-32-characters-long"),
        admin_password=SecretStr("test-admin-password-2026"),
    )

    with pytest.raises(ValueError, match="FORECAST_MODE must be 'production'"):
        settings.validate_secrets()


def test_production_mode_rejects_recent_synthetic_observations(
    dataset_path: Path,
    tmp_path: Path,
) -> None:
    with TestClient(
        create_test_app(
            dataset_path,
            tmp_path,
            operational_data_source="synthetic_simulation",
        )
    ) as client:
        token_response = client.post(
            "/api/v1/auth/token",
            data={"username": "test-admin", "password": "test-admin-password-2026"},
        )
        headers = {"Authorization": f"Bearer {token_response.json()['access_token']}"}
        status_response = client.get("/api/v1/model/status", headers=headers)
        forecast_response = client.post(
            "/api/v1/forecasts",
            json={"atm_id": "ATM_0001"},
            headers=headers,
        )

    assert status_response.status_code == 200
    assert status_response.json()["dataset_end_date"] == date.today().isoformat()
    assert status_response.json()["forecast_mode"] == "production"
    assert status_response.json()["forecast_available"] is False
    assert "Synthetic demonstration observations" in status_response.json()[
        "forecast_blocked_reason"
    ]
    assert forecast_response.status_code == 409
    assert "Synthetic demonstration observations" in forecast_response.json()["detail"]


def test_relative_dataset_and_artifact_paths_resolve_from_project_root() -> None:
    settings = Settings(
        dataset_path=Path("atm_cash.csv"),
        model_artifact_path=Path("artifacts/test-model.joblib"),
    )

    assert settings.dataset_path == Path(__file__).resolve().parents[2] / "atm_cash.csv"
    assert (
        settings.model_artifact_path
        == Path(__file__).resolve().parents[2] / "artifacts" / "test-model.joblib"
    )


def test_forecast_api_rejects_stale_observation_data(
    dataset_path: Path,
    tmp_path: Path,
) -> None:
    data = pd.read_csv(dataset_path)
    data["Date"] = (
        pd.to_datetime(data["Date"]) - pd.Timedelta(days=10)
    ).dt.strftime("%Y-%m-%d")
    stale_path = tmp_path / "stale-atm-cash.csv"
    data.to_csv(stale_path, index=False)
    with TestClient(create_test_app(stale_path, tmp_path)) as client:
        token_response = client.post(
            "/api/v1/auth/token",
            data={"username": "test-admin", "password": "test-admin-password-2026"},
        )
        response = client.post(
            "/api/v1/forecasts",
            json={"atm_id": "ATM_0001"},
            headers={"Authorization": f"Bearer {token_response.json()['access_token']}"},
        )

    assert response.status_code == 409
    assert "refresh the dataset" in response.json()["detail"]


def test_historical_demo_mode_labels_and_persists_stale_forecasts(
    dataset_path: Path,
    tmp_path: Path,
) -> None:
    data = pd.read_csv(dataset_path)
    data["Date"] = (
        pd.to_datetime(data["Date"]) - pd.Timedelta(days=10)
    ).dt.strftime("%Y-%m-%d")
    demo_path = tmp_path / "historical-demo-atm-cash.csv"
    data.to_csv(demo_path, index=False)
    with TestClient(
        create_test_app(
            demo_path,
            tmp_path,
            forecast_mode="historical_demo",
            operational_data_source="synthetic_simulation",
        )
    ) as client:
        token_response = client.post(
            "/api/v1/auth/token",
            data={"username": "test-admin", "password": "test-admin-password-2026"},
        )
        headers = {"Authorization": f"Bearer {token_response.json()['access_token']}"}
        status_response = client.get("/api/v1/model/status", headers=headers)
        forecast_response = client.post(
            "/api/v1/forecasts",
            json={"atm_id": "ATM_0001"},
            headers=headers,
        )
        history_response = client.get("/api/v1/forecasts", headers=headers)

    assert status_response.status_code == 200
    assert status_response.json()["forecast_mode"] == "historical_demo"
    assert status_response.json()["forecast_available"] is True
    assert forecast_response.status_code == 201
    assert forecast_response.json()["forecast_mode"] == "historical_demo"
    assert forecast_response.json()["data_source"] == "synthetic_simulation"
    assert forecast_response.json()["forecast_date"] < pd.Timestamp.now().date().isoformat()
    assert history_response.json()["items"][0]["forecast_mode"] == "historical_demo"
