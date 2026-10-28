# ATM Cash Demand Predictor

ATM cash-demand forecasting prototype with a React dashboard, FastAPI service, scikit-learn pipeline, PostgreSQL persistence, OAuth2/JWT authentication, and Docker/AWS ECS deployment examples.

> **Prototype only — not a live cash-control system.** The API, analytics, ATM watch, model training, and forecasts use observations read from PostgreSQL, selected by `OPERATIONAL_DATA_SOURCE` (default: `synthetic_simulation`). The bundled synthetic records are not Bank Muscat operational data. The original root CSV is retained only for offline model/EDA workflows and historical comparison. No source provides live transaction data, currency denominations, confirmed cash-out events, delivery lead times, or replenishment execution outcomes. Amounts are in **dataset units**, not OMR.

## Architecture

- `src/`: React/Vite dashboard for historical analytics, test metrics, ATM observations, and guarded one-day forecasts.
- `backend/app/repository.py`: loads the configured operational source from PostgreSQL for forecast training and inference.
- `backend/app/forecasting.py`: dataset validation, chronological model selection/evaluation, preprocessing pipeline, model artifact, prediction output, and Matplotlib reports. Its CLI remains an explicit CSV-based offline workflow.
- `backend/app/main.py`: FastAPI endpoints for analytics, model status/evaluation, forecasts, OAuth2/JWT, and admin retraining.
- `backend/app/models.py`, `database.py`, and `migrations/`: SQLAlchemy user, ATM, observation, and forecast-audit persistence with Alembic migrations.
- `backend/app/eda.py`: standalone data-quality and descriptive-analysis charts.
- `docker-compose.yml`, `Dockerfile`, `backend/Dockerfile`, and `deploy/`: local services and deployment examples.

Training compares a scikit-learn `HistGradientBoostingRegressor` pipeline against a training-fold median `DummyRegressor`. The earlier validation window selects the model and calibrates the empirical 90th-percentile absolute-error interval; an untouched later date window supplies the reported test metrics. All observations on a date stay together in each split. Numeric imputation and category encoding are fitted inside the sklearn pipeline and saved with the model. Since the target is next-day demand, calendar features during training use `Date + 1 day`, matching the forecast-date features used at API inference.

### Dataset schema and usage

The target is `Cash_Demand_Next_Day`; the date is `Date`; and `ATM_ID` identifies the machine.

| Column(s) | Meaning / use |
|---|---|
| `ATM_ID`, `Date` | ATM and observation date; rows are chronologically sorted and same-date rows remain grouped for splitting. |
| `Cash_Demand_Next_Day` | Supervised target: next-day demand in unspecified dataset units. |
| `Total_Withdrawals`, `Total_Deposits`, `Previous_Day_Cash_Level`, `ATM_Capacity`, `ATM_Balance` | Numeric observation inputs used by the model. Confirm they are available at prediction time in any replacement dataset. |
| `Holiday_Flag`, `Special_Event_Flag`, `Nearby_Competitor_ATMs` | Numeric observation inputs. |
| `Time_of_Day`, `Location_Type`, `Weather_Condition` | Categorical observation inputs; unseen categories are safely ignored during inference. |
| `Day_of_Week` | Supplied descriptor; weekday features are derived consistently from `Date` instead. |
| `Replenishment_Amount`, `Replenishment_Required` | Kept for analysis, but excluded from model features to avoid operational outcome/target leakage. |

The loader rejects missing dates/ATM IDs/targets, non-numeric targets, negative demand, and invalid balance/capacity. Missing or invalid optional numeric predictors are reported and median-imputed within each training fold. It does not silently drop records; duplicate observations are retained and counted.

The dataset contains 5,658 rows for 50 ATM IDs, dates 2022-01-01 to 2024-01-01, and 731 distinct dates. It has 413 duplicate ATM/date groups (not exact duplicate rows), no blank CSV fields, and changing `Location_Type` labels for all 50 ATM IDs. Each ATM has 81–136 observed dates; the median per-ATM gap is 5 days and the maximum is 52 days. Since this is not a continuous daily ATM history and same-day duplicate rows can disagree, the pipeline intentionally does **not** invent daily histories or target-derived lag/rolling-demand features. The exact data profile is written to the evaluation `metrics.json`.

