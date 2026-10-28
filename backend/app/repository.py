from __future__ import annotations

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import ATM, ATMObservation

FORECAST_DATA_COLUMNS = [
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
    "Data_Source",
]


def load_forecast_dataset(
    session_factory: sessionmaker[Session],
    data_source: str,
) -> pd.DataFrame:
    with session_factory() as session:
        rows = session.execute(
            select(ATMObservation, ATM)
            .join(ATM, ATMObservation.atm_id == ATM.atm_id)
            .where(
                ATM.data_source == data_source,
                ATMObservation.data_source == data_source,
            )
            .order_by(ATMObservation.observed_on, ATMObservation.atm_id)
        ).all()

    records = [
        {
            "ATM_ID": observation.atm_id,
            "Date": observation.observed_on,
            "Day_of_Week": observation.observed_on.strftime("%A"),
            "Time_of_Day": observation.time_of_day or "Unknown",
            "Total_Withdrawals": float(observation.total_withdrawals),
            "Total_Deposits": float(observation.total_deposits),
            "Location_Type": atm.location_type,
            "Holiday_Flag": int(observation.holiday_flag),
            "Special_Event_Flag": int(observation.special_event_flag),
            "Previous_Day_Cash_Level": float(observation.opening_cash_balance),
            "Weather_Condition": observation.weather_condition,
            "Nearby_Competitor_ATMs": observation.nearby_competitor_atms,
            "Cash_Demand_Next_Day": float(observation.next_day_demand),
            "ATM_Capacity": float(atm.capacity),
            "ATM_Balance": float(observation.closing_cash_balance),
            "Replenishment_Amount": float(observation.replenishment_amount),
            "Replenishment_Required": (
                "Yes" if observation.replenishment_amount > 0 else "No"
            ),
            "Data_Source": observation.data_source,
        }
        for observation, atm in rows
    ]
    dataset = pd.DataFrame.from_records(records, columns=FORECAST_DATA_COLUMNS)
    if not dataset.empty:
        dataset["Date"] = pd.to_datetime(dataset["Date"], errors="raise")
    return dataset
