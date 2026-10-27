from __future__ import annotations

import hashlib
import math
import os
import tempfile
from datetime import date, timedelta, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from app.schemas import ModelEvaluation

TARGET_COLUMN = "Cash_Demand_Next_Day"
NUMERIC_FEATURES = [
    "Total_Withdrawals",
    "Total_Deposits",
    "Holiday_Flag",
    "Special_Event_Flag",
    "Previous_Day_Cash_Level",
    "Nearby_Competitor_ATMs",
    "ATM_Capacity",
    "ATM_Balance",
    "month_sin",
    "month_cos",
    "weekday_sin",
    "weekday_cos",
    "day_of_year_sin",
    "day_of_year_cos",
]
CATEGORICAL_FEATURES = [
    "ATM_ID",
    "Time_of_Day",
    "Location_Type",
    "Weather_Condition",
]
REQUIRED_COLUMNS = {
    "ATM_ID",
    "Date",
    "Time_of_Day",
    "Total_Withdrawals",
    "Total_Deposits",
    "Location_Type",
    "Holiday_Flag",
    "Special_Event_Flag",
    "Previous_Day_Cash_Level",
    "Weather_Condition",
    "Nearby_Competitor_ATMs",
    TARGET_COLUMN,
    "ATM_Capacity",
    "ATM_Balance",
}
MODEL_VERSION = "hist-gradient-boosting-v1"


