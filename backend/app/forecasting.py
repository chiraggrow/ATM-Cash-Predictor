from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
from datetime import date, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
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
MODEL_VERSION = "hist-gradient-boosting-v3"
ARTIFACT_VERSION = 3
SYNTHETIC_PRODUCTION_BLOCK_REASON = (
    "Synthetic demonstration observations cannot be used for production forecasts; "
    "select FORECAST_MODE=historical_demo for a clearly labelled demo."
)
MODEL_CONFIGURATION = {
    "learning_rate": 0.06,
    "max_iter": 160,
    "max_leaf_nodes": 15,
    "min_samples_leaf": 15,
    "l2_regularization": 1.0,
    "early_stopping": False,
    "random_state": 42,
}
FEATURE_CONFIGURATION = {
    "numeric_features": NUMERIC_FEATURES,
    "categorical_features": CATEGORICAL_FEATURES,
    "date_features": [
        "month_sin",
        "month_cos",
        "weekday_sin",
        "weekday_cos",
        "day_of_year_sin",
        "day_of_year_cos",
    ],
    "calendar_feature_date": "Date + 1 day (next-day target date)",
    "lag_features": [],
    "numeric_imputation": "training-fold median; retain all-empty features",
    "categorical_imputation": "constant Unknown",
    "categorical_encoding": "one-hot, ignore unseen categories",
}


class StaleForecastDataError(ValueError):
    pass


