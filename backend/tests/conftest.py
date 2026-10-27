import csv
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import Settings
from app.main import create_app

DATASET_COLUMNS = [
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
]


@pytest.fixture
def dataset_path(tmp_path: Path) -> Path:
    path = tmp_path / "atm_cash.csv"
    start = date(2023, 1, 1)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=DATASET_COLUMNS)
        writer.writeheader()
        for day_index in range(80):
            current_date = start + timedelta(days=day_index)
            for atm_index in range(2):
                atm_id = f"ATM_{atm_index + 1:04d}"
                demand = 28_000 + (day_index * 173 + atm_index * 3_100) % 24_000
                row = {
                    "ATM_ID": atm_id,
                    "Date": current_date.isoformat(),
                    "Day_of_Week": current_date.strftime("%A"),
                    "Time_of_Day": ("Morning", "Evening")[atm_index],
                    "Total_Withdrawals": 25_000 + day_index * 55 + atm_index * 2_000,
                    "Total_Deposits": 3_500 + day_index % 7 * 150,
                    "Location_Type": ("Mall", "Standalone")[atm_index],
                    "Holiday_Flag": int(current_date.weekday() == 4),
                    "Special_Event_Flag": 0,
                    "Previous_Day_Cash_Level": 55_000 + atm_index * 1_000,
                    "Weather_Condition": ("Clear", "Cloudy")[day_index % 2],
                    "Nearby_Competitor_ATMs": atm_index + 1,
                    "Cash_Demand_Next_Day": demand,
                    "ATM_Capacity": 100_000,
                    "ATM_Balance": 24_000 + day_index * 65 + atm_index * 900,
                    "Replenishment_Amount": 0,
                    "Replenishment_Required": "No",
                }
                writer.writerow(row)
                if day_index == 10 and atm_index == 0:
                    duplicate = dict(row)
                    duplicate["Time_of_Day"] = "Night"
                    duplicate["Cash_Demand_Next_Day"] = demand + 2_500
                    writer.writerow(duplicate)
    return path


@pytest.fixture
def test_client(dataset_path: Path, tmp_path: Path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        jwt_secret_key=SecretStr("test-secret-key-that-is-at-least-32-characters-long"),
        admin_username="test-admin",
        admin_password=SecretStr("test-admin-password-2026"),
        cors_origins="http://localhost:5173",
        dataset_path=dataset_path,
        model_artifact_path=tmp_path / "artifacts" / "test-model.joblib",
    )
    with TestClient(create_app(settings)) as client:
        yield client


@pytest.fixture
def access_token(test_client: TestClient) -> str:
    response = test_client.post(
        "/api/v1/auth/token",
        data={"username": "test-admin", "password": "test-admin-password-2026"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]
