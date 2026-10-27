from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String
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


class ForecastRecord(Base):
    __tablename__ = "forecast_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    atm_id: Mapped[str] = mapped_column(String(32), index=True)
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
    model_name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    created_by: Mapped[User] = relationship(back_populates="forecasts")
