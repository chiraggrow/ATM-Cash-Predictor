from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "ATM Cash Intelligence API"
    environment: str = "development"
    database_url: str = (
        "postgresql+psycopg://atm_cash_app@localhost:5432/atm_cash_predictor"
    )
    jwt_secret_key: SecretStr = SecretStr("")
    access_token_expire_minutes: int = Field(default=30, ge=5, le=1440)
    admin_username: str = "admin"
    admin_password: SecretStr = SecretStr("")
    cors_origins: str = "http://localhost:5173,http://localhost:8080"
    dataset_path: Path = PROJECT_ROOT / "atm_cash.csv"
    model_artifact_path: Path = PROJECT_ROOT / "artifacts" / "atm-demand.joblib"
    target_accuracy_pct: float = Field(default=85.0, ge=0, le=100)
    model_test_size: float = Field(default=0.2, gt=0, lt=0.5)
    max_forecast_data_age_days: int = Field(default=1, ge=0, le=3650)
    forecast_mode: Literal["production", "historical_demo"] = "production"
    operational_data_source: str = "synthetic_simulation"
    create_schema_on_startup: bool = False

    @field_validator("dataset_path", "model_artifact_path", mode="before")
    @classmethod
    def resolve_project_paths(cls, value: str | Path) -> Path:
        path = Path(value)
        return path if path.is_absolute() else PROJECT_ROOT / path

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    def validate_secrets(self) -> None:
        if len(self.jwt_secret_key.get_secret_value()) < 32:
            raise ValueError("JWT_SECRET_KEY must contain at least 32 characters.")
        if len(self.admin_password.get_secret_value()) < 12:
            raise ValueError("ADMIN_PASSWORD must contain at least 12 characters.")
        if self.environment.casefold() == "production" and self.forecast_mode != "production":
            raise ValueError("FORECAST_MODE must be 'production' when ENVIRONMENT is 'production'.")
        if self.environment.casefold() == "production" and self.create_schema_on_startup:
            raise ValueError("CREATE_SCHEMA_ON_STARTUP must be false in production; use Alembic.")
