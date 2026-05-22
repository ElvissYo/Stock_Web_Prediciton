# KAG Stock Forecasting Dashboard

Knowledge-Augmented Generation (KAG) stock forecasting dashboard for IHSG market
analysis. This repository is being built phase by phase.

## Phase 0 Scope

Current implementation covers the project foundation:

- Environment variable loading
- Neo4j connection settings
- Neo4j schema/index bootstrap
- Connection validation script
- Focused unit tests for configuration and schema definitions

## Phase 1 Current Scope

The first Phase 1 slices cover stock universe and historical price ingestion:

- Load stock metadata from CSV
- Merge `Stock` and `Sector` nodes
- Create `(:Stock)-[:IN_SECTOR]->(:Sector)` relationships
- Fetch historical OHLCV prices from yfinance
- Merge `PricePoint` nodes
- Create `(:Stock)-[:HAS_PRICE]->(:PricePoint)` relationships
- Calculate return correlations between stocks
- Create `(:Stock)-[:CORRELATED_WITH]->(:Stock)` relationships

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

For Neo4j integration:

```powershell
.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Edit `.env` with your local Neo4j credentials.

## Verify Phase 0

Start local Neo4j with Docker:

```powershell
docker compose up -d neo4j
```

Run unit tests:

```powershell
.venv\Scripts\python.exe -m pytest
```

Check Neo4j connectivity:

```powershell
.venv\Scripts\python.exe scripts/check_neo4j_connection.py
```

Create Neo4j constraints and indexes:

```powershell
.venv\Scripts\python.exe scripts/setup_neo4j_schema.py
```

Fetch the expanded IDX stock universe CSV:

```powershell
.venv\Scripts\python.exe scripts/fetch_idx_stock_universe.py --output data/seeds/idx_stock_universe.csv
```

This uses StockAnalysis as the current broad IDX listing source and keeps the fetcher isolated so
an official IDX source can replace it later.

Ingest the expanded stock universe:

```powershell
.venv\Scripts\python.exe scripts/ingest_stock_universe.py --csv data/seeds/idx_stock_universe.csv
```

Install market data dependencies:

```powershell
.venv\Scripts\python.exe -m pip install -e ".[data]"
```

Ingest recent historical prices from yfinance:

```powershell
.venv\Scripts\python.exe scripts/ingest_historical_prices.py --period 1mo --interval 1d --limit 50 --skip-schema
```

Use `--limit` or `--ticker BBCA --ticker TLKM` while experimenting. Pulling prices for the full IDX
universe can hit provider rate limits and takes longer.

Build stock correlation relationships:

```powershell
.venv\Scripts\python.exe scripts/build_stock_correlations.py --min-observations 20 --min-abs-correlation 0.3
```

By default this replaces stale `CORRELATED_WITH` relationships for the calculated universe. Use
`--append` only when you intentionally want to avoid cleanup.

Build an initial supervised feature dataset:

```powershell
.venv\Scripts\python.exe scripts/build_training_dataset.py --output data/processed/training_features.csv
```

The feature builder adds generated rolling features for multiple windows, including returns,
volatility, drawdown, price position, and volume ratios.

Install ML dependencies:

```powershell
.venv\Scripts\python.exe -m pip install -e ".[ml]"
```

Train the baseline next-direction model:

```powershell
.venv\Scripts\python.exe scripts/train_direction_model.py --dataset data/processed/training_features.csv
```

Predict latest next-direction probabilities from Neo4j graph features:

```powershell
.venv\Scripts\python.exe scripts/predict_latest_direction.py --model models/direction_model.joblib
```

Install dashboard dependencies:

```powershell
.venv\Scripts\python.exe -m pip install -e ".[dashboard]"
```

Run the Streamlit dashboard:

```powershell
.venv\Scripts\python.exe -m streamlit run dashboard/app.py --server.address 127.0.0.1 --server.port 8501
```

The dashboard includes an investment simulator where a user can enter an amount, entry date,
and exit date. Historical ranges use realized prices; future ranges use a simple
model-adjusted projection band.

Run the lightweight daily update pipeline:

```powershell
.venv\Scripts\python.exe scripts/run_daily_update.py --price-period 1mo --limit 50
```

Retrain only when you explicitly want to refresh the model artifact:

```powershell
.venv\Scripts\python.exe scripts/run_daily_update.py --price-period 1y --min-correlation-observations 120 --train-model
```

GitHub Actions workflows:

- `CI` runs lint and tests.
- `Daily Pipeline Smoke` starts a temporary Neo4j service and runs the lightweight update pipeline.

Open Neo4j Browser:

```text
http://localhost:7474
```

Default local credentials come from `.env`.
