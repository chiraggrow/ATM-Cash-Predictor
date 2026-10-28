# Project Cleanup Audit

Audit date: 2026-10-27

## Repository state and scope

- The project repository is `ATM-CASH-DEMAND-PREDECTOR`.
- The worktree already contains staged and unstaged changes across application, test, configuration, and documentation files. Those pre-existing changes were preserved; no files were reset, checked out, or unstaged.
- `.env` exists and is ignored by Git. Its contents were not read or recorded.
- The expected old CSV path `data/atm_cash.csv` does not exist. The original source file is `atm_cash.csv` at the repository root.
- The generated dataset is `data/generated/atm_cash_10k.csv`.

## Dataset and database findings

- Original CSV: 5,658 rows, 17 columns, 50 ATM identifiers, dates 2022-01-01 through 2024-01-01; it has 413 duplicate ATM/date groups. It remains required for the established model/analytics and offline workflows.
- Generated CSV: 17,544 rows, 23 columns, 24 synthetic ATM identifiers, dates 2023-01-01 through 2024-12-31. It has no missing cells, invalid dates, prohibited negative numeric values, or duplicate ATM/date observations. All rows have `Data_Source=synthetic_simulation`; generation with the default seed is reproducible.
- The target is `Cash_Demand_Next_Day`. It is not in the model feature list. Calendar features use the next-day target date. Replenishment outcome fields are excluded from model features.
- PostgreSQL connection resolved to database `atm_cash_predictor`, role `atm_cash_app` (not a superuser), migration `0003_atm_observations`.
- PostgreSQL contains 17,544 observations across 24 distinct observed ATMs, dates 2023-01-01 through 2024-12-31, zero duplicate groups, nulls, invalid numeric values, or orphan observations. There are 25 ATM metadata records because a separate ATM was created for a historical-demo forecast. One saved forecast is labeled `historical_demo`.
- Authenticated `/api/v1/data/*` endpoints read ATM metadata and observations from PostgreSQL. The existing model, analytics, `/api/v1/atms`, and forecast input pipeline still load the original CSV. The dashboard presents those CSV-backed views separately from database-backed observation records; no silent CSV fallback is used for database endpoints. A full migration of model/forecast inputs to PostgreSQL is not part of this cleanup.
- A database smoke check found that lexically first ATM metadata may be a legacy forecast-only ATM with no observations. Added `observed_only=true` to the metadata listing and use it for the dashboard's database sample, so the UI selects a real observed ATM without hiding legacy metadata from the general list.
- Production freshness checks remain active; the generated dataset is historical and synthetic, not current banking data.

## File classification

### 1. Essential — preserve

- `backend/app/main.py`, `forecasting.py`, `models.py`, `schemas.py`, `security.py`, `database.py`, `config.py`.
- `src/App.jsx`, `src/data.js`, `src/main.jsx`, `src/styles.css`.
- `atm_cash.csv`: original historical-model and offline source data; do not overwrite or delete.
- `data/generated/atm_cash_10k.csv`: reproducible synthetic seed/training scenario; do not overwrite with the old CSV.

### 2. Required for development, testing, reproducibility, or deployment — preserve

- `backend/app/generate_synthetic_dataset.py`, `backend/app/seed_database.py`, `backend/app/eda.py`.
- `backend/migrations/`, `backend/tests/`, `backend/alembic.ini`.
- `backend/requirements.txt`, `backend/requirements-dev.txt`, `package.json`, `package-lock.json`.
- `.gitignore`, `.dockerignore`, `.env.example`, `README.md`, `PROJECT_CLEANUP_AUDIT.md`.
- `Dockerfile`, `backend/Dockerfile`, `docker-compose.yml`, `nginx/`, `deploy/`, `index.html`, `vite.config.js`.
- `artifacts/`: model, holdout predictions and evaluation outputs. They are ignored/generated but useful for reproducibility and local startup; preserve.
- `reports/`: generated EDA outputs; preserve as useful reproducible results.

### 3. Redundant and safe to remove — confirmed candidates

These are regenerable build/test caches and do not contain source data or application state:

- `dist/`: generated frontend production build.
- `backend/.pytest_cache/`.
- `backend/app/__pycache__/`.
- `backend/migrations/__pycache__/`.
- `backend/migrations/versions/__pycache__/`.
- `backend/tests/__pycache__/`.

No original or generated CSV, model artifact, report, dependency lock, migration, test, or deployment file is approved for deletion.

### 4. Uncertain — preserve until verified

- `mame.py`: zero-byte but tracked in Git; no references found. Preserve rather than infer intent.
- `.vscode/` and `.ipynb_checkpoints/`: currently contain no listed files; leave untouched.
- `node_modules/`: rebuildable, but retained to avoid disrupting the local development setup.

## Cleanup record

Removed the following regenerable, ignored directories after recording their purpose above:

- `dist/`
- `backend/.pytest_cache/`
- `backend/app/__pycache__/`
- `backend/migrations/__pycache__/`
- `backend/migrations/versions/__pycache__/`
- `backend/tests/__pycache__/`

No source files or datasets were deleted, moved, or archived. All other listed files remain untouched.

The database API filter and dashboard selection fix are documented and covered by the database endpoint test.

## Verification limitations

- Docker is not installed in this environment, so Docker Compose and image builds cannot be verified.
- No AWS resources were accessed or deployed.
- Final verification: Python syntax parsing passed for 19 Python files; backend suite passed (23 tests); React production build passed; Alembic reported `0003_atm_observations (head)`; repeat seeding inserted zero duplicate observations; PostgreSQL-backed authenticated API reads passed; stale production forecasts were blocked with HTTP 409; temporary-directory synthetic training and EDA completed; FastAPI readiness and Vite dashboard page/module checks passed.
- The test runner emits one third-party Starlette/httpx deprecation warning. No test failures remain.