The repository does not document the CSV's source or provenance, so it cannot be verified whether the supplied observations are real, anonymized, or synthetic. Do not treat it as bank operational data.

### Synthetic ATM dataset and PostgreSQL

`data/generated/atm_cash_10k.csv` is generated deterministically with seed `20261027`. It contains **17,544 synthetic ATM/date observations** (24 fictional ATMs × 731 daily dates, inclusive, 2023-01-01 through 2024-12-31). The original `atm_cash.csv` remains unchanged. Every row is marked `Data_Source=synthetic_simulation`; generated values are not Bank Muscat records and are not an operational forecast validation dataset.

The generator defines one future target: `Cash_Demand_Next_Day` is simulated for the day after the row's `Date`. The target is not used as a feature for that same observation. Daily demand simulation includes weekday multipliers, a smooth annual seasonal term, occasional event multipliers and spikes, ATM-specific base levels, and random variation. Withdrawals, deposits, stock balances and replenishment are bounded by simulated ATM capacity. The generator is a reproducible scenario fixture, not a statistical model fitted to bank data.

| Generated column(s) | Meaning / unit |
|---|---|
| `ATM_ID`, `Date` | Fictional ATM key and end-of-day observation date; unique per ATM/date. |
| `Day_of_Week`, `Time_of_Day` | Descriptive calendar values; observations are end-of-day (`EndOfDay`). |
| `Total_Withdrawals`, `Total_Deposits`, `Cash_Demand_Next_Day` | Simulated cash amounts in generic cash units (not labeled OMR); the last field is the next-day target. |
| `Withdrawal_Transactions`, `Deposit_Transactions` | Simulated daily transaction counts. |
| `Opening_Cash_Balance`, `Closing_Cash_Balance`, `Previous_Day_Cash_Level`, `ATM_Balance` | Cash stock in generic cash units. Opening and closing are the balance at this observation; the existing-schema aliases are retained for model compatibility. |
| `Replenishment_Amount`, `Replenishment_Required` | Simulated replenishment in generic cash units and its yes/no indicator. |
| `ATM_Capacity` | Simulated maximum balance in generic cash units. |
| `Location_Name`, `Location_Type`, `Nearby_Competitor_ATMs` | Fictional location profile and simulated nearby-ATM count. |
| `Holiday_Flag`, `Special_Event_Flag`, `Weather_Condition` | Simulated calendar/event/weather descriptors. |
| `Data_Source` | Always `synthetic_simulation`; provenance label. |

Regenerate without touching the supplied CSV:

```bash
cd backend
python -m app.generate_synthetic_dataset
```

For a reproducible synthetic extension that keeps existing ATM capacities unchanged, export the capacities for the 24 synthetic ATM IDs from PostgreSQL:

```bash
cd backend
python - <<'PY'
import json
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.config import Settings
from app.database import build_engine
from app.models import ATM

engine = build_engine(Settings().database_url)
try:
    with Session(engine) as session:
        rows = session.scalars(
            select(ATM).where(
                ATM.atm_id.like("SYN_ATM_%"),
                ATM.data_source == "synthetic_simulation",
            )
        ).all()
        capacities = {row.atm_id: int(row.capacity) for row in rows}
finally:
    engine.dispose()
if set(capacities) != {f"SYN_ATM_{index:04d}" for index in range(1, 25)}:
    raise SystemExit("Expected all 24 existing synthetic ATM profiles.")
Path("/tmp/synthetic-atm-capacities.json").write_text(
    json.dumps(capacities, indent=2) + "\n",
    encoding="utf-8",
)
PY
```

Then generate only the non-overlapping date range, using a distinct output file and the same fixed seed:

```bash
python -m app.generate_synthetic_dataset \
  --start-date 2025-01-01 \
  --end-date 2026-10-28 \
  --seed 20261027 \
  --atm-capacities-json /tmp/synthetic-atm-capacities.json \
  --output ../data/generated/atm_cash_synthetic_extension_2025-01-01_to-2026-10-28.csv
```

The JSON must map every `SYN_ATM_0001` through `SYN_ATM_0024` to its positive integer capacity in the database. Validate the output and check that its date range does not overlap stored rows before seeding. Each generated row remains explicitly labelled `synthetic_simulation`; the extension is demonstration data, not banking telemetry.

