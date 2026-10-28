from datetime import date, timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

from app.forecasting import ForecastEngine, StaleForecastDataError


def build_engine(dataset_path: Path, tmp_path: Path) -> ForecastEngine:
    return ForecastEngine(
        dataset_path=dataset_path,
        artifact_path=tmp_path / "artifacts" / "test-model.joblib",
    )


def test_dataset_profile_retains_duplicate_atm_date_observations(
    dataset_path: Path,
    tmp_path: Path,
) -> None:
    engine = build_engine(dataset_path, tmp_path)

    assert len(engine.data) == 161
    assert engine.data_quality_summary["duplicate_atm_date_groups"] == 1
    assert engine.data_quality_summary["exact_duplicate_rows"] == 0
    assert engine.data_quality_summary["duplicate_rows_retained"] is True
    assert engine.data_quality_summary["date_start"] == (
        date.today() - timedelta(days=79)
    ).isoformat()
    assert engine.data_quality_summary["date_end"] == date.today().isoformat()


def test_chronological_split_keeps_all_rows_for_a_date_together(
    dataset_path: Path,
    tmp_path: Path,
) -> None:
    engine = build_engine(dataset_path, tmp_path)
    train, validation, final_train, test = engine._chronological_split(engine.data, 0.2)

    train_dates = set(train["Date"])
    validation_dates = set(validation["Date"])
    test_dates = set(test["Date"])
    assert train["Date"].max() < validation["Date"].min()
    assert validation["Date"].max() < test["Date"].min()
    assert not train_dates.intersection(validation_dates)
    assert not validation_dates.intersection(test_dates)
    assert not final_train["Date"].isin(test_dates).any()
    assert set(train.index).isdisjoint(validation.index)


def test_training_calendar_features_target_the_following_day(
    dataset_path: Path,
    tmp_path: Path,
) -> None:
    engine = build_engine(dataset_path, tmp_path)
    sample = engine.data.iloc[[0]]
    features = engine._features(sample)
    forecast_date = sample["Date"].iloc[0] + pd.Timedelta(days=1)
    weekday_angle = 2 * np.pi * forecast_date.dayofweek / 7

    assert features.iloc[0]["weekday_sin"] == pytest.approx(np.sin(weekday_angle))
    assert features.iloc[0]["weekday_cos"] == pytest.approx(np.cos(weekday_angle))


def test_wape_is_undefined_when_actual_total_is_zero() -> None:
    assert ForecastEngine._wape(np.array([0.0, 0.0]), np.array([0.0, 1.0])) is None


def test_empty_operational_provider_does_not_fall_back_to_csv(
    dataset_path: Path,
    tmp_path: Path,
) -> None:
    empty_provider_data = pd.read_csv(dataset_path).iloc[:0]
    engine = ForecastEngine(
        dataset_path=dataset_path,
        dataset_provider=lambda: empty_provider_data,
        artifact_path=tmp_path / "empty-provider" / "model.joblib",
    )

    with pytest.raises(ValueError, match="contains no observations"):
        engine.load_or_train()


def test_training_persists_metrics_plots_and_preprocessing(
    dataset_path: Path,
    tmp_path: Path,
) -> None:
    engine = build_engine(dataset_path, tmp_path)
    evaluation = engine.load_or_train()

    assert evaluation.test_rows > 0
    assert evaluation.baseline_mae >= 0
    assert evaluation.baseline_rmse >= 0
    assert evaluation.mae >= 0
    assert evaluation.rmse >= 0
    assert evaluation.dataset_rows == 161
    assert engine.evaluation_artifacts_available

    artifact = joblib.load(engine.artifact_path)
    assert artifact["feature_configuration"]["lag_features"] == []
    assert artifact["artifact_version"] == 3
    assert artifact["training_configuration"]["model_parameters"]["random_state"] == 42
    expected_outputs = {
        "metrics.json",
        "test_predictions.csv",
        "actual_vs_predicted.png",
        "forecast_demand_trend.png",
        "residual_analysis.png",
    }
    assert expected_outputs.issubset({path.name for path in engine.evaluation_output_dir.iterdir()})
    predictions = pd.read_csv(engine.evaluation_output_dir / "test_predictions.csv")
    assert len(predictions) == evaluation.test_rows
    assert predictions["model_prediction"].ge(0).all()
    assert pd.to_datetime(predictions["Date"]).equals(
        pd.to_datetime(predictions["observation_date"]) + pd.Timedelta(days=1)
    )
    assert evaluation.test_start_date == (
        pd.to_datetime(predictions["Date"]).min().date()
    )
    assert evaluation.test_end_date == (
        pd.to_datetime(predictions["Date"]).max().date()
    )

    cached_engine = build_engine(dataset_path, tmp_path)
    cached = cached_engine.load_or_train()
    assert cached.dataset_sha256 == evaluation.dataset_sha256
    assert cached_engine.model is not None
    assert cached_engine.forecast_next_day("ATM_0001") == engine.forecast_next_day("ATM_0001")

    changed_configuration = ForecastEngine(
        dataset_path=dataset_path,
        artifact_path=engine.artifact_path,
        target_accuracy_pct=80,
    )
    changed_configuration.load_or_train()
    refreshed_artifact = joblib.load(engine.artifact_path)
    assert refreshed_artifact["training_configuration"]["target_accuracy_pct"] == 80


def test_forecast_returns_one_day_after_latest_atm_data(
    dataset_path: Path,
    tmp_path: Path,
) -> None:
    engine = build_engine(dataset_path, tmp_path)
    engine.load_or_train()

    forecast = engine.forecast_next_day("ATM_0001")

    assert forecast["forecast_date"] > forecast["source_data_as_of"]
    assert forecast["lower_bound"] <= forecast["predicted_demand"] <= forecast["upper_bound"]
    assert forecast["recommended_replenishment"] <= (
        forecast["capacity"] - forecast["current_balance"]
    )


def test_stale_data_is_not_returned_as_a_current_forecast(
    dataset_path: Path,
    tmp_path: Path,
) -> None:
    engine = build_engine(dataset_path, tmp_path)
    engine.load_or_train()

    with pytest.raises(StaleForecastDataError, match="refresh the dataset"):
        engine.forecast_next_day(
            "ATM_0001",
            reference_date=date.today() + timedelta(days=2),
        )


def test_missing_numeric_feature_is_reported_and_imputed(
    dataset_path: Path,
    tmp_path: Path,
) -> None:
    data = pd.read_csv(dataset_path)
    data["Total_Deposits"] = np.nan
    missing_feature_path = tmp_path / "missing-feature.csv"
    data.to_csv(missing_feature_path, index=False)
    engine = build_engine(missing_feature_path, tmp_path)
    engine.load_or_train()

    profile = engine.data_quality_summary
    assert profile["missing_values_by_column"]["Total_Deposits"] == len(data)
    assert profile["numeric_ranges_by_column"]["Total_Deposits"] == {
        "minimum": None,
        "maximum": None,
    }
    assert engine.forecast_next_day("ATM_0001")["predicted_demand"] >= 0


def test_invalid_date_is_reported_without_dropping_rows(
    dataset_path: Path,
    tmp_path: Path,
) -> None:
    data = pd.read_csv(dataset_path)
    data.loc[0, "Date"] = "not-a-date"
    invalid_path = tmp_path / "invalid-date.csv"
    data.to_csv(invalid_path, index=False)
    engine = build_engine(invalid_path, tmp_path)

    with pytest.raises(ValueError, match="invalid or missing Date"):
        _ = engine.data
