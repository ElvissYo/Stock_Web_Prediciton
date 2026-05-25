---
title: IHSG Forecasting Dashboard
emoji: 📈
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# IHSG Forecasting Dashboard

A public portfolio dashboard for Indonesian stock forecasting.  
The project combines historical market data, technical indicators, news sentiment, NLP features, and a single global machine learning model to support short-horizon stock movement analysis.

> This project is for educational and portfolio purposes only. It is not financial advice.

---

## Overview

This dashboard is designed to help users understand Indonesian stock market movement through:

- Market overview
- Stock price movement
- Interactive technical chart
- Stock prediction
- News sentiment
- NLP-based summary
- Model performance comparison

The project keeps the original KAG/Neo4j flow available, but the public dashboard mainly uses a lightweight artifact-based pipeline:

```text
price_features + nlp_features + stock_metadata_features
        ↓
single global model
        ↓
prediction + dashboard output
```

For public deployment, the dashboard reads exported runtime artifacts such as Parquet files, model files, and JSON reports. This makes the project easier to deploy without requiring a live database server.

---

## Problem Statement

Forecast short-horizon stock movement for Indonesian equities using historical OHLCV data and news sentiment.

The dashboard is intended to answer questions such as:

- Is the selected stock currently moving up or down?
- What does the model predict for the next movement?
- What is the latest available market condition?
- How does news sentiment relate to the selected stock?
- Does NLP improve the model compared to a baseline model?

---

## Architecture

### 1. Data Ingestion

Price data is collected from yfinance for Indonesian stock tickers such as:

```text
BBCA.JK, BBRI.JK, BMRI.JK, TLKM.JK, ASII.JK
```

Main script:

```powershell
python scripts/collect_prices.py
```

News data is collected from RSS feeds or news providers and stored as ticker-level rows.

Main script:

```powershell
python scripts/collect_news.py
```

Default news sources include:

- CNBC Indonesia Market
- Bisnis Finansial
- Kontan Investasi

News API options:

- `gdelt`: no API key required, useful for proof-of-concept collection
- `newsapi`: NewsAPI.org-compatible provider, requires `NEWSAPI_API_KEY`

---

### 2. Feature Engineering

Price feature builder:

```powershell
python scripts/build_price_features.py
```

NLP feature builder:

```powershell
python scripts/build_nlp_features.py
```

Final dataset builder:

```powershell
python scripts/build_final_dataset.py
```

Price features include:

- SMA
- EMA
- RSI
- MACD
- Bollinger Bands
- ATR
- Volume indicators
- Returns
- Rolling volatility
- Moving-average ratios
- Drawdown
- Price position
- Momentum

NLP features include:

- Sentiment score
- Sentiment standard deviation
- News count
- Sentiment momentum
- Embedding dimensions
- PCA-reduced text representation

---

### 3. Modeling

The project uses one global model for all stocks instead of one model per stock.

Model scripts:

```powershell
python scripts/train_baseline.py
python scripts/train_global_model.py
python scripts/evaluate_models.py
```

Model A:

```text
price features + metadata
```

Model B:

```text
price features + metadata + NLP features
```

The main model artifact is:

```text
models/global_model_with_nlp.joblib
```

---

### 4. Dashboard Runtime

The dashboard is served with a custom Python HTTP server, not Streamlit.

Main entry point:

```text
scripts/run_web_dashboard.py
```

API:

```text
kag/web/api.py
```

Frontend:

```text
web/
```

The dashboard reads local runtime artifacts:

```text
models/global_model_with_nlp.joblib
reports/metrics.json
data/prices_full_top100.parquet
data/final_dataset.parquet
data/processed/price_features.parquet
data/processed/global_model_predictions.parquet
data/news_raw.parquet
data/nlp_features.parquet
```

If a file is missing, the dashboard should show an empty state instead of fake or hardcoded values.

---

## Why Single Global Model?

This project intentionally uses a single global model for all stocks.

Reasons:

- Easier to train and deploy
- Smaller runtime footprint
- Learns cross-stock and sector-level behavior
- Helps stocks with sparse news coverage
- Avoids managing 100 separate models
- More practical for a public portfolio dashboard

The primary model stores return prediction and may include an optional direction classifier for up/down probability.

---

## Baseline vs NLP Evaluation

The project compares two approaches:

| Model | Features |
|---|---|
| Baseline | Price features + stock metadata |
| NLP Model | Price features + stock metadata + news/NLP features |

Evaluation output:

```text
reports/metrics.json
reports/model_comparison.md
reports/feature_importance.png
```