PostgreSQL tables are `atms`, `atm_observations`, and `forecast_records` (plus existing `users`). Observation rows enforce unique `(atm_id, observed_on)`, nonnegative numeric/count values, and an ATM foreign key. `forecast_records.atm_id` also references `atms`; pre-existing forecast ATM identifiers are backfilled during the additive migration with explicitly unknown legacy metadata. The observation table includes a date index, and ATM location type is indexed.

Set local values in an ignored `.env` based on `.env.example`; never commit the local file. Apply migrations and seed in repeatable steps:

```bash
cp .env.example .env
# Replace all REPLACE_WITH placeholders locally; configure POSTGRES_USER, POSTGRES_PASSWORD,
# POSTGRES_DB and a host-reachable DATABASE_URL for a locally installed PostgreSQL server.
cd backend
alembic upgrade head
python -m app.seed_database
```

Seeding validates the synthetic CSV, upserts ATM metadata, and inserts observation batches idempotently by ATM/date. It fills newly added feature/provenance fields only when existing observations lack them. `DATABASE_URL` is used by the API, migration environment, and seed CLI. The API does not create or alter production schema at startup; use Alembic. Authenticated database endpoints include `GET /api/v1/data/summary`, `GET /api/v1/data/atms`, and `GET /api/v1/data/atms/{atm_id}/observations?start_date=&end_date=`.

`OPERATIONAL_DATA_SOURCE` selects the exact `data_source` value required on both ATM metadata and observation records. The API does not fall back to a CSV if PostgreSQL is unavailable or the selected source has no observations. The original `atm_cash.csv` is not imported: it has 413 duplicate ATM/date groups, while the operational observation table enforces one row per ATM/date. Keep it for explicit offline training/EDA only. The generated CSV remains the repeatable seed/recovery input and optional offline training input; API operation reads PostgreSQL.

Migration `0004_database_forecasting_source` adds source provenance and the two forecast input columns omitted by the earlier schema. Apply it before seeding or starting the updated API. It is additive and backfills existing observation/forecast provenance from ATM metadata; no historical CSV records are imported.

Verify database totals directly after seeding:

```sql
SELECT COUNT(*) AS observations,
       COUNT(DISTINCT atm_id) AS atms,
       MIN(observed_on) AS first_date,
       MAX(observed_on) AS last_date
FROM atm_observations;

SELECT COUNT(*) AS duplicate_atm_date_groups
FROM (
  SELECT atm_id, observed_on
  FROM atm_observations
  GROUP BY atm_id, observed_on
  HAVING COUNT(*) > 1
) AS duplicates;

SELECT COUNT(*) AS forecast_records FROM forecast_records;
```

For generated data, the expected source-file totals are 17,544 observations and 24 ATMs, with zero duplicate ATM/date groups. Query PostgreSQL itself to establish stored totals; a CSV or in-memory count is not evidence that seeding succeeded.

The configured PostgreSQL source was evaluated with the chronological ML pipeline: 14,016 training rows through 2024-08-07 and 3,528 holdout rows with target dates 2024-08-08 through 2025-01-01. The selected model measured MAE **4,227.51**, RMSE **6,345.36**, and WAPE **8.57%**; the training-median baseline measured MAE **13,701.38**, RMSE **17,014.88**, and WAPE **27.77%**. These results were queried from the running API and describe generated, rule-based data only; they are not evidence of accuracy on real bank data. This generated source is historical and is blocked for current production forecasts by the freshness guard.

### Offline evaluation on the original CSV

The standalone CSV training workflow on the original file produced the following **chronological holdout** results (1,186 test observations; forecast target dates 2023-08-09 to 2024-01-02; input observations through 2024-01-01). These are not the current API model results, which are trained/evaluated from the configured PostgreSQL source. All amounts are dataset units.

| Measure | Selected model | Training-median baseline |
|---|---:|---:|
| MAE | 5,188.93 | 13,290.04 |
| RMSE | 6,306.91 | 16,519.55 |
| WAPE | 12.13% | 31.08% |
| WAPE-derived score (`max(0, 100 × (1 − WAPE))`) | 87.87% | — |

The selected model was `hist-gradient-boosting-v3`. The configured 85% score threshold was met on this one historical holdout; it is a project target, not a guarantee or a measured operational service level. WAPE is omitted (`null`) when actual demand totals zero. Cash-out reduction is not calculated or claimed because there are no confirmed incident or executed-delivery labels.

