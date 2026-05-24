# IHSG KAG Forecasting Dashboard

Portfolio project for Indonesian stock forecasting. The project now keeps the original
Neo4j/KAG dashboard flow and adds a Parquet-based hybrid modeling pipeline:

```text
price_features + nlp_features + stock_metadata_features -> single global LightGBM model
```

The first target is a fast proof of concept with 10 large IDX stocks. The same scripts can
scale to 100 stocks by changing the universe CSV and `--limit`.

## Problem Statement

Forecast short-horizon stock movement for Indonesian equities using historical OHLCV data and
news sentiment. The output is decision-support context for analysis, not financial advice.

## Architecture

1. Data ingestion
   - `scripts/collect_prices.py` downloads full available OHLCV history from yfinance and writes Parquet.
   - `scripts/collect_news.py` reads RSS feeds or news API providers into ticker-level rows.
2. Feature engineering
   - `scripts/build_price_features.py` creates technical indicators.
   - `scripts/build_nlp_features.py` creates sentiment, news-count, embedding, PCA, and ticker-date NLP features.
   - `scripts/build_final_dataset.py` fuses price, NLP, temporal, and stock metadata features.
3. Modeling
   - `scripts/train_baseline.py` trains Model A without NLP.
   - `scripts/train_global_model.py` trains Model B with NLP.
   - `scripts/evaluate_models.py` writes the A/B comparison reports.
4. Dashboard
   - `scripts/run_web_dashboard.py` serves a custom HTML/CSS/JS dashboard and JSON API.
   - The dashboard reads real yfinance data and local pipeline artifacts; missing data is shown as empty states.
   - The frontend uses Lightweight Charts for interactive candles, volume, crosshair hover, zoom, and pan.

## Data Sources

- Price data: yfinance IDX symbols such as `BBCA.JK`, `BBRI.JK`, `BMRI.JK`, `TLKM.JK`, `ASII.JK`.
- News RSS defaults:
  - CNBC Indonesia Market
  - Bisnis Finansial
  - Kontan Investasi
- News API options:
  - `gdelt`: no API key, useful for quick POC collection.
  - `newsapi`: NewsAPI.org-compatible provider, requires `NEWSAPI_API_KEY`.
- News image extraction:
  - RSS/API image fields are saved as `image_url` when available.
  - If the feed does not expose an image, the collector tries the article page `og:image`.
  - If no real image is available, `image_url` stays empty and the dashboard shows a visual fallback.
- Stock universe:
  - POC: `data/seeds/idx_top10_poc.csv`
  - Scale-up candidate: `data/seeds/idx_stock_universe.csv`

RSS sources can be overridden with `NEWS_RSS_FEEDS` or `--rss-sources` using:

```text
Source Name|https://example.com/rss,Other Source|https://example.com/rss
```

API-based news collection:

```powershell
python scripts/collect_news.py --provider gdelt --limit 500 --max-per-ticker 50
python scripts/collect_news.py --provider newsapi --api-key YOUR_KEY --limit 500
```

## Feature Engineering

Price features include SMA, EMA, RSI, MACD, Bollinger Bands, ATR, volume indicators, returns,
rolling volatility, moving-average ratios, drawdown, price position, and momentum. The current
technical feature builder creates about 50 numerical price features per ticker-date.

The target columns are:

- `next_day_price`
- `target_return = next_day_price / close - 1`
- `direction = 1 if target_return > 0 else 0`
- `market_next_return`, `target_excess_return`, and `outperform_market` for market-relative evaluation
- `sector_next_return`, `target_sector_excess_return`, and `outperform_sector` for sector-relative evaluation

Temporal features include day, week, month, and day of week. Metadata features include ticker and
sector encodings, market-cap-rank encoding, beta, and a beta-missing indicator.

## NLP Pipeline

`scripts/build_nlp_features.py` performs:

- text preprocessing
- sentiment scoring
- ticker/date aggregation
- embedding generation
- PCA reduction to 50 dimensions

The preferred embedding model is `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.
If transformer models are not available locally, the code falls back to deterministic hashing
embeddings. Sentiment uses a configurable Indonesian transformer model in `auto` mode and falls
back to a transparent Indonesian market lexicon if the model cannot be loaded.

NLP output is saved to `data/nlp_features.parquet` with:

- `sentiment_mean`
- `sentiment_std`
- `news_count`
- `sentiment_momentum`
- `embedding_dim_0` to `embedding_dim_49`

When the final dataset is built, NLP rows are shifted by one trading row by default before they
join to price features. This is intentionally conservative because the raw news artifact stores
dates, not exact publication timestamps. Use `--nlp-lag-trading-days 0` only for experiments where
same-day news availability is explicitly trusted.

## Why Single Global Model

This project intentionally uses one global model for all stocks, not one model per stock.

- It is lighter to train and deploy.
- It can learn cross-stock and sector-level patterns.
- Stocks with sparse news can benefit from patterns learned from other stocks.
- The dashboard and deployment only need one primary artifact.
- The primary artifact now stores a return regressor plus an optional direction classifier, so
  expected return and up/down probability can be evaluated separately.

## Baseline vs NLP Evaluation

A/B testing is explicit:

- Model A: price features + metadata, no NLP.
- Model B: price features + metadata + NLP features.

`scripts/evaluate_models.py` writes:

- `reports/metrics.json`
- `reports/model_comparison.md`
- `reports/feature_importance.png`

The comparison reports baseline MAPE, NLP model MAPE, improvement percentage, directional
accuracy from the regressor sign, direction-classifier accuracy, rank information coefficient,
top-N excess return, long-short return, and top feature importance. If NLP does not improve the
result, the report keeps the actual metrics and notes likely causes such as insufficient news
volume, market-date alignment, sentiment mismatch, leakage controls, or weak NLP features.

## How To Run Locally

Create and install the environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,data,ml,nlp]"
```

Run the POC pipeline:

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

For a faster offline NLP smoke run after `news_raw.parquet` exists:

```powershell
python scripts/build_nlp_features.py --sentiment-backend lexicon --embedding-backend hashing
```

Run or refresh the top-100 stock universe:

```powershell
python scripts/collect_prices.py
python scripts/collect_news.py --universe data/seeds/idx_stock_universe.csv --limit 10000
python scripts/build_final_dataset.py --metadata data/seeds/idx_stock_universe.csv
```

Run the dashboard:

```powershell
.venv\Scripts\python.exe scripts/run_web_dashboard.py --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

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

## Testing

Run lint and tests:

```powershell
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m pytest
```

## Limitations

- RSS feeds may not mention tickers consistently, so early NLP coverage can be sparse.
- News timestamps may not align perfectly with IDX trading dates.
- Fallback sentiment is transparent but weaker than a domain-tuned Indonesian finance model.
- yfinance can rate-limit or miss some IDX tickers.
- The POC top-10 seed is not a live market-cap ranking service.

## Future Improvement

- Replace the seeded top-100 universe with a maintained market-cap metadata source.
- Add article body extraction and richer company aliases.
- Use a finance-tuned Indonesian sentiment model.
- Add walk-forward backtests and transaction-cost assumptions.
- Deploy a lightweight Hugging Face Spaces app using real exported pipeline artifacts.
