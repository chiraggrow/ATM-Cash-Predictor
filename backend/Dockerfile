FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    DATASET_PATH=/app/data/atm_cash.csv \
    MODEL_ARTIFACT_PATH=/app/artifacts/atm-demand.joblib

WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --home-dir /app app

COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY backend/app /app/app
COPY backend/migrations /app/migrations
COPY backend/alembic.ini /app/alembic.ini
COPY atm_cash.csv /app/data/atm_cash.csv
COPY data/generated/atm_cash_10k.csv /app/data/generated/atm_cash_10k.csv

RUN mkdir -p /app/artifacts && chown -R app:app /app
USER app

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
