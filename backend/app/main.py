from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from collections.abc import Generator
from typing import Annotated

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import Settings
from app.database import Base, build_engine, build_session_factory, yield_session
from app.forecasting import TARGET_COLUMN, ForecastEngine
from app.models import ForecastRecord, User
from app.schemas import (
    AtmPage,
    AtmResponse,
    DashboardSummary,
    DemandPoint,
    ForecastHistory,
    ForecastRequest,
    ForecastResponse,
    LocationDemand,
    ModelEvaluation,
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

    current_user = build_current_user_dependency(config, get_session)
    admin_user = build_admin_dependency(current_user)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        config.validate_secrets()
        if not config.dataset_path.is_file():
            raise FileNotFoundError(f"ATM dataset was not found: {config.dataset_path}")
        Base.metadata.create_all(bind=engine)
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
            dataset_path=config.dataset_path,
            artifact_path=config.model_artifact_path,
            target_accuracy_pct=config.target_accuracy_pct,
            test_size=config.model_test_size,
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
    app.state.session_factory = session_factory
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
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
        data = forecaster.data
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
        data = app.state.forecaster.data
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
        data = app.state.forecaster.data
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

    @app.get("/api/v1/model/evaluation", response_model=ModelEvaluation, tags=["model"])
    def model_evaluation(user: User = Depends(current_user)) -> ModelEvaluation:
        return app.state.forecaster.evaluation_report()

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
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(error),
            ) from error

    @app.get("/api/v1/atms", response_model=AtmPage, tags=["ATMs"])
    def list_atms(
        search: Annotated[str | None, Query(max_length=80)] = None,
        risk: Annotated[str | None, Query(pattern="^(critical|watch|healthy)$")] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
        user: User = Depends(current_user),
    ) -> AtmPage:
        items = app.state.forecaster.latest_atm_records()
        if search:
            query = search.casefold()
            items = [
                item
                for item in items
                if query in item["atm_id"].casefold()
                or query in item["location_type"].casefold()
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
            prediction = forecaster.forecast_next_day(request.atm_id)
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"ATM '{request.atm_id}' was not found in the dataset.",
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
            model_name=record.model_name,
            created_at=record.created_at,
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
                model_name=record.model_name,
                created_at=record.created_at,
            )
            for record in records
        ]
        return ForecastHistory(total=total, items=items)

    return app


app = create_app()