class ForecastEngine:
    def __init__(
        self,
        dataset_path: Path | None,
        artifact_path: Path,
        dataset_provider: Callable[[], pd.DataFrame] | None = None,
        target_accuracy_pct: float = 85.0,
        test_size: float = 0.2,
        evaluation_output_dir: Path | None = None,
        max_forecast_data_age_days: int = 1,
    ) -> None:
        if dataset_provider is None and dataset_path is None:
            raise ValueError("dataset_path is required when no database dataset provider is configured.")
        self.dataset_path = Path(dataset_path) if dataset_path is not None else None
        self.dataset_provider = dataset_provider
        self.artifact_path = Path(artifact_path)
        self.target_accuracy_pct = target_accuracy_pct
        if not 0 < test_size < 0.5:
            raise ValueError("test_size must be greater than 0 and less than 0.5.")
        if max_forecast_data_age_days < 0:
            raise ValueError("max_forecast_data_age_days cannot be negative.")
        self.test_size = test_size
        self.max_forecast_data_age_days = max_forecast_data_age_days
        self.model: Pipeline | DummyRegressor | None = None
        self.evaluation: ModelEvaluation | None = None
        self.model_dataset_sha256: str | None = None
        self.interval_abs_error_p90 = 0.0
        self._data: pd.DataFrame | None = None
        self._data_quality_summary: dict[str, Any] | None = None
        self.evaluation_output_dir = Path(
            evaluation_output_dir or self.artifact_path.parent / "evaluation"
        )

    @property
    def feature_count(self) -> int:
        return len(NUMERIC_FEATURES) + len(CATEGORICAL_FEATURES)

    @property
    def model_data_current(self) -> bool:
        return (
            self.evaluation is not None
            and self.model_dataset_sha256 == self.evaluation.dataset_sha256
            and self.model_dataset_sha256 == self._dataframe_hash(self.data)
        )

    @property
    def training_configuration(self) -> dict[str, Any]:
        return {
            "test_size": self.test_size,
            "target_accuracy_pct": self.target_accuracy_pct,
            "validation_start_fraction": 0.65,
            "selection_metric": "WAPE, falling back to MAE if WAPE is undefined",
            "model_parameters": MODEL_CONFIGURATION,
        }

    @property
    def evaluation_artifacts_available(self) -> bool:
        required_files = (
            "metrics.json",
            "test_predictions.csv",
            "actual_vs_predicted.png",
            "forecast_demand_trend.png",
            "residual_analysis.png",
        )
        return all((self.evaluation_output_dir / name).is_file() for name in required_files)

    def forecast_availability(
        self,
        reference_date: date | None = None,
        *,
        allow_historical_demo: bool = False,
    ) -> tuple[bool, str | None]:
        if not allow_historical_demo and self._contains_synthetic_observations():
            return False, SYNTHETIC_PRODUCTION_BLOCK_REASON
        today = reference_date or pd.Timestamp.now(tz=timezone.utc).date()
        latest_date = self.data["Date"].max().date()
        forecast_date = latest_date + timedelta(days=1)
        if allow_historical_demo:
            return True, None
        if latest_date < today - timedelta(days=self.max_forecast_data_age_days):
            return False, (
                f"Latest dataset observation is {latest_date}; refresh the dataset before "
                "requesting a current forecast."
            )
        if not allow_historical_demo and forecast_date <= today:
            return False, (
                f"The next-day forecast date ({forecast_date}) is not in the future; "
                "a newer ATM observation is required."
            )
        return True, None

    def _contains_synthetic_observations(self) -> bool:
        return (
            "Data_Source" in self.data.columns
            and self.data["Data_Source"].astype(str).eq("synthetic_simulation").any()
        )

    @property
    def data_quality_summary(self) -> dict[str, Any]:
        if self._data_quality_summary is None:
            data = self.data
            numeric_columns = data.select_dtypes(include="number").columns
            numeric_ranges: dict[str, dict[str, float | None]] = {}
            for column in numeric_columns:
                finite_values = data[column].replace([np.inf, -np.inf], np.nan).dropna()
                numeric_ranges[str(column)] = {
                    "minimum": float(finite_values.min()) if not finite_values.empty else None,
                    "maximum": float(finite_values.max()) if not finite_values.empty else None,
                }
            self._data_quality_summary = {
                "observations": len(data),
                "unique_atms": int(data["ATM_ID"].nunique()),
                "distinct_dates": int(data["Date"].nunique()),
                "date_start": data["Date"].min().date().isoformat(),
                "date_end": data["Date"].max().date().isoformat(),
                "column_dtypes": {
                    str(column): str(dtype)
                    for column, dtype in data.dtypes.items()
                },
                "missing_values_by_column": {
                    str(column): int(count)
                    for column, count in data.isna().sum().items()
                    if count > 0
                },
                "exact_duplicate_rows": int(data.duplicated().sum()),
                "duplicate_atm_date_groups": int(
                    data.groupby(["ATM_ID", "Date"], dropna=False).size().gt(1).sum()
                ),
                "atms_with_changing_location_labels": int(
                    data.groupby("ATM_ID")["Location_Type"].nunique().gt(1).sum()
                ),
                "negative_numeric_values_by_column": {
                    str(column): int((data[column] < 0).sum())
                    for column in numeric_columns
                    if (data[column] < 0).any()
                },
                "infinite_numeric_values_by_column": {
                    str(column): int(np.isinf(data[column]).sum())
                    for column in numeric_columns
                    if np.isinf(data[column]).any()
                },
                "numeric_ranges_by_column": numeric_ranges,
                "observations_per_atm": {
                    "minimum": int(data.groupby("ATM_ID").size().min()),
                    "maximum": int(data.groupby("ATM_ID").size().max()),
                    "mean": float(data.groupby("ATM_ID").size().mean()),
                },
                "per_atm_observation_gap_days": self._observation_gap_summary(data),
                "zero_demand_observations": int((data[TARGET_COLUMN] == 0).sum()),
                "cash_amount_unit": "dataset units; currency not specified",
                "duplicate_rows_retained": True,
            }
        return self._data_quality_summary

    @staticmethod
    def _observation_gap_summary(dataset: pd.DataFrame) -> dict[str, float | int]:
        unique_dates = dataset[["ATM_ID", "Date"]].drop_duplicates()
        gaps = (
            unique_dates.sort_values(["ATM_ID", "Date"])
            .groupby("ATM_ID")["Date"]
            .diff()
            .dt.days.dropna()
        )
        if gaps.empty:
            return {"minimum": 0, "median": 0, "maximum": 0}
        return {
            "minimum": int(gaps.min()),
            "median": float(gaps.median()),
            "maximum": int(gaps.max()),
        }

    @property
    def data(self) -> pd.DataFrame:
        if self._data is None:
            self._data = self._load_dataset()
        return self._data

    def refresh_data(self) -> pd.DataFrame:
        self._data = self._load_dataset()
        self._data_quality_summary = None
        return self._data

    @staticmethod
    def _dataframe_hash(dataset: pd.DataFrame) -> str:
        canonical = dataset.to_csv(index=False, date_format="%Y-%m-%d").encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def _load_dataset(self) -> pd.DataFrame:
        if self.dataset_provider is not None:
            dataset = self.dataset_provider()
        else:
            if self.dataset_path is None or not self.dataset_path.is_file():
                raise FileNotFoundError(f"ATM dataset was not found: {self.dataset_path}")
            dataset = pd.read_csv(self.dataset_path)
        missing_columns = sorted(REQUIRED_COLUMNS.difference(dataset.columns))
        if missing_columns:
            raise ValueError(f"ATM dataset is missing required columns: {', '.join(missing_columns)}")
        if dataset.empty:
            raise ValueError("ATM dataset contains no observations.")

        dataset = dataset.copy()
        dataset["Date"] = pd.to_datetime(dataset["Date"], errors="coerce", format="mixed")
        if dataset["Date"].isna().any():
            raise ValueError("ATM dataset contains an invalid or missing Date value.")
        if dataset["ATM_ID"].isna().any():
            raise ValueError("ATM dataset contains a missing ATM_ID.")
        dataset["ATM_ID"] = dataset["ATM_ID"].astype(str).str.strip()
        if dataset["ATM_ID"].eq("").any():
            raise ValueError("ATM dataset contains a blank ATM_ID.")
        for column in NUMERIC_FEATURES + [TARGET_COLUMN]:
            if column not in dataset.columns:
                continue
            dataset[column] = pd.to_numeric(dataset[column], errors="coerce").replace(
                [np.inf, -np.inf],
                np.nan,
            )
        if dataset[TARGET_COLUMN].isna().any():
            raise ValueError("ATM dataset contains a missing or non-numeric cash demand target.")
        if (dataset[TARGET_COLUMN] < 0).any():
            raise ValueError("ATM dataset contains negative cash demand targets.")
        for column in ("ATM_Balance", "ATM_Capacity"):
            if dataset[column].isna().any() or (dataset[column] < 0).any():
                raise ValueError(f"ATM dataset contains missing or negative {column} values.")
        dataset = dataset.sort_values(["Date", "ATM_ID"], kind="stable").reset_index(drop=True)
        self._data_quality_summary = None
        return dataset

    @staticmethod
    def _features(
        dataset: pd.DataFrame,
        *,
        date_is_forecast_date: bool = False,
    ) -> pd.DataFrame:
        dates = pd.to_datetime(dataset["Date"], errors="raise")
        if not date_is_forecast_date:
            dates = dates + pd.Timedelta(days=1)
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
                    SimpleImputer(strategy="median", keep_empty_features=True),
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
                    HistGradientBoostingRegressor(**MODEL_CONFIGURATION),
                ),
            ]
        )

    @staticmethod
    def _wape(actual: np.ndarray, predicted: np.ndarray) -> float | None:
        denominator = float(np.abs(actual).sum())
        if denominator == 0:
            return None
        return float(np.abs(actual - predicted).sum() / denominator)

    def load_or_train(self, force: bool = False) -> ModelEvaluation:
        if force:
            self._data = None
            self._data_quality_summary = None
        if self.dataset_provider is not None:
            self.refresh_data()
            dataset_hash = self._dataframe_hash(self.data)
        else:
            if self.dataset_path is None or not self.dataset_path.is_file():
                raise FileNotFoundError(f"ATM dataset was not found: {self.dataset_path}")
            dataset_hash = hashlib.sha256(self.dataset_path.read_bytes()).hexdigest()
        if not force and self.artifact_path.is_file():
            artifact = joblib.load(self.artifact_path)
            if not isinstance(artifact, dict):
                raise ValueError("Model artifact has an unsupported format.")
            if (
                artifact.get("artifact_version") == ARTIFACT_VERSION
                and artifact.get("dataset_sha256") == dataset_hash
                and artifact.get("sklearn_version") == sklearn.__version__
                and artifact.get("feature_configuration") == FEATURE_CONFIGURATION
                and artifact.get("training_configuration") == self.training_configuration
            ):
                self.model = artifact["model"]
                self.evaluation = ModelEvaluation.model_validate(artifact["evaluation"])
                self.interval_abs_error_p90 = float(artifact["interval_abs_error_p90"])
                self.model_dataset_sha256 = dataset_hash
                return self.evaluation_report()

        self._train(dataset_hash)
        return self.evaluation_report()

    @staticmethod
    def _chronological_split(
        dataset: pd.DataFrame,
        test_size: float,
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        unique_dates = pd.Index(dataset["Date"].drop_duplicates().sort_values())
        if len(unique_dates) < 20:
            raise ValueError("At least 20 distinct dates are required for chronological model evaluation.")

        validation_start_index = max(1, int(len(unique_dates) * 0.65))
        test_start_index = max(
            validation_start_index + 1,
            int(len(unique_dates) * (1 - test_size)),
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
        return train.copy(), validation.copy(), final_train.copy(), test.copy()

    def _train(self, dataset_hash: str) -> None:
        dataset = self.data
        train, validation, final_train, test = self._chronological_split(
            dataset,
            self.test_size,
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
        candidate_validation_wape = self._wape(validation_target, candidate_validation_predictions)
        candidate_score = (
            candidate_validation_wape
            if candidate_validation_wape is not None
            else float(mean_absolute_error(validation_target, candidate_validation_predictions))
        )
        baseline_score = (
            baseline_validation_wape
            if baseline_validation_wape is not None
            else float(mean_absolute_error(validation_target, baseline_validation_predictions))
        )
        if candidate_score <= baseline_score:
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
        test_baseline = DummyRegressor(strategy="median")
        test_baseline.fit(final_train_features, final_train_target)
        test_baseline_predictions = np.maximum(0, test_baseline.predict(test_features))
        test_baseline_wape = self._wape(test_target, test_baseline_predictions)
        test_wape = self._wape(test_target, test_predictions)
        self.model = selected_model
        self.model_dataset_sha256 = dataset_hash
        accuracy_pct = (
            max(0.0, (1 - test_wape) * 100)
            if test_wape is not None
            else None
        )
        self.evaluation = ModelEvaluation(
            model_name=selected_name,
            training_rows=len(final_train),
            test_rows=len(test),
            train_end_date=(final_train["Date"].max() + pd.Timedelta(days=1)).date(),
            test_start_date=(test["Date"].min() + pd.Timedelta(days=1)).date(),
            test_end_date=(test["Date"].max() + pd.Timedelta(days=1)).date(),
            accuracy_pct=accuracy_pct,
            target_accuracy_pct=self.target_accuracy_pct,
            target_met=accuracy_pct >= self.target_accuracy_pct if accuracy_pct is not None else None,
            wape_pct=test_wape * 100 if test_wape is not None else None,
            mae=float(mean_absolute_error(test_target, test_predictions)),
            rmse=float(np.sqrt(mean_squared_error(test_target, test_predictions))),
            smape_pct=float(
                np.mean(
                    2 * np.abs(test_target - test_predictions)
                    / np.maximum(np.abs(test_target) + np.abs(test_predictions), 1)
                )
                * 100
            ),
            baseline_wape_pct=test_baseline_wape * 100 if test_baseline_wape is not None else None,
            baseline_mae=float(mean_absolute_error(test_target, test_baseline_predictions)),
            baseline_rmse=float(np.sqrt(mean_squared_error(test_target, test_baseline_predictions))),
            interval_abs_error_p90=self.interval_abs_error_p90,
            dataset_rows=len(dataset),
            dataset_sha256=dataset_hash,
            trained_at=pd.Timestamp.now(tz=timezone.utc).to_pydatetime(),
        )
        self._write_evaluation_outputs(test, test_predictions, test_baseline_predictions)
        self._persist_artifact(dataset_hash)

    def _write_evaluation_outputs(
        self,
        test: pd.DataFrame,
        predictions: np.ndarray,
        baseline_predictions: np.ndarray,
    ) -> None:
        self.evaluation_output_dir.mkdir(parents=True, exist_ok=True)
        test_results = test[["Date", "ATM_ID", TARGET_COLUMN]].copy()
        test_results = test_results.rename(columns={"Date": "observation_date"})
        test_results["Date"] = test_results["observation_date"] + pd.Timedelta(days=1)
        test_results = test_results.rename(columns={TARGET_COLUMN: "actual_demand"})
        test_results["model_prediction"] = predictions
        test_results["baseline_prediction"] = baseline_predictions
        test_results["residual"] = test_results["actual_demand"] - predictions
        test_results = test_results.sort_values(["Date", "ATM_ID"], kind="stable")
        test_results.to_csv(
            self.evaluation_output_dir / "test_predictions.csv",
            index=False,
            date_format="%Y-%m-%d",
        )

        by_date = test_results.groupby("Date", sort=True)[
            ["actual_demand", "model_prediction", "baseline_prediction"]
        ].mean()
        figure, axis = plt.subplots(figsize=(12, 5))
        axis.plot(by_date.index, by_date["actual_demand"], label="Actual", linewidth=1.8)
        axis.plot(by_date.index, by_date["model_prediction"], label="Selected model", linewidth=1.6)
        axis.plot(by_date.index, by_date["baseline_prediction"], label="Median baseline", linewidth=1.2)
        axis.set(
            title="Actual vs predicted next-day demand (chronological test period)",
            xlabel="Date",
            ylabel="Cash units",
        )
        axis.legend()
        figure.tight_layout()
        figure.savefig(self.evaluation_output_dir / "actual_vs_predicted.png", dpi=160)
        plt.close(figure)

        figure, axis = plt.subplots(figsize=(12, 5))
        axis.plot(by_date.index, by_date["model_prediction"], color="#bd2835", linewidth=1.7)
        axis.set(
            title="Predicted demand trend over chronological test period",
            xlabel="Date",
            ylabel="Average forecast cash units",
        )
        figure.tight_layout()
        figure.savefig(self.evaluation_output_dir / "forecast_demand_trend.png", dpi=160)
        plt.close(figure)

        residuals = test_results["residual"].to_numpy(dtype=float)
        figure, axes = plt.subplots(1, 2, figsize=(12, 5))
        axes[0].scatter(test_results["model_prediction"], residuals, alpha=0.35, s=12)
        axes[0].axhline(0, color="#555555", linewidth=1)
        axes[0].set(
            title="Residuals vs predicted demand",
            xlabel="Predicted cash units",
            ylabel="Actual − predicted",
        )
        axes[1].hist(residuals, bins=30, color="#bd2835", edgecolor="white")
        axes[1].set(
            title="Residual distribution",
            xlabel="Actual − predicted cash units",
            ylabel="Observations",
        )
        figure.tight_layout()
        figure.savefig(self.evaluation_output_dir / "residual_analysis.png", dpi=160)
        plt.close(figure)

        if self.evaluation is None:
            raise RuntimeError("Cannot write evaluation output before metrics are available.")
        report = {
            "evaluation": self.evaluation.model_dump(mode="json"),
            "data_quality": self.data_quality_summary,
            "training_configuration": {
                **self.training_configuration,
                "same_date_rows_kept_in_the_same_partition": True,
            },
        }
        (self.evaluation_output_dir / "metrics.json").write_text(
            json.dumps(report, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )

    def _persist_artifact(self, dataset_hash: str) -> None:
        if self.model is None or self.evaluation is None:
            raise RuntimeError("Cannot persist a model before training completes.")
        self.artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact: dict[str, Any] = {
            "artifact_version": ARTIFACT_VERSION,
            "dataset_sha256": dataset_hash,
            "sklearn_version": sklearn.__version__,
            "feature_configuration": FEATURE_CONFIGURATION,
            "training_configuration": self.training_configuration,
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
        source_values = rows.get("Data_Source", pd.Series(dtype=str)).dropna().astype(str).mode()
        snapshot["Data_Source"] = source_values.iloc[0] if not source_values.empty else "csv_offline"
        for column in NUMERIC_FEATURES:
            if column.endswith(("_sin", "_cos")):
                continue
            values = pd.to_numeric(rows[column], errors="coerce").dropna()
            snapshot[column] = float(values.mean()) if not values.empty else np.nan
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

    def forecast_next_day(
        self,
        atm_id: str,
        reference_date: date | None = None,
        *,
        allow_historical_demo: bool = False,
    ) -> dict[str, Any]:
        if self.model is None:
            raise RuntimeError("Forecast model has not been trained.")
        try:
            snapshot, source_date = self._latest_atm_snapshot(atm_id)
        except KeyError:
            raise
        if not allow_historical_demo and self._contains_synthetic_observations():
            raise StaleForecastDataError(SYNTHETIC_PRODUCTION_BLOCK_REASON)
        today = reference_date or pd.Timestamp.now(tz=timezone.utc).date()
        forecast_date = source_date + timedelta(days=1)
        if not allow_historical_demo and source_date < today - timedelta(days=self.max_forecast_data_age_days):
            raise StaleForecastDataError(
                f"Latest observation for ATM '{atm_id}' is {source_date}; refresh the dataset "
                "before requesting a current forecast."
            )
        if not allow_historical_demo and forecast_date <= today:
            raise StaleForecastDataError(
                f"The next-day forecast date ({forecast_date}) for ATM '{atm_id}' is not in "
                "the future; a newer ATM observation is required."
            )

        prediction_date = forecast_date
        snapshot["Date"] = pd.Timestamp(prediction_date)
        features = self._features(
            pd.DataFrame([snapshot]),
            date_is_forecast_date=True,
        )
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
            "data_source": str(snapshot.get("Data_Source", "csv_offline")),
            "forecast_mode": "historical_demo" if allow_historical_demo else "production",
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

    def scenario_forecasts(
        self,
        *,
        festival: bool = False,
        holiday: bool = False,
        adjustment_pct: float = 0.0,
        atm_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return clearly labelled simulation estimates for calendar/what-if assumptions.

        The festival and holiday switches replace the corresponding model inputs for the
        next-day feature row. The percentage adjustment is applied after inference as an
        explicit demand stress assumption, so it is never presented as an observed value.
        """
        if self.model is None:
            raise RuntimeError("Forecast model has not been trained.")
        if not -30 <= adjustment_pct <= 30:
            raise ValueError("adjustment_pct must be between -30 and 30.")

        available_ids = set(self.data["ATM_ID"].astype(str))
        requested_ids = (
            sorted(available_ids)
            if atm_ids is None
            else [str(atm_id) for atm_id in atm_ids]
        )
        missing_ids = sorted(set(requested_ids) - available_ids)
        if missing_ids:
            raise KeyError(missing_ids[0])

        base_records: list[dict[str, Any]] = []
        scenario_records: list[dict[str, Any]] = []
        context: list[tuple[str, dict[str, Any], date, date]] = []
        for atm_id in requested_ids:
            snapshot, source_date = self._latest_atm_snapshot(atm_id)
            forecast_date = source_date + timedelta(days=1)
            base_records.append({**snapshot, "Date": pd.Timestamp(forecast_date)})
            scenario_records.append(
                {
                    **snapshot,
                    "Date": pd.Timestamp(forecast_date),
                    "Holiday_Flag": int(holiday),
                    "Special_Event_Flag": int(festival),
                }
            )
            context.append((atm_id, snapshot, source_date, forecast_date))

        if not context:
            return []

        base_features = self._features(
            pd.DataFrame(base_records), date_is_forecast_date=True
        )
        scenario_features = self._features(
            pd.DataFrame(scenario_records), date_is_forecast_date=True
        )
        base_predictions = np.maximum(0, self.model.predict(base_features))
        scenario_predictions = np.maximum(0, self.model.predict(scenario_features))
        adjustment_factor = 1 + (adjustment_pct / 100)
        interval = self.interval_abs_error_p90
        model_name = self.evaluation_report().model_name

        results: list[dict[str, Any]] = []
        for (
            (atm_id, snapshot, source_date, forecast_date),
            base_prediction,
            scenario_prediction,
        ) in zip(context, base_predictions, scenario_predictions, strict=True):
            base_value = max(0.0, float(base_prediction))
            adjusted_value = max(0.0, float(scenario_prediction) * adjustment_factor)
            lower_bound = max(0.0, adjusted_value - interval)
            upper_bound = adjusted_value + interval
            current_balance = max(
                0, int(round(float(snapshot.get("ATM_Balance", 0) or 0)))
            )
            capacity = max(0, int(round(float(snapshot.get("ATM_Capacity", 0) or 0))))
            available_capacity = max(0, capacity - current_balance)
            recommended_replenishment = min(
                available_capacity,
                max(0, math.ceil(upper_bound - current_balance)),
            )
            risk_level = (
                "critical"
                if current_balance < lower_bound
                else "watch"
                if current_balance < upper_bound
                else "healthy"
            )
            results.append(
                {
                    "atm_id": atm_id,
                    "location_type": snapshot["Location_Type"],
                    "base_forecast": int(round(base_value)),
                    "adjusted_forecast": int(round(adjusted_value)),
                    "adjustment_pct": float(adjustment_pct),
                    "lower_bound": int(math.floor(lower_bound)),
                    "upper_bound": int(math.ceil(upper_bound)),
                    "current_balance": current_balance,
                    "capacity": capacity,
                    "cash_cover_days": (
                        current_balance / adjusted_value if adjusted_value > 0 else None
                    ),
                    "base_cash_cover_days": (
                        current_balance / base_value if base_value > 0 else None
                    ),
                    "recommended_replenishment": recommended_replenishment,
                    "risk_level": risk_level,
                    "capacity_constrained": upper_bound > capacity,
                    "source_data_as_of": source_date,
                    "forecast_date": forecast_date,
                    "data_source": str(snapshot.get("Data_Source", "unknown")),
                    "model_name": model_name,
                    "simulation": True,
                }
            )
        return results


def main() -> None:
    from app.config import Settings

    parser = argparse.ArgumentParser(description="Train and evaluate the ATM demand forecasting model.")
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--artifact", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--test-size", type=float)
    arguments = parser.parse_args()
    settings = Settings()
    artifact_path = arguments.artifact or settings.model_artifact_path
    forecaster = ForecastEngine(
        dataset_path=arguments.dataset or settings.dataset_path,
        artifact_path=artifact_path,
        target_accuracy_pct=settings.target_accuracy_pct,
        test_size=(
            arguments.test_size
            if arguments.test_size is not None
            else settings.model_test_size
        ),
        evaluation_output_dir=arguments.output_dir,
        max_forecast_data_age_days=settings.max_forecast_data_age_days,
    )
    evaluation = forecaster.load_or_train(force=True)
    print(json.dumps(evaluation.model_dump(mode="json"), indent=2))
    print(f"Evaluation artifacts: {forecaster.evaluation_output_dir.resolve()}")


if __name__ == "__main__":
    main()
