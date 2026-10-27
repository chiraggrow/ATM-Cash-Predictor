# ATM Cash Intelligence

ATM cash-demand forecasting and replenishment planning for Bank Muscat. The application includes a React operations dashboard, a FastAPI service, chronological machine-learning evaluation, PostgreSQL persistence, OAuth2/JWT authentication, and Docker deployment examples.

> **This repository is a historical-data prototype, not a live cash-control system.** The supplied CSV covers 2022-01-01 through 2024-01-01. It contains no transaction feed, currency denomination, confirmed cash-out incident, delivery lead-time, or replenishment execution data. All cash amounts are therefore shown in **dataset units**, not OMR. Do not use prototype forecasts or simulated savings to make live replenishment decisions.

## What is included

- **Forecasting:** A scikit-learn histogram gradient-boosting regressor with categorical preprocessing and date-cycle features, compared with a training-median baseline.
- **Evaluation:** Date-ordered training, validation, and untouched test windows. Model selection and uncertainty calibration use the earlier validation window; the final holdout is reserved for reporting. Same-day ATM observations stay on the same side of each split.
- **Inventory planning:** A one-step-ahead point estimate, empirical validation-residual P90 interval, and capacity-limited replenishment recommendation.
- **Impact measurement:** A backtest scenario compares the test-window proxy `ATM_Balance < Cash_Demand_Next_Day` with replenishment to the model's upper estimate, limited by recorded ATM capacity. The 70% result is an **idealized simulated proxy**, not measured incident reduction: the CSV has no confirmed cash-out or delivery-execution outcomes.
- **Analytics:** Historical monthly demand, location comparisons, network risk flags, model metrics, data freshness, and duplicate ATM/date-group counts.
- **Analyst report:** A pandas/Matplotlib command generates monthly-demand, location-label, and distribution charts plus a JSON data-quality profile.
- **API:** FastAPI/OpenAPI, OAuth2 password login with JWT bearer tokens, admin-only model retraining, and a persisted forecast audit trail.
- **Persistence/deployment:** SQLAlchemy, PostgreSQL, Alembic migrations, Docker Compose, separate web/API images, and an example Amazon ECS Fargate task definition.
- **Tests:** API authentication, chronological model evaluation, data-quality handling, forecast bounds, and audit persistence.

The CSV has 5,658 observations for 50 ATM IDs. There are 413 duplicate ATM/date groups, with different observations within some groups, and all 50 IDs use more than one `Location_Type` label. The pipeline retains rows as recorded observations, reports those quality issues, and treats location as an observation category; it does not fabricate a daily ATM history or create target-derived lag features from ambiguous same-day data.

## Run locally

Prerequisites: Python 3.11, Node.js 22+, npm, Docker, and Docker Compose.

1. Copy `.env.example` to `.env`.
2. Replace every `REPLACE_WITH` value in `.env`. Use the same value for `POSTGRES_PASSWORD` and the password in `DATABASE_URL`. Set `JWT_SECRET_KEY` and `ADMIN_PASSWORD` to private values; the key must be at least 32 characters and the password at least 12 characters. Generate a key with:

   ```bash
   python3.11 -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

3. Start the complete application:

   ```bash
   docker compose up --build
   ```

4. Open <http://localhost:8080>. Sign in using the `ADMIN_USERNAME` and `ADMIN_PASSWORD` values from your private `.env`.
5. API documentation is at <http://localhost:8080/api/v1/docs>; readiness is at <http://localhost:8080/health/ready>.

The first API start applies Alembic migrations, creates the initial administrator from environment settings, and trains/evaluates the model if no matching artifact exists. PostgreSQL and trained model artifacts are held in named Docker volumes.

### Run the frontend without Docker

Create a Python environment, install the backend requirements, and configure `DATABASE_URL` in the root `.env` to point to a PostgreSQL server reachable from the host, using the credentials configured for that server. Then start the API from the repository root:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
cd backend
export DATASET_PATH=../atm_cash.csv
export MODEL_ARTIFACT_PATH=../artifacts/atm-demand.joblib
alembic upgrade head
uvicorn app.main:app --reload
```

In another terminal, start the frontend:

```bash
npm ci
npm run dev
```

Vite proxies `/api` and `/health` to `http://127.0.0.1:8000`. For a host-run API pointed at the Compose database, set `DATABASE_URL` to the Compose database URL using the username and password from `.env`, with host `localhost`. A Docker Compose database is reachable on `localhost:5432` from the host.

### Run Python tests

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements-dev.txt
cd backend
python -m pytest tests -q
```

### Generate a data-quality and EDA report

From the repository root, after installing the Python requirements:

```bash
cd backend
python -m app.eda --input ../atm_cash.csv --output ../reports
```

The report writes three PNG charts and `data_quality_summary.json`. Location comparisons describe observation labels, not verified fixed ATM locations; the balance-versus-demand rate is only a stockout proxy.

Tests use a temporary SQLite database and a small generated dataset. The application defaults to PostgreSQL for normal use.

## Main API routes

All `/api/v1` routes except `/auth/token` require a bearer access token.

| Route | Purpose |
|---|---|
| `POST /api/v1/auth/token` | OAuth2 password login; returns a short-lived JWT |
| `GET /api/v1/auth/me` | Current signed-in user and role |
| `GET /api/v1/analytics/summary` | Network, data-quality, model, and impact summary |
| `GET /api/v1/analytics/demand-trend?months=12` | Monthly observed-demand series |
| `GET /api/v1/analytics/location-demand?months=12` | Location-type demand comparison |
| `GET /api/v1/model/evaluation` | Chronological test metrics and target flags |
| `POST /api/v1/admin/model/retrain` | Re-evaluate and retrain from the configured CSV (admin only) |
| `GET /api/v1/atms?search=&risk=` | Search, filter, and page latest ATM observations |
| `POST /api/v1/forecasts` | Forecast next day for `{"atm_id":"ATM_0001"}` and record the result |
| `GET /api/v1/forecasts?limit=20` | Recent forecast and replenishment audit history |

Cash-demand accuracy is reported as `max(0, 100 × (1 − WAPE))`, with WAPE, MAE, RMSE, sMAPE, and a median baseline alongside it. The API explicitly reports whether the 85% threshold was met; the threshold is not guaranteed. The 70% reduction KPI is likewise reported as a scenario estimate and must be replaced with operationally measured incident/delivery data before it can be considered achieved.

## Data and deployment controls

- Keep `.env`, production secrets, database backups, and generated model artifacts out of Git.
- Replace every example password and secret. In AWS, store `DATABASE_URL`, `JWT_SECRET_KEY`, and `ADMIN_PASSWORD` in AWS Secrets Manager and reference them through ECS task secrets.
- The sample ECS task runs the web and API containers in one Fargate task and uses the task-local API connection. Place it behind a TLS-enabled Application Load Balancer; use private subnets, security groups, an RDS PostgreSQL database, and least-privilege task roles.
- The sample task definition contains placeholder AWS account, role, image, and secret ARNs. Replace them before deployment. From Apple Silicon, build images for the sample `X86_64` task platform with `docker buildx build --platform linux/amd64 ...`.
- Establish bank-approved IAM/SSO, secret rotation, audit retention, monitoring, data-quality checks, and human approval controls before production use.
- No production certification, financial-service compliance, forecast target, or cash-out reduction is implied by this prototype.
