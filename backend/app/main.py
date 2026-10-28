from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from collections.abc import Generator
from datetime import date, datetime, timezone
from typing import Annotated

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import Settings
from app.database import Base, build_engine, build_session_factory, yield_session
from app.forecasting import StaleForecastDataError, TARGET_COLUMN, ForecastEngine
from app.models import ATM, ATMObservation, ForecastRecord, User
from app.repository import load_forecast_dataset
from app.schemas import (
    ATMMetadataPage,
    ATMMetadataResponse,
    ATMObservationPage,
    ATMObservationResponse,
    AtmPage,
    AtmResponse,
    DashboardSummary,
    DemandPoint,
    DemandSeriesPoint,
    DemandSeriesResponse,
    DatabaseSummary,
    ForecastHistory,
    ForecastRequest,
    ForecastResponse,
    LocationDemand,
    ModelEvaluation,
    ModelStatus,
    NextDemandForecast,
    ScenarioForecast,
    ScenarioRequest,
    ScenarioResponse,
    TokenResponse,
    UserResponse,
)
from app.security import (
    build_admin_dependency,
    build_current_user_dependency,
    create_access_token,
    hash_password,
    verify_password,
)

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()
    engine = build_engine(config.database_url)
    session_factory = build_session_factory(engine)

    def get_session() -> Generator[Session, None, None]:
        yield from yield_session(session_factory)

    def database_dataset() -> pd.DataFrame:
        return load_forecast_dataset(session_factory, config.operational_data_source)

    current_user = build_current_user_dependency(config, get_session)
    admin_user = build_admin_dependency(current_user)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        config.validate_secrets()
        if config.create_schema_on_startup:
            Base.metadata.create_all(bind=engine)
        with session_factory() as session:
            session.execute(text("SELECT 1"))
        with session_factory() as session:
            admin = session.scalar(select(User).where(User.username == config.admin_username))
            if admin is None:
                session.add(
                    User(
                        username=config.admin_username,
                        password_hash=hash_password(config.admin_password.get_secret_value()),
                        role="admin",
                        is_active=True,
                    )
                )
                session.commit()

        app.state.forecaster = ForecastEngine(
            dataset_path=None,
            artifact_path=config.model_artifact_path,
            dataset_provider=database_dataset,
            target_accuracy_pct=config.target_accuracy_pct,
            test_size=config.model_test_size,
            max_forecast_data_age_days=config.max_forecast_data_age_days,
        )
        app.state.forecaster.load_or_train()
        yield
        engine.dispose()

    app = FastAPI(
        title=config.app_name,
        description=(
            "ATM cash demand forecasting, holdout evaluation, inventory recommendations, "
            "and audit history. All cash amounts are reported in dataset units."
        ),
        version="1.0.0",
        lifespan=lifespan,
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
        redoc_url="/api/v1/redoc",
    )
    app.state.settings = config
    app.state.database_dataset = database_dataset
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.exception_handler(SQLAlchemyError)
    async def database_error_handler(_request, error: SQLAlchemyError):
        logger.error("Database operation failed: %s", type(error).__name__)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "The operational database is unavailable."},
        )

    @app.get("/health/live", tags=["health"])
    def live_health() -> dict[str, str]:
        return {"status": "alive"}

    @app.get("/health/ready", tags=["health"])
    def ready_health() -> dict[str, str]:
        try:
            with session_factory() as session:
                session.execute(text("SELECT 1"))
        except SQLAlchemyError as error:
            logger.exception("Database readiness check failed.")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database is not ready.",
            ) from error
        if not hasattr(app.state, "forecaster") or app.state.forecaster.model is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Forecast model is not ready.",
            )
        return {"status": "ready"}

    @app.post(
        "/api/v1/auth/token",
        response_model=TokenResponse,
        tags=["authentication"],
    )
    def login(
        form: Annotated[OAuth2PasswordRequestForm, Depends()],
        db: Session = Depends(get_session),
    ) -> TokenResponse:
        user = db.scalar(select(User).where(User.username == form.username))
        if user is None or not user.is_active or not verify_password(
            form.password, user.password_hash
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        token, expires_in = create_access_token(user, config)
        return TokenResponse(access_token=token, expires_in=expires_in)

    @app.get("/api/v1/auth/me", response_model=UserResponse, tags=["authentication"])
    def who_am_i(user: User = Depends(current_user)) -> UserResponse:
        return UserResponse(username=user.username, role=user.role)

    @app.get(
        "/api/v1/analytics/summary",
        response_model=DashboardSummary,
        tags=["analytics"],
    )
    def dashboard_summary(
        user: User = Depends(current_user),
    ) -> DashboardSummary:
        forecaster: ForecastEngine = app.state.forecaster
        data = forecaster.refresh_data()
        latest_atms = forecaster.latest_atm_records()
        duplicate_groups = int(
            data.groupby(["ATM_ID", "Date"], dropna=False).size().gt(1).sum()
        )
        changing_location_atms = int(
            data.groupby("ATM_ID")["Location_Type"].nunique().gt(1).sum()
        )
        latest_date = data["Date"].max().date()
        return DashboardSummary(
            record_count=len(data),
            atm_count=len(latest_atms),
            average_demand=float(data[TARGET_COLUMN].mean()),
            total_replenishment_flags=sum(
                atm["replenishment_required"] for atm in latest_atms
            ),
            at_risk_atms=sum(atm["risk_level"] == "critical" for atm in latest_atms),
            duplicate_atm_date_groups=duplicate_groups,
            changing_location_atms=changing_location_atms,
            latest_dataset_date=latest_date,
            model=forecaster.evaluation_report(),
        )

    @app.get(
        "/api/v1/analytics/demand-trend",
        response_model=list[DemandPoint],
        tags=["analytics"],
    )
    def demand_trend(
        months: Annotated[int, Query(ge=1, le=36)] = 12,
        user: User = Depends(current_user),
    ) -> list[DemandPoint]:
        data = app.state.forecaster.refresh_data()
        latest = data["Date"].max()
        cutoff = latest - pd.DateOffset(months=months)
        selected = data.loc[data["Date"] > cutoff].copy()
        selected["period"] = selected["Date"].dt.strftime("%Y-%m")
        grouped = selected.groupby("period")[TARGET_COLUMN].agg(["mean", "count"])
        return [
            DemandPoint(
                period=period,
                average_demand=float(row["mean"]),
                observations=int(row["count"]),
            )
            for period, row in grouped.iterrows()
        ]

    @app.get(
        "/api/v1/analytics/location-demand",
        response_model=list[LocationDemand],
        tags=["analytics"],
    )
    def location_demand(
        months: Annotated[int, Query(ge=1, le=36)] = 12,
        user: User = Depends(current_user),
    ) -> list[LocationDemand]:
        data = app.state.forecaster.refresh_data()
        cutoff = data["Date"].max() - pd.DateOffset(months=months)
        selected = data.loc[data["Date"] > cutoff]
        grouped = (
            selected.groupby("Location_Type")[TARGET_COLUMN]
            .agg(["mean", "count"])
            .sort_values("mean", ascending=False)
        )
        return [
            LocationDemand(
                location_type=str(location),
                average_demand=float(row["mean"]),
                observations=int(row["count"]),
            )
            for location, row in grouped.iterrows()
        ]

    @app.get(
        "/api/v1/analytics/demand-series",
        response_model=DemandSeriesResponse,
        tags=["analytics"],
    )
    def demand_series(
        months: Annotated[int, Query(ge=1, le=36)] = 12,
        atm_id: Annotated[str | None, Query(max_length=32)] = None,
        user: User = Depends(current_user),
    ) -> DemandSeriesResponse:
        forecaster: ForecastEngine = app.state.forecaster
        data = forecaster.refresh_data()
        if atm_id and atm_id not in set(data["ATM_ID"].astype(str)):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"ATM '{atm_id}' was not found in the operating dataset.",
            )

        latest = data["Date"].max()
        cutoff = latest - pd.DateOffset(months=months)
        selected = data.loc[data["Date"] > cutoff]
        if atm_id:
            selected = selected.loc[selected["ATM_ID"].astype(str) == atm_id]
        selected = selected.sort_values(["Date", "ATM_ID"], kind="stable")
        grouped = (
            selected.groupby("Date", sort=True)[TARGET_COLUMN]
            .agg(["mean", "count"])
            .sort_index()
        )

        predictions: dict[date, float] = {}
        prediction_available = False
        prediction_path = forecaster.evaluation_output_dir / "test_predictions.csv"
        if prediction_path.is_file() and not grouped.empty:
            try:
                prediction_frame = pd.read_csv(prediction_path)
                required_columns = {"observation_date", "ATM_ID", "model_prediction"}
                if required_columns.issubset(prediction_frame.columns):
                    prediction_frame["observation_date"] = pd.to_datetime(
                        prediction_frame["observation_date"], errors="coerce"
                    ).dt.normalize()
                    prediction_frame = prediction_frame.dropna(
                        subset=["observation_date", "model_prediction"]
                    )
                    prediction_frame = prediction_frame.loc[
                        prediction_frame["observation_date"] > cutoff
                    ]
                    if atm_id:
                        prediction_frame = prediction_frame.loc[
                            prediction_frame["ATM_ID"].astype(str) == atm_id
                        ]
                    if not prediction_frame.empty:
                        by_date = prediction_frame.groupby("observation_date")[
                            "model_prediction"
                        ].mean()
                        predictions = {
                            timestamp.date(): float(value)
                            for timestamp, value in by_date.items()
                            if pd.notna(value)
                        }
                        prediction_available = bool(predictions)
            except (OSError, ValueError, pd.errors.ParserError) as error:
                logger.warning("Evaluation predictions could not be read: %s", type(error).__name__)

        points = [
            DemandSeriesPoint(
                date=timestamp.date(),
                observed=float(row["mean"]),
                prediction=predictions.get(timestamp.date()),
                observations=int(row["count"]),
            )
            for timestamp, row in grouped.iterrows()
        ]
        data_sources = (
            selected.get("Data_Source", pd.Series(dtype=str))
            .dropna()
            .astype(str)
        )
        data_source = (
            str(data_sources.mode().iloc[0])
            if not data_sources.empty
            else config.operational_data_source
        )

        next_forecast = None
        try:
            estimates = forecaster.scenario_forecasts(
                atm_ids=[atm_id] if atm_id else None
            )
        except (KeyError, RuntimeError, ValueError):
            estimates = []
        if estimates:
            next_forecast = NextDemandForecast(
                forecast_date=estimates[0]["forecast_date"],
                predicted_demand=(
                    estimates[0]["base_forecast"]
                    if atm_id
                    else sum(item["base_forecast"] for item in estimates) / len(estimates)
                ),
                scope="atm" if atm_id else "network",
                data_source=str(estimates[0]["data_source"]),
                model_name=str(estimates[0]["model_name"]),
                note=(
                    "Simulation estimate from the trained model and latest observation per ATM. "
                    "Not an operational forecast."
                ),
            )

        return DemandSeriesResponse(
            scope="atm" if atm_id else "network",
            atm_id=atm_id,
            start_date=(
                selected["Date"].min().date()
                if not selected.empty
                else latest.date()
            ),
            end_date=latest.date(),
            data_source=data_source,
            observations=len(selected),
            prediction_available=prediction_available,
            points=points,
            next_forecast=next_forecast,
        )

    @app.get("/api/v1/model/evaluation", response_model=ModelEvaluation, tags=["model"])
    def model_evaluation(user: User = Depends(current_user)) -> ModelEvaluation:
        app.state.forecaster.refresh_data()
        return app.state.forecaster.evaluation_report()

    @app.get("/api/v1/model/status", response_model=ModelStatus, tags=["model"])
    def model_status(user: User = Depends(current_user)) -> ModelStatus:
        forecaster: ForecastEngine = app.state.forecaster
        data = forecaster.refresh_data()
        evaluation = forecaster.evaluation
        forecast_available, forecast_blocked_reason = forecaster.forecast_availability(
            allow_historical_demo=config.forecast_mode == "historical_demo",
        )
        return ModelStatus(
            loaded=forecaster.model is not None,
            data_source=config.operational_data_source,
            model_data_current=forecaster.model_data_current,
            model_name=evaluation.model_name if evaluation else None,
            forecast_mode=config.forecast_mode,
            forecast_available=forecast_available,
            forecast_blocked_reason=forecast_blocked_reason,
            training_rows=evaluation.training_rows if evaluation else None,
            test_rows=evaluation.test_rows if evaluation else None,
            dataset_rows=len(data),
            atm_count=int(data["ATM_ID"].nunique()),
            dataset_start_date=data["Date"].min().date(),
            dataset_end_date=data["Date"].max().date(),
            trained_at=evaluation.trained_at if evaluation else None,
            feature_count=forecaster.feature_count,
            evaluation_artifacts_available=forecaster.evaluation_artifacts_available,
        )

    @app.post(
        "/api/v1/admin/model/retrain",
        response_model=ModelEvaluation,
        tags=["administration"],
    )
    def retrain_model(user: User = Depends(admin_user)) -> ModelEvaluation:
        try:
            return app.state.forecaster.load_or_train(force=True)
        except (FileNotFoundError, ValueError) as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(error),
            ) from error

    @app.get("/api/v1/atms", response_model=AtmPage, tags=["ATMs"])
    def list_atms(
        search: Annotated[str | None, Query(max_length=80)] = None,
        risk: Annotated[str | None, Query(pattern="^(critical|watch|healthy)$")] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
        db: Session = Depends(get_session),
        user: User = Depends(current_user),
    ) -> AtmPage:
        forecaster: ForecastEngine = app.state.forecaster
        forecaster.refresh_data()
        items = forecaster.latest_atm_records()
        metadata = {
            row.atm_id: row for row in db.scalars(select(ATM)).all()
        }
        for item in items:
            row = metadata.get(item["atm_id"])
            item["location_name"] = row.location_name if row is not None else None
        if search:
            query = search.casefold()
            items = [
                item
                for item in items
                if query in item["atm_id"].casefold()
                or query in item["location_type"].casefold()
                or query in str(item.get("location_name") or "").casefold()
            ]
        if risk:
            items = [item for item in items if item["risk_level"] == risk]
        items.sort(
            key=lambda item: (
                {"critical": 0, "watch": 1, "healthy": 2}[item["risk_level"]],
                -item["demand"],
            )
        )
        return AtmPage(
            total=len(items),
            limit=limit,
            offset=offset,
            items=[AtmResponse(**item) for item in items[offset : offset + limit]],
        )

    @app.get(
        "/api/v1/data/atms",
        response_model=ATMMetadataPage,
        tags=["database"],
    )
    def list_database_atms(
        search: Annotated[str | None, Query(max_length=80)] = None,
        observed_only: bool = False,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        offset: Annotated[int, Query(ge=0)] = 0,
        db: Session = Depends(get_session),
        user: User = Depends(current_user),
    ) -> ATMMetadataPage:
        query = select(ATM)
        count_query = select(func.count()).select_from(ATM)
        if observed_only:
            query = query.where(ATM.observations.any())
            count_query = count_query.where(ATM.observations.any())
        if search:
            pattern = f"%{search.strip()}%"
            query = query.where(
                (ATM.atm_id.ilike(pattern))
                | (ATM.location_name.ilike(pattern))
                | (ATM.location_type.ilike(pattern))
            )
            count_query = count_query.where(
                (ATM.atm_id.ilike(pattern))
                | (ATM.location_name.ilike(pattern))
                | (ATM.location_type.ilike(pattern))
            )
        total = db.scalar(count_query) or 0
        rows = db.scalars(
            query.order_by(ATM.atm_id).offset(offset).limit(limit)
        ).all()
        return ATMMetadataPage(
            total=total,
            limit=limit,
            offset=offset,
            items=[
                ATMMetadataResponse(
                    atm_id=row.atm_id,
                    location_name=row.location_name,
                    location_type=row.location_type,
                    capacity=float(row.capacity),
                    data_source=row.data_source,
                )
                for row in rows
            ],
        )

    @app.get(
        "/api/v1/data/summary",
        response_model=DatabaseSummary,
        tags=["database"],
    )
    def database_summary(
        db: Session = Depends(get_session),
        user: User = Depends(current_user),
    ) -> DatabaseSummary:
        observation_totals = db.execute(
            select(
                func.count(ATMObservation.id),
                func.min(ATMObservation.observed_on),
                func.max(ATMObservation.observed_on),
            )
        ).one()
        synthetic_observations = db.scalar(
            select(func.count(ATMObservation.id))
            .join(ATM, ATMObservation.atm_id == ATM.atm_id)
            .where(
                ATM.data_source == "synthetic_simulation",
                ATMObservation.data_source == "synthetic_simulation",
            )
        ) or 0
        return DatabaseSummary(
            atm_count=db.scalar(select(func.count()).select_from(ATM)) or 0,
            observation_count=int(observation_totals[0] or 0),
            synthetic_observation_count=synthetic_observations,
            forecast_count=db.scalar(select(func.count()).select_from(ForecastRecord)) or 0,
            earliest_observation=observation_totals[1],
            latest_observation=observation_totals[2],
        )

    @app.get(
        "/api/v1/data/atms/{atm_id}/observations",
        response_model=ATMObservationPage,
        tags=["database"],
    )
    def list_database_observations(
        atm_id: str,
        start_date: Annotated[date | None, Query()] = None,
        end_date: Annotated[date | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        offset: Annotated[int, Query(ge=0)] = 0,
        db: Session = Depends(get_session),
        user: User = Depends(current_user),
    ) -> ATMObservationPage:
        if start_date and end_date and start_date > end_date:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="start_date must be on or before end_date.",
            )
        atm = db.get(ATM, atm_id)
        if atm is None:
            raise HTTPException(status_code=404, detail=f"ATM '{atm_id}' was not found.")
        filters = [ATMObservation.atm_id == atm_id]
        if start_date:
            filters.append(ATMObservation.observed_on >= start_date)
        if end_date:
            filters.append(ATMObservation.observed_on <= end_date)
        total = db.scalar(
            select(func.count())
            .select_from(ATMObservation)
            .where(*filters)
        ) or 0
        rows = db.scalars(
            select(ATMObservation)
            .where(*filters)
            .order_by(ATMObservation.observed_on.desc())
            .offset(offset)
            .limit(limit)
        ).all()
        return ATMObservationPage(
            total=total,
            limit=limit,
            offset=offset,
            items=[
                ATMObservationResponse(
                    atm_id=row.atm_id,
                    observed_on=row.observed_on,
                    total_withdrawals=float(row.total_withdrawals),
                    total_deposits=float(row.total_deposits),
                    withdrawal_transactions=row.withdrawal_transactions,
                    deposit_transactions=row.deposit_transactions,
                    opening_cash_balance=float(row.opening_cash_balance),
                    closing_cash_balance=float(row.closing_cash_balance),
                    replenishment_amount=float(row.replenishment_amount),
                    next_day_demand=float(row.next_day_demand),
                    holiday_flag=row.holiday_flag,
                    special_event_flag=row.special_event_flag,
                    weather_condition=row.weather_condition,
                    nearby_competitor_atms=row.nearby_competitor_atms,
                    time_of_day=row.time_of_day,
                    data_source=row.data_source,
                )
                for row in rows
            ],
        )

    @app.post(
        "/api/v1/forecasts",
        response_model=ForecastResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["forecasts"],
    )
    def create_forecast(
        request: ForecastRequest,
        db: Session = Depends(get_session),
        user: User = Depends(current_user),
    ) -> ForecastResponse:
        forecaster: ForecastEngine = app.state.forecaster
        try:
            forecaster.refresh_data()
            if not forecaster.model_data_current:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Operational data changed since model evaluation; retrain before forecasting.",
                )
            prediction = forecaster.forecast_next_day(
                request.atm_id,
                allow_historical_demo=config.forecast_mode == "historical_demo",
            )
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"ATM '{request.atm_id}' was not found in the dataset.",
            ) from error
        except StaleForecastDataError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(error),
            ) from error
        record = ForecastRecord(
            atm_id=prediction["atm_id"],
            forecast_date=prediction["forecast_date"],
            source_data_as_of=prediction["source_data_as_of"],
            predicted_demand=prediction["predicted_demand"],
            lower_bound=prediction["lower_bound"],
            upper_bound=prediction["upper_bound"],
            current_balance=prediction["current_balance"],
            capacity=prediction["capacity"],
            recommended_replenishment=prediction["recommended_replenishment"],
            risk_level=prediction["risk_level"],
            capacity_constrained=prediction["capacity_constrained"],
            forecast_mode=prediction["forecast_mode"],
            data_source=prediction["data_source"],
            model_name=prediction["model_name"],
            created_by_id=user.id,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return ForecastResponse(
            id=record.id,
            atm_id=record.atm_id,
            forecast_date=record.forecast_date,
            source_data_as_of=record.source_data_as_of,
            predicted_demand=record.predicted_demand,
            lower_bound=record.lower_bound,
            upper_bound=record.upper_bound,
            current_balance=record.current_balance,
            capacity=prediction["capacity"],
            recommended_replenishment=record.recommended_replenishment,
            risk_level=record.risk_level,
            capacity_constrained=record.capacity_constrained,
            forecast_mode=record.forecast_mode,
            data_source=record.data_source,
            model_name=record.model_name,
            created_at=record.created_at,
        )

    @app.post(
        "/api/v1/forecasts/scenario",
        response_model=ScenarioResponse,
        tags=["forecasts"],
    )
    def scenario_forecast(
        request: ScenarioRequest,
        db: Session = Depends(get_session),
        user: User = Depends(current_user),
    ) -> ScenarioResponse:
        forecaster: ForecastEngine = app.state.forecaster
        forecaster.refresh_data()
        try:
            estimates = forecaster.scenario_forecasts(
                festival=request.festival,
                holiday=request.holiday,
                adjustment_pct=request.adjustment_pct,
                atm_ids=request.atm_ids,
            )
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"ATM '{error.args[0]}' was not found in the operating dataset.",
            ) from error
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(error),
            ) from error
        except RuntimeError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="The forecast model is not ready.",
            ) from error

        metadata = {
            row.atm_id: row for row in db.scalars(select(ATM)).all()
        }
        items = [
            ScenarioForecast(
                **estimate,
                location_name=(
                    metadata[estimate["atm_id"]].location_name
                    if estimate["atm_id"] in metadata
                    else None
                ),
            )
            for estimate in estimates
        ]
        return ScenarioResponse(
            festival=request.festival,
            holiday=request.holiday,
            adjustment_pct=request.adjustment_pct,
            data_source=(
                items[0].data_source if items else config.operational_data_source
            ),
            forecast_mode=config.forecast_mode,
            note=(
                "Simulation only. The model uses the latest observation for each ATM. "
                "Festival and holiday switches replace the corresponding model inputs; "
                "the percentage adjustment is applied after inference. These are not "
                "operational forecasts or observed bank outcomes."
            ),
            generated_at=datetime.now(timezone.utc),
            items=items,
        )

    @app.get("/api/v1/forecasts", response_model=ForecastHistory, tags=["forecasts"])
    def forecast_history(
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        db: Session = Depends(get_session),
        user: User = Depends(current_user),
    ) -> ForecastHistory:
        query = select(ForecastRecord).order_by(ForecastRecord.created_at.desc())
        total = db.scalar(select(func.count()).select_from(ForecastRecord)) or 0
        records = db.scalars(query.limit(limit)).all()
        items = [
            ForecastResponse(
                id=record.id,
                atm_id=record.atm_id,
                forecast_date=record.forecast_date,
                source_data_as_of=record.source_data_as_of,
                predicted_demand=record.predicted_demand,
                lower_bound=record.lower_bound,
                upper_bound=record.upper_bound,
                current_balance=record.current_balance,
                capacity=record.capacity,
                recommended_replenishment=record.recommended_replenishment,
                risk_level=record.risk_level,
                capacity_constrained=record.capacity_constrained,
                forecast_mode=record.forecast_mode,
                data_source=record.data_source,
                model_name=record.model_name,
                created_at=record.created_at,
            )
            for record in records
        ]
        return ForecastHistory(total=total, items=items)

    return app


app = create_app()