When trained, the model and evaluation outputs are saved under `artifacts/` (ignored by Git). The default report directory is `artifacts/evaluation/`, containing:

- `metrics.json`: evaluation, data-quality profile, and training/feature configuration.
- `test_predictions.csv`: per-row actuals, selected-model and baseline predictions, and residuals.
- `actual_vs_predicted.png`, `forecast_demand_trend.png`, and `residual_analysis.png`.

## Installation and commands

Requirements: Python 3.11, Node.js 22+, npm, PostgreSQL (or Docker Compose for a local PostgreSQL container), and optionally Docker for the full container stack. Dependencies are declared in `backend/requirements.txt` and `backend/requirements-dev.txt`.

Create the Python environment and install development dependencies:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements-dev.txt
```

Train/evaluate from the backend directory (paths can also be set with `DATASET_PATH`, `MODEL_ARTIFACT_PATH`, and `MODEL_TEST_SIZE`):

```bash
cd backend
python -m app.forecasting
```

Optional CLI overrides:

```bash
python -m app.forecasting \
  --dataset ../atm_cash.csv \
  --artifact ../artifacts/atm-demand.joblib \
  --output-dir ../artifacts/evaluation \
  --test-size 0.2
```

The standalone training CLI above is an explicit CSV-based offline workflow; `DATASET_PATH` applies to that workflow, not API data access. The API loads/trains against the selected PostgreSQL source at startup, does not retrain for each request, and the admin retrain endpoint forces a fresh evaluation against PostgreSQL. A mismatched database-data hash, scikit-learn version, artifact version, feature configuration, or training configuration triggers retraining on startup. If selected-source rows change after training, forecasts are blocked until an administrator retrains.

To explicitly evaluate the generated synthetic scenario instead of the original sample:

```bash
python -m app.forecasting \
  --dataset ../data/generated/atm_cash_10k.csv \
  --artifact ../artifacts/synthetic-atm-demand.joblib \
  --output-dir ../artifacts/synthetic-evaluation
```

This evaluates simulated data only; it cannot establish real ATM forecast accuracy or cash-out reduction.

### Run the API and dashboard

Configure `.env` from `.env.example` and replace all `REPLACE_WITH` values. Use a private `JWT_SECRET_KEY` of at least 32 characters and `ADMIN_PASSWORD` of at least 12 characters. `MAX_FORECAST_DATA_AGE_DAYS` defaults to 1 and `FORECAST_MODE` defaults to `production`. The API requires a reachable PostgreSQL database containing the configured source. Then:

```bash
cd backend
alembic upgrade head
python -m app.seed_database
uvicorn app.main:app --reload
```

Start the API only after the configured PostgreSQL database has its schema and selected-source observations. For a fresh local database, run the Alembic migration and idempotent seed commands shown above first. Then, in another terminal:

```bash
npm ci
npm run dev
```

Vite proxies `/api` and `/health` to `http://127.0.0.1:8000`. The authenticated API docs are available at <http://localhost:8000/api/v1/docs>.

Production mode blocks a forecast unless the selected ATM's newest PostgreSQL observation satisfies the configured freshness limit, the next-day forecast date is in the future, and the loaded model was evaluated against the current database source. It also rejects `synthetic_simulation` observations even when their generated dates are recent; only the explicitly labelled historical demo mode may forecast from synthetic records. PostgreSQL errors or an empty selected source fail explicitly; the API never falls back to CSV.

For local demonstrations only, run the API with process-scoped settings such as `ENVIRONMENT=development FORECAST_MODE=historical_demo uvicorn app.main:app --reload` from `backend`; this avoids changing the local `.env` and is rejected if `ENVIRONMENT=production`. Historical demo mode explicitly permits forecasts from stale sample observations. API responses and saved audit records include `forecast_mode: "historical_demo"`; the dashboard labels each output **HISTORICAL DEMO · NOT CURRENT**. These outputs are synthetic historical examples, not current forecasts, and must not be used as replenishment instructions. Production mode and its freshness guard remain enabled by default. The AWS ECS example pins `FORECAST_MODE=production`.

To run the complete PostgreSQL/web/API stack instead, copy and configure `.env.example` as `.env`, then run:

```bash
docker compose up --build
```

