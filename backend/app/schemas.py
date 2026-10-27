from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    username: str
    role: str


class ModelEvaluation(BaseModel):
    model_name: str
    training_rows: int
    test_rows: int
    train_end_date: date
    test_start_date: date
    test_end_date: date
    accuracy_pct: float
    target_accuracy_pct: float
    target_met: bool
    wape_pct: float
    mae: float
    rmse: float
    smape_pct: float
    baseline_wape_pct: float
    interval_abs_error_p90: float
    cashout_proxy_rate_pct: float
    simulated_cashout_reduction_pct: float
    cashout_reduction_target_pct: float
    cashout_reduction_target_met: bool
    baseline_cashout_proxy_events: int
    simulated_cashout_proxy_events: int
    dataset_rows: int
    dataset_sha256: str
    trained_at: datetime


class AtmResponse(BaseModel):
    atm_id: str
    location_type: str
    last_observed_at: date
    demand: float
    balance: float
    capacity: float
    replenishment_required: bool
    coverage_ratio: float | None
    risk_level: str


class AtmPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[AtmResponse]


class ForecastRequest(BaseModel):
    atm_id: str = Field(min_length=1, max_length=32)

    @field_validator("atm_id")
    @classmethod
    def strip_atm_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("ATM ID must contain a non-whitespace character.")
        return normalized


class ForecastResponse(BaseModel):
    id: int
    atm_id: str
    forecast_date: date
    source_data_as_of: date
    predicted_demand: int
    lower_bound: int
    upper_bound: int
    current_balance: int
    capacity: int
    recommended_replenishment: int
    risk_level: str
    capacity_constrained: bool
    model_name: str
    created_at: datetime


class ForecastHistory(BaseModel):
    total: int
    items: list[ForecastResponse]


class DemandPoint(BaseModel):
    period: str
    average_demand: float
    observations: int


class LocationDemand(BaseModel):
    location_type: str
    average_demand: float
    observations: int


class DashboardSummary(BaseModel):
    record_count: int
    atm_count: int
    average_demand: float
    total_replenishment_flags: int
    at_risk_atms: int
    duplicate_atm_date_groups: int
    changing_location_atms: int
    latest_dataset_date: date
    model: ModelEvaluation
