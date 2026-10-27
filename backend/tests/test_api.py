from fastapi.testclient import TestClient


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
    assert summary["record_count"] == 161
    assert summary["atm_count"] == 2
    assert summary["duplicate_atm_date_groups"] == 1
    assert summary["changing_location_atms"] == 0
    assert summary["model"]["train_end_date"] < summary["model"]["test_start_date"]
    assert summary["model"]["test_rows"] > 0
    assert summary["model"]["target_met"] == (
        summary["model"]["accuracy_pct"] >= summary["model"]["target_accuracy_pct"]
    )
    assert summary["model"]["cashout_reduction_target_met"] == (
        summary["model"]["simulated_cashout_reduction_pct"]
        >= summary["model"]["cashout_reduction_target_pct"]
    )


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
    assert forecast["lower_bound"] <= forecast["predicted_demand"] <= forecast["upper_bound"]
    assert forecast["recommended_replenishment"] <= (
        forecast["capacity"] - forecast["current_balance"]
    )

    history = test_client.get("/api/v1/forecasts", headers=headers)
    assert history.status_code == 200
    assert history.json()["total"] == 1
    assert history.json()["items"][0]["id"] == forecast["id"]
    assert history.json()["items"][0]["capacity"] == forecast["capacity"]


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
    assert response.json()["dataset_rows"] == 161