Metrics can include:

- Baseline MAPE
- NLP model MAPE
- Improvement percentage
- Directional accuracy
- Rank information coefficient
- Top-N excess return
- Long-short return

If NLP does not improve the model, the report keeps the actual result and notes possible causes such as:

- Limited news volume
- News-date alignment issues
- Weak sentiment signal
- Market noise
- Sparse ticker coverage
- Feature leakage controls

---

## Data Sources

### Price Data

Price data comes from yfinance IDX symbols.

Example tickers:

```text
BBCA.JK
BBRI.JK
BMRI.JK
TLKM.JK
ASII.JK
```

### News Data

News can come from RSS feeds or API providers.

RSS sources can be overridden using:

```text
NEWS_RSS_FEEDS
```

Format:

```text
Source Name|https://example.com/rss,Other Source|https://example.com/rss
```

Example commands:

```powershell
python scripts/collect_news.py --provider gdelt --limit 500 --max-per-ticker 50
python scripts/collect_news.py --provider newsapi --api-key YOUR_KEY --limit 500
```

### News Images

The news collector stores `image_url` when available.

Image extraction priority:

1. RSS or API image field
2. RSS `media:content`
3. RSS enclosure
4. Article page `og:image`
5. Empty value if no real image is found

If no real image exists, the dashboard shows a visual fallback. It should not use fake hardcoded news images.

---

## NLP Pipeline

The NLP pipeline performs:

- Text preprocessing
- Sentiment scoring
- Ticker/date aggregation
- Embedding generation
- PCA reduction

Preferred embedding model:

```text
sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
```

If transformer models are unavailable, the pipeline can fall back to deterministic hashing embeddings.

Sentiment uses a configurable Indonesian transformer model in auto mode and can fall back to a transparent Indonesian market lexicon if the model cannot be loaded.

NLP output:

```text
data/nlp_features.parquet
```

Main columns:

```text
sentiment_mean
sentiment_std
news_count
sentiment_momentum
embedding_dim_0 ... embedding_dim_49
```

By default, NLP rows are shifted by one trading row before joining price features. This is a conservative design because raw news artifacts may store dates without exact publication timestamps.

---

## Runtime Artifacts

The public dashboard depends on these files:

```text
models/global_model_with_nlp.joblib
reports/metrics.json
data/prices_full_top100.parquet
data/final_dataset.parquet
data/processed/price_features.parquet
data/processed/global_model_predictions.parquet
data/news_raw.parquet
data/nlp_features.parquet
```

These files are tracked using Git LFS because they may be large.

Git LFS patterns:

```text
*.parquet
*.joblib
*.pkl
*.png
models/*.txt
```

---

## Folder Structure

```text
data/
  raw/
  processed/
  prices_full_top100.parquet
  news_raw.parquet
  nlp_features.parquet
  final_dataset.parquet

models/
  baseline_model.txt
  baseline_model.joblib
  global_model_with_nlp.txt
  global_model_with_nlp.joblib
  encoders.pkl
  pca.pkl

reports/
  metrics.json
  feature_importance.png
  model_comparison.md

scripts/
  run_web_dashboard.py
  collect_prices.py
  collect_news.py
  build_price_features.py
  build_nlp_features.py
  build_final_dataset.py
  train_baseline.py
  train_global_model.py
  evaluate_models.py

kag/
  web/
  features/
  market_data/
  modeling/
  news/
  graph/

web/
  index.html
  styles/
    main.css
    animations.css
    responsive.css
  js/
    app.js
    chart.js
    data-loader.js
    news.js
    prediction.js
    ui.js
```

---

## How to Run Locally

Create and install the environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Run the dashboard locally:

```powershell
$env:PORT="7860"
python scripts/run_web_dashboard.py
```

Open:

```text
http://localhost:7860
```

Health check:

```text
http://localhost:7860/api/health
```

Expected response:

```json
{"status": "ok"}
```

---

## Run with Docker

Build the Docker image:

```powershell
docker build -t ihsg-forecasting-dashboard .
```

Run the container:

```powershell
docker run --rm -p 7860:7860 -e PORT=7860 ihsg-forecasting-dashboard
```

Open:

```text
http://localhost:7860
```

---

## Hugging Face Spaces Deployment

This project is prepared for Hugging Face Spaces using Docker.

Space configuration:

```yaml
sdk: docker
app_port: 7860
```

Deployment target:

```text
Hugging Face Spaces Docker
CPU Basic / Free
Public Space
```

Expected public URL format:

```text
https://ElvssYo-ihsg-forecasting-dashboard.hf.space
```

