# CashCast — ATM Cash Demand Predictor

A full-stack machine learning project for forecasting ATM cash demand, visualizing cash trends, and supporting data-driven cash replenishment decisions.

## Overview

CashCast combines a React dashboard, FastAPI backend, machine learning pipeline, and PostgreSQL database to demonstrate an end-to-end ATM cash-demand forecasting workflow.

**Note:** This is a prototype, not a live cash-control system. The project uses synthetic or configured historical observations rather than a verified live ATM transaction feed.

## Key Features

- ATM cash-demand forecasting
- Interactive analytics dashboard
- Historical data visualization
- REST API built with FastAPI
- PostgreSQL data persistence
- Configurable data source and model pipeline
- Docker Compose deployment

## Tech Stack

| Component | Technology |
|---|---|
| Frontend | React |
| Backend | FastAPI, Python |
| Machine Learning | scikit-learn |
| Database | PostgreSQL |
| Deployment | Docker, Docker Compose |
| Data Analysis | Pandas, NumPy |

## Architecture

React Dashboard → FastAPI REST API → Forecasting Pipeline → PostgreSQL

The exact data flow depends on the configured services and model implementation.

## Getting Started

### Prerequisites

- Docker Desktop
- Git
- A configured `.env` file based on `.env.example`

### Installation

```bash
git clone YOUR_REPOSITORY_URL
cd ATM-CASH-DEMAND-PREDICTOR
cp .env.example .env
```

Configure the environment variables in `.env`, then start the services:

```bash
docker compose up --build
```

### Access the Application

- **Dashboard:** http://localhost:8080
- **API documentation:** http://localhost:8000/docs, if the backend exposes port 8000

Check `docker-compose.yml` for the actual service ports.

## Project Structure

```text
ATM-CASH-DEMAND-PREDICTOR/
├── src/                 # Frontend source
├── data/                # Data and generated datasets
├── reports/             # Reports and analysis
├── deploy/              # Deployment configuration
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

Adjust this structure to match the actual repository contents.

## Limitations

- Forecast quality depends on data quality and model configuration.
- Synthetic data does not represent verified live ATM operations.
- Production deployment requires secure credentials, monitoring, validation, and operational testing.

## Future Improvements

- Evaluate multiple forecasting models
- Add model performance metrics
- Improve forecast visualizations
- Add automated model retraining
- Deploy a production-ready version

## License

Add a license if you intend to distribute this project publicly.
