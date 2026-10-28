from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    role: Mapped[str] = mapped_column(String(32), default="analyst")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    forecasts: Mapped[list["ForecastRecord"]] = relationship(back_populates="created_by")


class ATM(Base):
    __tablename__ = "atms"
    __table_args__ = (
        CheckConstraint("capacity > 0", name="ck_atms_capacity_positive"),
        Index("ix_atms_location_type", "location_type"),
    )

    atm_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    location_name: Mapped[str] = mapped_column(String(120), nullable=False)
    location_type: Mapped[str] = mapped_column(String(50), nullable=False)
    capacity: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    data_source: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")

    observations: Mapped[list["ATMObservation"]] = relationship(back_populates="atm")


class ATMObservation(Base):
    __tablename__ = "atm_observations"
    __table_args__ = (
        UniqueConstraint("atm_id", "observed_on", name="uq_atm_observations_atm_date"),
        CheckConstraint("total_withdrawals >= 0", name="ck_atm_observations_withdrawals_nonnegative"),
        CheckConstraint("total_deposits >= 0", name="ck_atm_observations_deposits_nonnegative"),
        CheckConstraint("opening_cash_balance >= 0", name="ck_atm_observations_opening_nonnegative"),
        CheckConstraint("closing_cash_balance >= 0", name="ck_atm_observations_closing_nonnegative"),
        CheckConstraint("replenishment_amount >= 0", name="ck_atm_observations_replenishment_nonnegative"),
        CheckConstraint("next_day_demand >= 0", name="ck_atm_observations_demand_nonnegative"),
        CheckConstraint("withdrawal_transactions >= 0", name="ck_atm_observations_withdrawals_count_nonnegative"),
        CheckConstraint("deposit_transactions >= 0", name="ck_atm_observations_deposits_count_nonnegative"),
        CheckConstraint(
            "nearby_competitor_atms IS NULL OR nearby_competitor_atms >= 0",
            name="ck_atm_observations_competitors_nonnegative",
        ),
        Index("ix_atm_observations_observed_on", "observed_on"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    atm_id: Mapped[str] = mapped_column(
        ForeignKey("atms.atm_id", ondelete="RESTRICT"),
        nullable=False,
    )
    observed_on: Mapped[date] = mapped_column(Date, nullable=False)
    total_withdrawals: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    total_deposits: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    withdrawal_transactions: Mapped[int] = mapped_column(Integer, nullable=False)
    deposit_transactions: Mapped[int] = mapped_column(Integer, nullable=False)
    opening_cash_balance: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    closing_cash_balance: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    replenishment_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    next_day_demand: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    nearby_competitor_atms: Mapped[int | None] = mapped_column(Integer)
    time_of_day: Mapped[str | None] = mapped_column(String(32))
    data_source: Mapped[str] = mapped_column(String(32), nullable=False, default="legacy_unknown")
    holiday_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    special_event_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    weather_condition: Mapped[str] = mapped_column(String(32), nullable=False)

    atm: Mapped[ATM] = relationship(back_populates="observations")


class ForecastRecord(Base):
    __tablename__ = "forecast_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    atm_id: Mapped[str] = mapped_column(
        ForeignKey("atms.atm_id", ondelete="RESTRICT"),
        index=True,
    )
    forecast_date: Mapped[date] = mapped_column(Date, index=True)
    source_data_as_of: Mapped[date] = mapped_column(Date)
    predicted_demand: Mapped[int] = mapped_column(Integer)
    lower_bound: Mapped[int] = mapped_column(Integer)
    upper_bound: Mapped[int] = mapped_column(Integer)
    current_balance: Mapped[int] = mapped_column(Integer)
    capacity: Mapped[int] = mapped_column(Integer)
    recommended_replenishment: Mapped[int] = mapped_column(Integer)
    risk_level: Mapped[str] = mapped_column(String(16))
    capacity_constrained: Mapped[bool] = mapped_column(Boolean, default=False)
    forecast_mode: Mapped[str] = mapped_column(String(32), default="production")
    data_source: Mapped[str] = mapped_column(String(32), default="legacy_unknown")
    model_name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    created_by: Mapped[User] = relationship(back_populates="forecasts")