Or Space page:

```text
https://huggingface.co/spaces/ElvssYo/ihsg-forecasting-dashboard
```

Push to Hugging Face remote:

```powershell
git remote add hf https://huggingface.co/spaces/ElvssYo/ihsg-forecasting-dashboard
git push hf main
```

If the Space already contains a default README and rejects the push:

```powershell
git push --force hf main
```

When prompted for password, use a Hugging Face access token with write permission.

---

## Git LFS Setup

Install and track large files:

```powershell
git lfs install
git lfs track "*.parquet" "*.joblib" "*.pkl" "*.png" "models/*.txt"
git add .gitattributes
```

Check tracked files:

```powershell
git lfs ls-files
```

Expected LFS artifacts include:

```text
data/final_dataset.parquet
data/news_raw.parquet
data/nlp_features.parquet
data/prices_full_top100.parquet
data/processed/global_model_predictions.parquet
data/processed/price_features.parquet
models/global_model_with_nlp.joblib
```

---

## Full Pipeline

Run the proof-of-concept pipeline:

```powershell
python scripts/collect_prices.py
python scripts/collect_news.py
python scripts/build_price_features.py
python scripts/build_nlp_features.py
python scripts/build_final_dataset.py
python scripts/train_baseline.py
python scripts/train_global_model.py
python scripts/evaluate_models.py
```

For a faster offline NLP smoke test after `news_raw.parquet` exists:

```powershell
python scripts/build_nlp_features.py --sentiment-backend lexicon --embedding-backend hashing
```

Run or refresh a larger stock universe:

```powershell
python scripts/collect_prices.py
python scripts/collect_news.py --universe data/seeds/idx_stock_universe.csv --limit 10000
python scripts/build_final_dataset.py --metadata data/seeds/idx_stock_universe.csv
```

---

## Legacy Neo4j Flow

The original graph pipeline is still available:

```powershell
docker compose up -d neo4j
.venv\Scripts\python.exe scripts/check_neo4j_connection.py
.venv\Scripts\python.exe scripts/setup_neo4j_schema.py
.venv\Scripts\python.exe scripts/ingest_stock_universe.py --csv data/seeds/idx_stock_universe.csv
.venv\Scripts\python.exe scripts/ingest_historical_prices.py --period 1mo --interval 1d --limit 50 --skip-schema
.venv\Scripts\python.exe scripts/build_stock_correlations.py --min-observations 20 --min-abs-correlation 0.3
.venv\Scripts\python.exe scripts/run_daily_update.py --price-period 1mo --limit 50
```

The public dashboard does not require Neo4j to run.

---

## Testing

Run Python compile checks:

```powershell
python -m py_compile scripts/run_web_dashboard.py
python -m py_compile kag/web/api.py
```

Run tests if available:

```powershell
python -m pytest
```

Run lint if configured:

```powershell
python -m ruff check .
```

---

## Free Deployment Notes

This project is designed to work as a free public demo.

Recommended free architecture:

```text
Hugging Face Spaces Docker
        +
GitHub repository
        +
Git LFS artifacts
```

For the first public launch, the dashboard reads existing model/data artifacts directly from the repository.

A future version can use GitHub Actions to retrain and push updated artifacts automatically.

---

## Limitations

- This is not a production trading system.
- Predictions are for analysis and portfolio demonstration only.
- Hugging Face free Spaces can sleep and may have slower first load.
- Free runtime storage is not intended for persistent retraining output.
- Large artifacts should be kept reasonable for free deployment.
- RSS feeds may not mention tickers consistently.
- News timestamps may not align perfectly with IDX trading dates.
- Fallback sentiment is transparent but weaker than a domain-tuned Indonesian finance model.
- yfinance can rate-limit or miss some IDX tickers.
- The proof-of-concept stock universe is not a live market-cap ranking service.

---

## Future Improvements

- Add GitHub Actions for scheduled retraining.
- Replace the seeded top-100 universe with a maintained market-cap metadata source.
- Add article body extraction and richer company aliases.
- Use a finance-tuned Indonesian sentiment model.
- Add walk-forward backtests.
- Add transaction-cost assumptions.
- Add persistent storage for production-grade deployment.
- Add MLflow or experiment tracking for advanced model lifecycle management.
- Add PostgreSQL or object storage only if the project moves beyond free demo mode.

---

## Disclaimer

This dashboard is built for educational, research, and portfolio purposes.

It does not provide investment advice, financial advice, trading recommendations, or guaranteed predictions. Users should not make financial decisions based solely on this dashboard.