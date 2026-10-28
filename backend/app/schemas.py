from datetime import date, datetime
from typing import Literal

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
    accuracy_pct: float | None
    target_accuracy_pct: float
    target_met: bool | None
    wape_pct: float | None
    mae: float
    rmse: float
    smape_pct: float
    baseline_wape_pct: float | None
    baseline_mae: float
    baseline_rmse: float
    interval_abs_error_p90: float
    dataset_rows: int
    dataset_sha256: str
    trained_at: datetime


class ModelStatus(BaseModel):
    loaded: bool
    data_source: str
    model_data_current: bool
    model_name: str | None
    forecast_mode: Literal["production", "historical_demo"]
    forecast_available: bool
    forecast_blocked_reason: str | None
    training_rows: int | None
    test_rows: int | None
    dataset_rows: int
    atm_count: int
    dataset_start_date: date
    dataset_end_date: date
    trained_at: datetime | None
    feature_count: int
    evaluation_artifacts_available: bool


class AtmResponse(BaseModel):
    atm_id: str
    location_name: str | None = None
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


class ATMMetadataResponse(BaseModel):
    atm_id: str
    location_name: str
    location_type: str
    capacity: float
    data_source: str


class ATMMetadataPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[ATMMetadataResponse]


class ATMObservationResponse(BaseModel):
    atm_id: str
    observed_on: date
    total_withdrawals: float
    total_deposits: float
    withdrawal_transactions: int
    deposit_transactions: int
    opening_cash_balance: float
    closing_cash_balance: float
    replenishment_amount: float
    next_day_demand: float
    nearby_competitor_atms: int | None
    time_of_day: str | None
    holiday_flag: bool
    special_event_flag: bool
    weather_condition: str
    data_source: str


class ATMObservationPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[ATMObservationResponse]


class DatabaseSummary(BaseModel):
    atm_count: int
    observation_count: int
    synthetic_observation_count: int
    forecast_count: int
    earliest_observation: date | None
    latest_observation: date | None


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
    forecast_mode: Literal["production", "historical_demo", "legacy_unknown"]
    data_source: str
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


class DemandSeriesPoint(BaseModel):
    date: date
    observed: float
    prediction: float | None = None
    observations: int


class NextDemandForecast(BaseModel):
    forecast_date: date
    predicted_demand: float
    scope: Literal["network", "atm"]
    data_source: str
    model_name: str
    simulation: bool = True
    note: str


class DemandSeriesResponse(BaseModel):
    scope: Literal["network", "atm"]
    atm_id: str | None
    start_date: date
    end_date: date
    granularity: Literal["daily"] = "daily"
    unit: str = "cash_units"
    data_source: str
    observations: int
    prediction_available: bool
    points: list[DemandSeriesPoint]
    next_forecast: NextDemandForecast | None = None


class ScenarioRequest(BaseModel):
    festival: bool = False
    holiday: bool = False
    adjustment_pct: float = Field(default=0.0, ge=-30.0, le=30.0)
    atm_ids: list[str] | None = Field(default=None, max_length=100)


class ScenarioForecast(BaseModel):
    atm_id: str
    location_name: str | None = None
    location_type: str
    base_forecast: int
    adjusted_forecast: int
    adjustment_pct: float
    lower_bound: int
    upper_bound: int
    current_balance: int
    capacity: int
    cash_cover_days: float | None
    base_cash_cover_days: float | None
    recommended_replenishment: int
    risk_level: str
    capacity_constrained: bool
    source_data_as_of: date
    forecast_date: date
    data_source: str
    model_name: str
    simulation: bool = True


class ScenarioResponse(BaseModel):
    festival: bool
    holiday: bool
    adjustment_pct: float
    data_source: str
    forecast_mode: str
    simulation: bool = True
    note: str
    generated_at: datetime
    items: list[ScenarioForecast]


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