class ForecastEngine:
    def __init__(
        self,
        dataset_path: Path,
        artifact_path: Path,
        target_accuracy_pct: float = 85.0,
        test_size: float = 0.2,
    ) -> None:
        self.dataset_path = Path(dataset_path)
        self.artifact_path = Path(artifact_path)
        self.target_accuracy_pct = target_accuracy_pct
        self.test_size = test_size
        self.model: Pipeline | DummyRegressor | None = None
        self.evaluation: ModelEvaluation | None = None
        self.interval_abs_error_p90 = 0.0
        self._data: pd.DataFrame | None = None

    @property
    def data(self) -> pd.DataFrame:
        if self._data is None:
            self._data = self._load_dataset()
        return self._data

    def _load_dataset(self) -> pd.DataFrame:
        if not self.dataset_path.is_file():
            raise FileNotFoundError(f"ATM dataset was not found: {self.dataset_path}")

        dataset = pd.read_csv(self.dataset_path)
        missing_columns = sorted(REQUIRED_COLUMNS.difference(dataset.columns))
        if missing_columns:
            raise ValueError(f"ATM dataset is missing required columns: {', '.join(missing_columns)}")
        if dataset.empty:
            raise ValueError("ATM dataset contains no observations.")

        dataset = dataset.copy()
        dataset["Date"] = pd.to_datetime(dataset["Date"], errors="coerce")
        if dataset["Date"].isna().any():
            raise ValueError("ATM dataset contains an invalid or missing Date value.")
        for column in NUMERIC_FEATURES + [TARGET_COLUMN]:
            if column not in dataset.columns:
                continue
            dataset[column] = pd.to_numeric(dataset[column], errors="coerce")
        if dataset[TARGET_COLUMN].isna().any():
            raise ValueError("ATM dataset contains a missing or non-numeric cash demand target.")
        if (dataset[TARGET_COLUMN] < 0).any():
            raise ValueError("ATM dataset contains negative cash demand targets.")
        for column in ("ATM_Balance", "ATM_Capacity"):
            if dataset[column].isna().any() or (dataset[column] < 0).any():
                raise ValueError(f"ATM dataset contains missing or negative {column} values.")
        if dataset["ATM_ID"].isna().any():
            raise ValueError("ATM dataset contains a missing ATM_ID.")
        dataset["ATM_ID"] = dataset["ATM_ID"].astype(str)
        return dataset.sort_values("Date", kind="stable").reset_index(drop=True)

    @staticmethod
    def _features(dataset: pd.DataFrame) -> pd.DataFrame:
        dates = pd.to_datetime(dataset["Date"], errors="raise")
        month_angle = 2 * np.pi * (dates.dt.month - 1) / 12
        weekday_angle = 2 * np.pi * dates.dt.dayofweek / 7
        year_angle = 2 * np.pi * (dates.dt.dayofyear - 1) / 365.25
        features = dataset.copy()
        features["month_sin"] = np.sin(month_angle)
        features["month_cos"] = np.cos(month_angle)
        features["weekday_sin"] = np.sin(weekday_angle)
        features["weekday_cos"] = np.cos(weekday_angle)
        features["day_of_year_sin"] = np.sin(year_angle)
        features["day_of_year_cos"] = np.cos(year_angle)
        return features[NUMERIC_FEATURES + CATEGORICAL_FEATURES]

    @staticmethod
    def _pipeline() -> Pipeline:
        preprocessing = ColumnTransformer(
            transformers=[
                (
                    "numeric",
                    SimpleImputer(strategy="median"),
                    NUMERIC_FEATURES,
                ),
                (
                    "categorical",
                    Pipeline(
                        steps=[
                            ("imputer", SimpleImputer(strategy="constant", fill_value="Unknown")),
                            ("one_hot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
                        ]
                    ),
                    CATEGORICAL_FEATURES,
                ),
            ],
            remainder="drop",
        )
        return Pipeline(
            steps=[
                ("preprocessor", preprocessing),
                (
                    "regressor",
                    HistGradientBoostingRegressor(
                        learning_rate=0.06,
                        max_iter=160,
                        max_leaf_nodes=15,
                        min_samples_leaf=15,
                        l2_regularization=1.0,
                        early_stopping=False,
                        random_state=42,
                    ),
                ),
            ]
        )

    @staticmethod
    def _wape(actual: np.ndarray, predicted: np.ndarray) -> float:
        denominator = float(np.abs(actual).sum())
        if denominator == 0:
            return 0.0 if np.allclose(actual, predicted) else 1.0
        return float(np.abs(actual - predicted).sum() / denominator)

    def load_or_train(self, force: bool = False) -> ModelEvaluation:
        if force:
            self._data = None
        dataset_hash = hashlib.sha256(self.dataset_path.read_bytes()).hexdigest()
        if not force and self.artifact_path.is_file():
            artifact = joblib.load(self.artifact_path)
            if (
                artifact.get("dataset_sha256") == dataset_hash
                and artifact.get("sklearn_version") == sklearn.__version__
            ):
                self.model = artifact["model"]
                self.evaluation = ModelEvaluation.model_validate(artifact["evaluation"])
                self.interval_abs_error_p90 = float(artifact["interval_abs_error_p90"])
                return self.evaluation_report()

        self._train(dataset_hash)
        return self.evaluation_report()

    def _train(self, dataset_hash: str) -> None:
        dataset = self.data
        unique_dates = pd.Index(dataset["Date"].drop_duplicates().sort_values())
        if len(unique_dates) < 20:
            raise ValueError("At least 20 distinct dates are required for chronological model evaluation.")

        validation_start_index = max(1, int(len(unique_dates) * 0.65))
        test_start_index = max(
            validation_start_index + 1,
            int(len(unique_dates) * (1 - self.test_size)),
        )
        test_start_index = min(test_start_index, len(unique_dates) - 1)
        validation_start = unique_dates[validation_start_index]
        test_start = unique_dates[test_start_index]
        train = dataset.loc[dataset["Date"] < validation_start]
        validation = dataset.loc[
            (dataset["Date"] >= validation_start) & (dataset["Date"] < test_start)
        ]
        final_train = dataset.loc[dataset["Date"] < test_start]
        test = dataset.loc[dataset["Date"] >= test_start]
        if train.empty or validation.empty or final_train.empty or test.empty:
            raise ValueError(
                "The chronological train, validation, and test partitions must all contain observations."
            )

        train_features = self._features(train)
        validation_features = self._features(validation)
        final_train_features = self._features(final_train)
        test_features = self._features(test)
        train_target = train[TARGET_COLUMN].to_numpy(dtype=float)
        validation_target = validation[TARGET_COLUMN].to_numpy(dtype=float)
        final_train_target = final_train[TARGET_COLUMN].to_numpy(dtype=float)
        test_target = test[TARGET_COLUMN].to_numpy(dtype=float)
        baseline = DummyRegressor(strategy="median")
        baseline.fit(train_features, train_target)
        baseline_validation_predictions = np.maximum(
            0,
            baseline.predict(validation_features),
        )
        baseline_validation_wape = self._wape(
            validation_target,
            baseline_validation_predictions,
        )
        candidate = self._pipeline()
        candidate.fit(train_features, train_target)
        candidate_validation_predictions = np.maximum(
            0,
            candidate.predict(validation_features),
        )
        candidate_validation_wape = self._wape(
            validation_target,
            candidate_validation_predictions,
        )
        if candidate_validation_wape <= baseline_validation_wape:
            selected_model: Pipeline | DummyRegressor = candidate
            selected_name = MODEL_VERSION
            validation_predictions = candidate_validation_predictions
        else:
            selected_model = baseline
            selected_name = "training-median-baseline-v1"
            validation_predictions = baseline_validation_predictions

        residuals = np.abs(validation_target - validation_predictions)
        self.interval_abs_error_p90 = float(np.quantile(residuals, 0.9))
        selected_model.fit(final_train_features, final_train_target)
        test_predictions = np.maximum(0, selected_model.predict(test_features))
        test_wape = self._wape(test_target, test_predictions)
        test_baseline = DummyRegressor(strategy="median")
        test_baseline.fit(final_train_features, final_train_target)
        test_baseline_predictions = np.maximum(0, test_baseline.predict(test_features))
        test_baseline_wape = self._wape(test_target, test_baseline_predictions)
        balances = test["ATM_Balance"].to_numpy(dtype=float)
        capacities = test["ATM_Capacity"].to_numpy(dtype=float)
        available_capacity = np.maximum(0, capacities - balances)
        suggested_replenishment = np.minimum(
            available_capacity,
            np.maximum(0, test_predictions + self.interval_abs_error_p90 - balances),
        )
        baseline_stockout = balances < test_target
        simulated_stockout = balances + suggested_replenishment < test_target
        baseline_stockout_count = int(baseline_stockout.sum())
        remaining_stockout_count = int(simulated_stockout.sum())
        stockout_reduction_pct = (
            (baseline_stockout_count - remaining_stockout_count)
            / baseline_stockout_count
            * 100
            if baseline_stockout_count
            else 0.0
        )
        self.model = selected_model
        self.evaluation = ModelEvaluation(
            model_name=selected_name,
            training_rows=len(final_train),
            test_rows=len(test),
            train_end_date=final_train["Date"].max().date(),
            test_start_date=test["Date"].min().date(),
            test_end_date=test["Date"].max().date(),
            accuracy_pct=max(0.0, (1 - test_wape) * 100),
            target_accuracy_pct=self.target_accuracy_pct,
            target_met=(1 - test_wape) * 100 >= self.target_accuracy_pct,
            wape_pct=test_wape * 100,
            mae=float(mean_absolute_error(test_target, test_predictions)),
            rmse=float(np.sqrt(mean_squared_error(test_target, test_predictions))),
            smape_pct=float(
                np.mean(
                    2 * np.abs(test_target - test_predictions)
                    / np.maximum(np.abs(test_target) + np.abs(test_predictions), 1)
                )
                * 100
            ),
            baseline_wape_pct=test_baseline_wape * 100,
            interval_abs_error_p90=self.interval_abs_error_p90,
            cashout_proxy_rate_pct=float(baseline_stockout.mean() * 100),
            simulated_cashout_reduction_pct=stockout_reduction_pct,
            cashout_reduction_target_pct=70.0,
            cashout_reduction_target_met=stockout_reduction_pct >= 70.0,
            baseline_cashout_proxy_events=baseline_stockout_count,
            simulated_cashout_proxy_events=remaining_stockout_count,
            dataset_rows=len(dataset),
            dataset_sha256=dataset_hash,
            trained_at=pd.Timestamp.now(tz=timezone.utc).to_pydatetime(),
        )
        self._persist_artifact(dataset_hash)

    def _persist_artifact(self, dataset_hash: str) -> None:
        if self.model is None or self.evaluation is None:
            raise RuntimeError("Cannot persist a model before training completes.")
        self.artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact: dict[str, Any] = {
            "dataset_sha256": dataset_hash,
            "sklearn_version": sklearn.__version__,
            "model": self.model,
            "evaluation": self.evaluation.model_dump(mode="json"),
            "interval_abs_error_p90": self.interval_abs_error_p90,
        }
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.artifact_path.name}.",
            suffix=".tmp",
            dir=self.artifact_path.parent,
        )
        os.close(descriptor)
        temporary_path = Path(temporary_name)
        try:
            joblib.dump(artifact, temporary_path)
            temporary_path.replace(self.artifact_path)
        finally:
            temporary_path.unlink(missing_ok=True)

    def evaluation_report(self) -> ModelEvaluation:
        if self.evaluation is None:
            raise RuntimeError("Forecast model has not been trained.")
        evaluation = self.evaluation
        return evaluation

    def _latest_atm_snapshot(self, atm_id: str) -> tuple[dict[str, Any], date]:
        atm_rows = self.data.loc[self.data["ATM_ID"] == atm_id]
        if atm_rows.empty:
            raise KeyError(atm_id)
        last_date = atm_rows["Date"].max()
        rows = atm_rows.loc[atm_rows["Date"] == last_date]
        snapshot: dict[str, Any] = {"ATM_ID": atm_id, "Date": last_date}

        for column in CATEGORICAL_FEATURES:
            mode = rows[column].dropna().astype(str).mode()
            snapshot[column] = mode.iloc[0] if not mode.empty else "Unknown"
        for column in NUMERIC_FEATURES:
            if column.endswith(("_sin", "_cos")):
                continue
            values = pd.to_numeric(rows[column], errors="coerce").dropna()
            if not values.empty:
                snapshot[column] = float(values.mean())
        snapshot["Date"] = (last_date + pd.Timedelta(days=1)).date()
        return snapshot, last_date.date()

    def latest_atm_records(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for atm_id in sorted(self.data["ATM_ID"].unique()):
            snapshot, source_date = self._latest_atm_snapshot(atm_id)
            raw_rows = self.data.loc[
                (self.data["ATM_ID"] == atm_id) & (self.data["Date"].dt.date == source_date)
            ]
            demand = float(raw_rows[TARGET_COLUMN].mean())
            balance = float(raw_rows["ATM_Balance"].mean())
            capacity = float(raw_rows["ATM_Capacity"].mean())
            coverage = balance / demand if demand > 0 else None
            risk = "critical" if coverage is not None and coverage < 1 else (
                "watch" if coverage is not None and coverage < 1.25 else "healthy"
            )
            rows.append(
                {
                    "atm_id": atm_id,
                    "location_type": snapshot["Location_Type"],
                    "last_observed_at": source_date,
                    "demand": demand,
                    "balance": balance,
                    "capacity": capacity,
                    "replenishment_required": bool(
                        (raw_rows.get("Replenishment_Required", pd.Series(dtype=str)) == "Yes").any()
                    ),
                    "coverage_ratio": coverage,
                    "risk_level": risk,
                }
            )
        return rows

    def forecast_next_day(self, atm_id: str) -> dict[str, Any]:
        if self.model is None:
            raise RuntimeError("Forecast model has not been trained.")
        try:
            snapshot, source_date = self._latest_atm_snapshot(atm_id)
        except KeyError:
            raise

        prediction_date = source_date + timedelta(days=1)
        snapshot["Date"] = pd.Timestamp(prediction_date)
        features = self._features(pd.DataFrame([snapshot]))
        predicted_demand = max(0, float(self.model.predict(features)[0]))
        interval = self.interval_abs_error_p90
        lower_bound = max(0, predicted_demand - interval)
        upper_bound = predicted_demand + interval
        current_balance = max(0, int(round(snapshot.get("ATM_Balance", 0))))
        capacity = max(0, int(round(snapshot.get("ATM_Capacity", 0))))
        available_capacity = max(0, capacity - current_balance)
        recommendation = min(
            available_capacity,
            max(0, math.ceil(upper_bound - current_balance)),
        )
        risk = (
            "critical"
            if current_balance < lower_bound
            else "watch"
            if current_balance < upper_bound
            else "healthy"
        )

        return {
            "atm_id": atm_id,
            "forecast_date": prediction_date,
            "source_data_as_of": source_date,
            "predicted_demand": int(round(predicted_demand)),
            "lower_bound": int(math.floor(lower_bound)),
            "upper_bound": int(math.ceil(upper_bound)),
            "current_balance": current_balance,
            "capacity": capacity,
            "recommended_replenishment": recommendation,
            "risk_level": risk,
            "capacity_constrained": upper_bound > capacity,
            "model_name": self.evaluation_report().model_name,
        }