Open <http://localhost:8080>. Docker Compose waits for PostgreSQL, applies migrations, seeds the synthetic observations, and only then starts the API; it provisions the initial admin user at API startup and keeps PostgreSQL/model files in named volumes. The UI identifies the selected PostgreSQL source and labels synthetic records as synthetic, not current live ATM data.

### Tests and data-quality report

```bash
cd backend
python -m pytest tests -q
python -m app.eda --input ../atm_cash.csv --output ../reports
```

The test suite uses isolated SQLite databases and synthetic fixtures. The EDA command writes three charts and a JSON summary. Evaluation plots and per-row holdout predictions are generated by the training command. For PostgreSQL integration, first apply migrations and seed the generated CSV, then use the SQL verification queries above; never point destructive test setup at a production database.

## Main API routes

All `/api/v1` routes except `/auth/token` require a bearer access token.

| Route | Purpose |
|---|---|
| `POST /api/v1/auth/token` | OAuth2 password login; returns a short-lived JWT |
| `GET /api/v1/auth/me` | Current signed-in user and role |
| `GET /api/v1/analytics/summary` | Network, data-quality, and model summary |
| `GET /api/v1/analytics/demand-trend?months=12` | Monthly observed-demand series |
| `GET /api/v1/analytics/location-demand?months=12` | Location-type demand comparison |
| `GET /api/v1/model/evaluation` | Chronological test metrics and target flags |
| `GET /api/v1/model/status` | Loaded model, PostgreSQL source, dataset date range, model/data freshness, and evaluation artifacts |
| `POST /api/v1/admin/model/retrain` | Re-evaluate and retrain from the configured PostgreSQL source (admin only) |
| `GET /api/v1/atms?search=&risk=` | Search, filter, and page latest ATM observations |
| `GET /api/v1/data/summary` | Database ATM, observation, synthetic-source, and forecast totals |
| `GET /api/v1/data/atms?search=&observed_only=true` | Page ATM metadata stored in PostgreSQL; filter out legacy forecast-only ATM metadata when needed |
| `GET /api/v1/data/atms/{atm_id}/observations?start_date=&end_date=` | Page persisted historical observations for one ATM |
| `POST /api/v1/forecasts` | Forecast one day ahead for `{"atm_id":"ATM_0001"}` and record the result; returns HTTP 409 when data is stale or the forecast date is not in the future |
| `GET /api/v1/forecasts?limit=20` | Recent forecast and replenishment audit history |

The configured freshness guard is `MAX_FORECAST_DATA_AGE_DAYS` (default: 1). A production next-day forecast must use an ATM observation within that age limit and its forecast date must be after the current UTC date. The supplied historical dataset is stale, so production forecast requests are intentionally blocked until current observations replace it. For local demos only, set `FORECAST_MODE=historical_demo`; outputs and persisted audit records are labelled `historical_demo` and the UI explicitly says they are not current. `ENVIRONMENT=production` rejects this mode at startup. Existing records from before the mode migration are marked `legacy_unknown`, not assumed to be live or demo. The regression API evaluates the data historically regardless of forecast mode.

The API reports MAE, RMSE, WAPE when its denominator is nonzero, sMAPE, and the same metrics for the training-median baseline. The UI calls `max(0, 100 × (1 − WAPE))` a **holdout score**, not a guaranteed accuracy. There is no cash-out reduction KPI because no confirmed incident or delivery outcome data exists.

## Data and deployment controls

- Keep `.env`, production secrets, database backups, and generated model artifacts out of Git.
- Replace every example password and secret. In AWS, store `DATABASE_URL`, `JWT_SECRET_KEY`, and `ADMIN_PASSWORD` in AWS Secrets Manager and reference them through ECS task secrets.
- The sample ECS task runs the web and API containers in one Fargate task and uses the task-local API connection. Place it behind a TLS-enabled Application Load Balancer; use private subnets, security groups, an RDS PostgreSQL database, and least-privilege task roles.
- The sample task definition contains placeholder AWS account, role, image, and secret ARNs. Replace them before deployment. From Apple Silicon, build images for the sample `X86_64` task platform with `docker buildx build --platform linux/amd64 ...`.
- Establish bank-approved IAM/SSO, secret rotation, audit retention, monitoring, data-quality checks, and human approval controls before production use.
- No production certification, financial-service compliance, forecast target, or cash-out reduction is implied by this prototype. Do not deploy or make operational replenishment decisions from the sample data.
