"""Data access and formatting helpers for the custom dashboard."""

from __future__ import annotations

import csv
from datetime import date
from datetime import datetime
from datetime import timedelta
from html.parser import HTMLParser
import json
from pathlib import Path
import statistics
from typing import Any
from urllib.parse import quote
from urllib.parse import urljoin
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import warnings

from kag.graph.client import Neo4jClient


DEFAULT_PREDICTIONS_PATH = Path("data/processed/latest_direction_predictions.csv")
DEFAULT_METRICS_PATH = Path("models/direction_model_metrics.json")
DEFAULT_GLOBAL_PREDICTIONS_PATH = Path("data/processed/global_model_predictions.parquet")
DEFAULT_MODEL_COMPARISON_PATH = Path("reports/metrics.json")
DEFAULT_PRICE_HISTORY_PATH = Path("data/prices_full_top100.parquet")
LEGACY_PRICE_HISTORY_PATH = Path("data/prices_20y_top100.parquet")
DEFAULT_PRICE_FEATURES_PATH = Path("data/processed/price_features.parquet")
DEFAULT_STOCK_UNIVERSE_PATH = Path("data/seeds/idx_stock_universe.csv")
DEFAULT_COMPANY_PROFILE_CACHE_PATH = Path("data/processed/company_profiles.json")
DEFAULT_NEWS_PATH = Path("data/news_raw.parquet")
DEFAULT_NLP_FEATURES_PATH = Path("data/nlp_features.parquet")
DEFAULT_FINAL_DATASET_PATH = Path("data/final_dataset.parquet")
DEFAULT_GLOBAL_MODEL_PATH = Path("models/global_model_with_nlp.joblib")
USER_FACING_DRIVER_LABELS = {
    "trend": "Technical trend",
    "momentum": "Market momentum",
    "volume": "Volume pressure",
    "sentiment": "News sentiment",
    "volatility": "Volatility",
    "model": "Model confidence",
}


def load_prediction_rows(path: str | Path = DEFAULT_PREDICTIONS_PATH) -> list[dict[str, Any]]:
    """Load latest direction predictions from CSV."""

    csv_path = Path(path)
    if not csv_path.exists():
        return []

    with csv_path.open("r", encoding="utf-8", newline="") as file:
        return normalize_prediction_rows(csv.DictReader(file))


def normalize_prediction_rows(rows: Any) -> list[dict[str, Any]]:
    """Normalize prediction rows from CSV/records into typed dictionaries."""

    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        normalized_rows.append(
            {
                "ticker": row["ticker"],
                "date": row["date"],
                "sector": row["sector"],
                "close": _float_or_none(row.get("close")),
                "probability_up": _float_or_none(row.get("probability_up")),
                "predicted_direction": _int_or_none(row.get("predicted_direction")),
                "model_type": row.get("model_type") or "unknown",
            }
        )

    return normalized_rows


def load_model_metrics(path: str | Path = DEFAULT_METRICS_PATH) -> dict[str, Any]:
    """Load model metrics JSON if it exists."""

    metrics_path = Path(path)
    if not metrics_path.exists():
        return {}

    return json.loads(metrics_path.read_text(encoding="utf-8"))


def load_global_prediction_rows(
    path: str | Path = DEFAULT_GLOBAL_PREDICTIONS_PATH,
) -> list[dict[str, Any]]:
    """Load latest global model predictions from Parquet or CSV."""

    data_path = Path(path)
    if not data_path.exists():
        return []

    frame = _read_tabular_file(data_path)
    rows = []
    for row in frame.to_dict("records"):
        rows.append(
            {
                "ticker": row["ticker"],
                "date": _date_text(row.get("date")),
                "sector": row.get("sector") or "UNKNOWN",
                "close": _float_or_none(row.get("close")),
                "predicted_return": _float_or_none(row.get("predicted_return")),
                "predicted_direction": _int_or_none(row.get("predicted_direction")),
                "probability_up": _float_or_none(row.get("probability_up")),
                "confidence": _float_or_none(row.get("confidence")),
                "model_name": row.get("model_name") or "global_model",
                "model_type": row.get("model_type") or "unknown",
            }
        )
    return rows


def load_model_comparison(path: str | Path = DEFAULT_MODEL_COMPARISON_PATH) -> dict[str, Any]:
    """Load baseline vs NLP comparison metrics."""

    metrics_path = Path(path)
    if not metrics_path.exists():
        return {}
    return json.loads(metrics_path.read_text(encoding="utf-8"))


def load_last_updated() -> dict[str, Any]:
    """Return honest freshness metadata from local artifacts."""

    paths = [
        DEFAULT_PRICE_HISTORY_PATH,
        LEGACY_PRICE_HISTORY_PATH,
        DEFAULT_NEWS_PATH,
        DEFAULT_NLP_FEATURES_PATH,
        DEFAULT_PRICE_FEATURES_PATH,
        DEFAULT_FINAL_DATASET_PATH,
        DEFAULT_GLOBAL_PREDICTIONS_PATH,
        DEFAULT_GLOBAL_MODEL_PATH,
        DEFAULT_MODEL_COMPARISON_PATH,
    ]
    existing_paths = [Path(path) for path in paths if Path(path).exists()]
    latest_artifact_time = max(
        (datetime.fromtimestamp(path.stat().st_mtime) for path in existing_paths),
        default=None,
    )
    return {
        "mode": "local_snapshot",
        "status_label": "Latest available market data",
        "refresh_label": "Live refresh enabled",
        "latest_artifact_update": latest_artifact_time.isoformat(timespec="seconds")
        if latest_artifact_time
        else None,
        "latest_market_date": _latest_date_from_table(_resolve_price_history_path(DEFAULT_PRICE_HISTORY_PATH)),
        "latest_news_date": _latest_date_from_table(DEFAULT_NEWS_PATH),
        "latest_prediction_date": _latest_date_from_table(DEFAULT_GLOBAL_PREDICTIONS_PATH),
        "artifacts": artifact_freshness_rows(existing_paths),
    }


def artifact_freshness_rows(paths: list[Path]) -> list[dict[str, Any]]:
    rows = []
    for path in paths:
        rows.append(
            {
                "path": str(path),
                "exists": path.exists(),
                "bytes": path.stat().st_size if path.exists() else None,
                "modified_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
                if path.exists()
                else None,
            }
        )
    return rows


def load_market_overview() -> dict[str, Any]:
    """Build a user-facing market overview from prices, predictions, and news."""

    candles = load_local_price_ohlcv("^JKSE", period="max", interval="1d")
    if not candles:
        try:
            candles = load_yfinance_ohlcv("^JKSE", period="1y", interval="1d")
        except Exception:
            candles = []

    latest = candles[-1] if candles else {}
    previous = candles[-2] if len(candles) > 1 else {}
    latest_close = _float_or_none(latest.get("close"))
    previous_close = _float_or_none(previous.get("close"))
    daily_change = None
    if latest_close is not None and previous_close and previous_close > 0:
        daily_change = (latest_close / previous_close) - 1

    predictions = load_global_prediction_rows()
    prediction_count = len(predictions)
    bullish_count = sum(1 for row in predictions if row.get("predicted_direction") == 1)
    avg_confidence = _mean_or_none([row.get("confidence") for row in predictions])
    avg_predicted_return = _mean_or_none([row.get("predicted_return") for row in predictions])

    market_news = load_recent_news_rows(None, limit=100)
    sentiment_score = _mean_or_none([row.get("sentiment_score") for row in market_news])
    movers = load_market_movers(limit=10)
    return {
        "status": "ok" if candles or predictions else "empty",
        "source": latest.get("source") or "local artifacts",
        "index": {
            "symbol": "^JKSE",
            "name": "IDX Composite",
            "date": latest.get("date"),
            "close": latest_close,
            "previous_close": previous_close,
            "daily_change": daily_change,
            "direction": "up" if (daily_change or 0) > 0 else "down" if (daily_change or 0) < 0 else "neutral",
        },
        "prediction": {
            "covered_stocks": prediction_count,
            "bullish_count": bullish_count,
            "bearish_count": max(prediction_count - bullish_count, 0),
            "bullish_ratio": bullish_count / prediction_count if prediction_count else None,
            "avg_confidence": avg_confidence,
            "avg_predicted_return": avg_predicted_return,
            "bias": _market_bias(bullish_count, prediction_count),
        },
        "sentiment": {
            "score": sentiment_score,
            "label": sentiment_label(sentiment_score),
            "news_count": len(market_news),
        },
        "movers": {
            "available_tickers": movers.get("available_tickers", 0),
            "top_gainer": (movers.get("gainers") or [None])[0],
            "top_loser": (movers.get("losers") or [None])[0],
        },
        "freshness": load_last_updated(),
    }


def load_model_performance_summary() -> dict[str, Any]:
    """Return model metrics summarized for non-technical users."""

    metrics = load_model_comparison()
    if not metrics:
        return {"status": "empty", "message": "Model performance report belum ditemukan."}

    comparison = metrics.get("comparison", {})
    baseline = metrics.get("baseline", {})
    nlp_model = metrics.get("nlp_model", {})
    final_stats = _dataset_stats(DEFAULT_FINAL_DATASET_PATH)
    news_stats = _news_stats(DEFAULT_NEWS_PATH)
    return {
        "status": "ok",
        "baseline_mape": _float_or_none(comparison.get("baseline_mape")),
        "nlp_model_mape": _float_or_none(comparison.get("nlp_model_mape")),
        "improvement_pct": _float_or_none(comparison.get("mape_improvement_pct")),
        "directional_accuracy": _float_or_none(comparison.get("nlp_directional_accuracy")),
        "direction_classifier_accuracy": _float_or_none(
            comparison.get("nlp_direction_classifier_accuracy")
        ),
        "rank_ic": _float_or_none(comparison.get("nlp_rank_ic")),
        "top_n_excess_return": _float_or_none(comparison.get("nlp_top_n_excess_return")),
        "last_training_date": nlp_model.get("train_end_date") or baseline.get("train_end_date"),
        "stocks_covered": final_stats["stocks"],
        "data_rows": final_stats["rows"],
        "news_articles": news_stats["rows"],
        "latest_news_date": news_stats["latest_date"],
        "model_type": nlp_model.get("model_type") or baseline.get("model_type") or "unknown",
        "narrative": _model_narrative(comparison),
    }


def load_market_symbols(
    path: str | Path = DEFAULT_STOCK_UNIVERSE_PATH,
    *,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Load IHSG plus the top stock universe used by the dashboard selectors."""

    symbols = [
        {
            "ticker": "IHSG",
            "symbol": "^JKSE",
            "name": "IDX Composite",
            "sector": "Index",
            "rank": 0,
        }
    ]
    universe_path = Path(path)
    if not universe_path.exists():
        return symbols

    with universe_path.open("r", encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    profile_cache = _read_profile_cache()

    def rank(row: dict[str, Any]) -> int:
        return _int_or_none(row.get("universe_rank") or row.get("market_cap_rank")) or 1_000_000

    for row in sorted(rows, key=rank)[:limit]:
        ticker = str(row.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        cached_profile = profile_cache.get(ticker, {})
        symbols.append(
            {
                "ticker": ticker,
                "symbol": str(row.get("yfinance_symbol") or f"{ticker}.JK").strip(),
                "name": cached_profile.get("name") or str(row.get("name") or ticker).strip(),
                "sector": cached_profile.get("sector") or str(row.get("sector") or "UNKNOWN").strip(),
                "logo_url": cached_profile.get("logo_url"),
                "logo_candidates": _logo_candidates(cached_profile),
                "website": cached_profile.get("website") or "",
                "rank": rank(row),
            }
        )
    return symbols


def load_market_movers(
    path: str | Path = DEFAULT_PRICE_HISTORY_PATH,
    *,
    limit: int = 10,
) -> dict[str, Any]:
    """Compute top gainers and losers from the latest local price artifact."""

    data_path = _resolve_price_history_path(path)
    if not data_path.exists():
        return {
            "source": str(data_path),
            "available_tickers": 0,
            "gainers": [],
            "losers": [],
        }

    frame = _read_tabular_file(data_path)
    if frame.empty:
        return {
            "source": str(data_path),
            "available_tickers": 0,
            "gainers": [],
            "losers": [],
        }

    pd = _require_pandas()
    frame = frame.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame = frame.dropna(subset=["ticker", "date", "close"]).sort_values(["ticker", "date"])

    metadata = {row["ticker"]: row for row in load_market_symbols(limit=1000)}
    profile_cache = _read_profile_cache()
    rows = []
    for ticker, group in frame.groupby(frame["ticker"].astype(str).str.upper()):
        valid = group.dropna(subset=["close"]).tail(2)
        if len(valid) < 2:
            continue
        previous = float(valid.iloc[0]["close"])
        latest = float(valid.iloc[1]["close"])
        if previous <= 0:
            continue
        symbol_meta = metadata.get(ticker, {})
        cached_profile = profile_cache.get(ticker, {})
        rows.append(
            {
                "ticker": ticker,
                "symbol": valid.iloc[1].get("yfinance_symbol") or symbol_meta.get("symbol") or f"{ticker}.JK",
                "name": symbol_meta.get("name") or ticker,
                "logo_url": cached_profile.get("logo_url"),
                "logo_candidates": _logo_candidates(cached_profile),
                "website": cached_profile.get("website") or "",
                "date": _date_text(valid.iloc[1].get("date")),
                "close": latest,
                "previous_close": previous,
                "change": latest - previous,
                "change_pct": (latest / previous) - 1,
            }
        )

    gainers = sorted(rows, key=lambda row: row["change_pct"], reverse=True)[:limit]
    losers = sorted(rows, key=lambda row: row["change_pct"])[:limit]
    return {
        "source": str(data_path),
        "available_tickers": len(rows),
        "gainers": gainers,
        "losers": losers,
    }


def load_market_watchlist(
    path: str | Path = DEFAULT_PRICE_HISTORY_PATH,
    *,
    limit: int = 100,
) -> dict[str, Any]:
    """Build a trading-workspace watchlist from local price and prediction artifacts."""

    metadata_rows = [row for row in load_market_symbols(limit=1000) if row["ticker"] != "IHSG"]
    predictions = {row["ticker"]: row for row in load_global_prediction_rows()}
    data_path = _resolve_price_history_path(path)
    latest_prices: dict[str, dict[str, Any]] = {}

    if data_path.exists():
        frame = _read_tabular_file(data_path)
        if not frame.empty:
            pd = _require_pandas()
            frame = frame.copy()
            frame["ticker"] = frame["ticker"].astype(str).str.upper()
            frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
            frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
            if "volume" in frame.columns:
                frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce")
            else:
                frame["volume"] = None
            frame = frame.dropna(subset=["ticker", "date", "close"]).sort_values(["ticker", "date"])

            for ticker, group in frame.groupby("ticker"):
                valid = group.dropna(subset=["close"]).tail(2)
                if valid.empty:
                    continue
                latest = valid.iloc[-1]
                previous = valid.iloc[-2] if len(valid) > 1 else None
                latest_close = _float_or_none(latest.get("close"))
                previous_close = _float_or_none(previous.get("close")) if previous is not None else None
                daily_change = (
                    latest_close - previous_close
                    if latest_close is not None and previous_close is not None
                    else None
                )
                daily_change_pct = (
                    (latest_close / previous_close) - 1
                    if latest_close is not None and previous_close and previous_close > 0
                    else None
                )
                latest_prices[ticker] = {
                    "date": _date_text(latest.get("date")),
                    "last_price": latest_close,
                    "previous_close": previous_close,
                    "daily_change": daily_change,
                    "daily_change_pct": daily_change_pct,
                    "volume": _int_or_none(latest.get("volume")),
                    "symbol": latest.get("yfinance_symbol") or f"{ticker}.JK",
                }

    rows = []
    for meta in metadata_rows:
        ticker = meta["ticker"]
        price = latest_prices.get(ticker, {})
        prediction = predictions.get(ticker, {})
        rows.append(
            {
                "ticker": ticker,
                "symbol": price.get("symbol") or meta.get("symbol") or f"{ticker}.JK",
                "company_name": meta.get("name") or ticker,
                "name": meta.get("name") or ticker,
                "sector": meta.get("sector") or "UNKNOWN",
                "rank": meta.get("rank"),
                "date": price.get("date"),
                "last_price": price.get("last_price"),
                "previous_close": price.get("previous_close"),
                "daily_change": price.get("daily_change"),
                "daily_change_pct": price.get("daily_change_pct"),
                "volume": price.get("volume"),
                "prediction_direction": _watchlist_prediction_direction(prediction),
                "prediction_return": prediction.get("predicted_return"),
                "prediction_confidence": prediction.get("confidence"),
                "prediction_probability_up": prediction.get("probability_up"),
                "logo_url": meta.get("logo_url"),
                "logo_candidates": meta.get("logo_candidates") or [],
            }
        )

    rows.sort(
        key=lambda row: (
            row["last_price"] is None,
            row.get("rank") if row.get("rank") is not None else 1_000_000,
            row["ticker"],
        )
    )
    return {
        "source": str(data_path),
        "prediction_source": str(DEFAULT_GLOBAL_PREDICTIONS_PATH),
        "available_tickers": sum(1 for row in rows if row.get("last_price") is not None),
        "stocks": rows[:limit],
    }


def load_company_profile(
    ticker: str,
    *,
    cache_path: str | Path = DEFAULT_COMPANY_PROFILE_CACHE_PATH,
    fetch_remote: bool = True,
) -> dict[str, Any]:
    """Load company metadata and a real logo URL when one can be discovered."""

    cleaned = ticker.upper().replace(".JK", "").strip()
    if cleaned in {"IHSG", "^JKSE"}:
        return {
            "ticker": "IHSG",
            "symbol": "^JKSE",
            "name": "IDX Composite",
            "sector": "Index",
            "industry": "Index",
            "website": "",
            "logo_url": None,
            "logo_candidates": [],
            "logo_source": None,
        }

    symbol_rows = {row["ticker"]: row for row in load_market_symbols(limit=1000)}
    base = symbol_rows.get(
        cleaned,
        {
            "ticker": cleaned,
            "symbol": f"{cleaned}.JK",
            "name": cleaned,
            "sector": "UNKNOWN",
            "rank": None,
        },
    )
    cache = _read_profile_cache(cache_path)
    cached = cache.get(cleaned, {})
    profile = {**base, **cached}

    if cached.get("checked") or not fetch_remote:
        return _with_logo_candidates(profile)

    try:
        remote = _fetch_yfinance_profile(profile["symbol"])
    except Exception as exc:
        profile["checked"] = False
        profile["profile_error"] = str(exc)
        return _with_logo_candidates(profile)

    profile = {
        **profile,
        **{key: value for key, value in remote.items() if value is not None},
        "ticker": cleaned,
        "symbol": profile["symbol"],
    }
    profile = _with_logo_candidates(profile)
    cache[cleaned] = profile
    _write_profile_cache(cache, cache_path)
    return profile


def load_yfinance_ohlcv(
    symbol: str,
    *,
    period: str = "1y",
    interval: str = "1d",
) -> list[dict[str, Any]]:
    """Load real OHLCV candles from Yahoo Finance."""

    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError(
            "yfinance is not installed. Run: .venv\\Scripts\\python.exe -m pip install -e \".[data]\""
        ) from exc

    yf_period = "max" if period in {"10y", "20y"} else period
    try:
        frame = yf.download(
            symbol,
            period=yf_period,
            interval=interval,
            auto_adjust=False,
            actions=False,
            progress=False,
            threads=False,
            timeout=20,
        )
    except TypeError:
        ticker = yf.Ticker(symbol)
        frame = ticker.history(period=yf_period, interval=interval, auto_adjust=False, actions=False)
    if frame.empty:
        return []

    if hasattr(frame.columns, "nlevels") and frame.columns.nlevels > 1:
        frame = frame.copy()
        frame.columns = [column[0] for column in frame.columns]

    rows = []
    for index, row in frame.reset_index().iterrows():
        del index
        date_value = row.get("Date") if "Date" in row else row.get("Datetime")
        rows.append(
            {
                "date": _market_time_text(date_value, interval=interval),
                "open": _float_or_none(row.get("Open")),
                "high": _float_or_none(row.get("High")),
                "low": _float_or_none(row.get("Low")),
                "close": _float_or_none(row.get("Close")),
                "volume": _int_or_none(row.get("Volume")),
                "symbol": symbol,
                "source": "Yahoo Finance / yfinance",
            }
        )
    return [row for row in rows if row["date"] and row["close"] is not None]


def load_local_price_ohlcv(
    symbol: str,
    *,
    period: str = "1y",
    interval: str = "1d",
    path: str | Path = DEFAULT_PRICE_HISTORY_PATH,
) -> list[dict[str, Any]]:
    """Load OHLCV candles from the local price pipeline artifact when available."""

    if interval not in {"1d", "5d", "1wk", "1mo"}:
        return []

    data_path = _resolve_price_history_path(path)
    if not data_path.exists():
        return []

    frame = _read_tabular_file(data_path)
    if frame.empty:
        return []

    ticker = _ticker_from_symbol(symbol)
    symbol_upper = symbol.upper()
    mask = frame["ticker"].astype(str).str.upper().eq(ticker)
    if "yfinance_symbol" in frame.columns:
        mask = mask | frame["yfinance_symbol"].astype(str).str.upper().eq(symbol_upper)
    frame = frame[mask].copy()
    if frame.empty:
        return []

    pd = _require_pandas()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.dropna(subset=["date", "close"]).sort_values("date")
    frame = _filter_price_period(frame, period)

    rows = []
    for row in frame.to_dict("records"):
        rows.append(
            {
                "date": _market_time_text(row.get("date"), interval=interval),
                "open": _float_or_none(row.get("open")),
                "high": _float_or_none(row.get("high")),
                "low": _float_or_none(row.get("low")),
                "close": _float_or_none(row.get("close")),
                "volume": _int_or_none(row.get("volume")),
                "symbol": row.get("yfinance_symbol") or symbol,
                "source": str(data_path),
            }
        )
    return [row for row in rows if row["date"] and row["close"] is not None]


def generate_latest_global_prediction(
    ticker: str,
    *,
    model_path: str | Path = DEFAULT_GLOBAL_MODEL_PATH,
    dataset_path: str | Path = DEFAULT_FINAL_DATASET_PATH,
) -> dict[str, Any]:
    """Generate a real latest prediction from the trained global model artifact."""

    model_file = Path(model_path)
    if not model_file.exists():
        return {
            "status": "missing_model",
            "message": "Model file not found. Please train the model first.",
        }

    dataset_file = Path(dataset_path)
    if not dataset_file.exists():
        return {
            "status": "missing_dataset",
            "message": "Final dataset not found. Please run build_final_dataset.py.",
        }

    try:
        import joblib
    except ImportError as exc:
        raise RuntimeError(
            "joblib is not installed. Run: .venv\\Scripts\\python.exe -m pip install -e \".[ml]\""
        ) from exc

    pd = _require_pandas()
    artifact = joblib.load(model_file)
    model = artifact.get("model")
    direction_model = artifact.get("direction_model")
    feature_columns = artifact.get("feature_columns") or []
    if model is None or not feature_columns:
        return {"status": "invalid_model", "message": f"Invalid model artifact: {model_file}"}

    frame = pd.read_parquet(dataset_file)
    ticker_frame = frame[frame["ticker"].astype(str).str.upper() == ticker.upper()].copy()
    if ticker_frame.empty:
        return {
            "status": "missing_ticker",
            "message": f"No real feature rows found for {ticker}. Run the feature pipeline first.",
        }

    ticker_frame["date"] = pd.to_datetime(ticker_frame["date"], errors="coerce")
    latest = ticker_frame.sort_values("date").iloc[-1:].copy()
    for column in feature_columns:
        if column not in latest.columns:
            return {"status": "missing_feature", "message": f"Missing model feature column: {column}"}

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="X does not have valid feature names")
        predicted_return = float(model.predict(latest[feature_columns])[0])
        if direction_model is not None:
            probability_up = float(direction_model.predict_proba(latest[feature_columns])[0][1])
            predicted_direction = int(direction_model.predict(latest[feature_columns])[0])
        else:
            probability_up = None
            predicted_direction = 1 if predicted_return > 0 else 0
    close = _float_or_none(latest.iloc[0].get("close"))
    volatility = _float_or_none(latest.iloc[0].get("volatility_20d")) or 0.0
    confidence = (
        min(abs(probability_up - 0.5) * 2, 1.0)
        if probability_up is not None
        else _prediction_confidence(predicted_return, volatility)
    )
    return {
        "status": "ok",
        "ticker": ticker.upper(),
        "date": _date_text(latest.iloc[0].get("date")),
        "sector": latest.iloc[0].get("sector") or "UNKNOWN",
        "close": close,
        "predicted_return": predicted_return,
        "predicted_direction": predicted_direction,
        "probability_up": probability_up,
        "confidence": confidence,
        "model_name": artifact.get("model_name") or "global_model_with_nlp",
        "model_type": artifact.get("model_type") or "unknown",
        "direction_model_type": artifact.get("direction_model_type"),
        "source": "Generated by trained LightGBM model"
        if artifact.get("model_type") == "lightgbm"
        else "Generated by trained model artifact",
    }


def load_prediction_drivers(ticker: str) -> dict[str, Any]:
    """Summarize model context into user-facing drivers without exposing raw features."""

    cleaned = ticker.upper().replace(".JK", "").strip()
    prediction = generate_latest_global_prediction(cleaned)
    history = load_price_feature_history(cleaned, limit=260)
    nlp_summary = load_latest_nlp_summary(cleaned)
    profile = load_company_profile(cleaned, fetch_remote=False)
    drivers = []

    latest = history[-1] if history else {}
    previous_5 = history[-6] if len(history) >= 6 else None
    close = _float_or_none(latest.get("close"))
    sma20 = _float_or_none(latest.get("SMA_20"))
    sma50 = _float_or_none(latest.get("SMA_50"))
    volume = _float_or_none(latest.get("volume"))
    average_volume = _mean_or_none([row.get("volume") for row in history[-20:]])

    trend_score = _bounded_score(_relative_position(close, sma50))
    drivers.append(
        {
            "key": "trend",
            "label": USER_FACING_DRIVER_LABELS["trend"],
            "value": _technical_trend_label(close, sma20, sma50),
            "status": _status_from_score(trend_score),
            "score": trend_score,
            "detail": "Close price compared with SMA 20 and SMA 50 from price features.",
        }
    )

    momentum_return = None
    if close is not None and previous_5 and _float_or_none(previous_5.get("close")):
        momentum_return = (close / float(previous_5["close"])) - 1
    momentum_score = _bounded_score(momentum_return)
    drivers.append(
        {
            "key": "momentum",
            "label": USER_FACING_DRIVER_LABELS["momentum"],
            "value": _momentum_label(momentum_return),
            "status": _status_from_score(momentum_score),
            "score": momentum_score,
            "raw_value": momentum_return,
            "detail": "Five-session price movement from latest available feature history.",
        }
    )

    volume_ratio = volume / average_volume if volume is not None and average_volume else None
    volume_score = _bounded_score((volume_ratio - 1) / 2 if volume_ratio is not None else None)
    drivers.append(
        {
            "key": "volume",
            "label": USER_FACING_DRIVER_LABELS["volume"],
            "value": _volume_label(volume_ratio),
            "status": "neutral" if volume_ratio is None else "positive" if volume_ratio >= 1 else "neutral",
            "score": abs(volume_score),
            "raw_value": volume_ratio,
            "detail": "Latest volume compared with the recent 20-row average.",
        }
    )

    sentiment_score = _float_or_none(nlp_summary.get("sentiment_mean"))
    drivers.append(
        {
            "key": "sentiment",
            "label": USER_FACING_DRIVER_LABELS["sentiment"],
            "value": sentiment_label(sentiment_score),
            "status": signed_status(sentiment_score),
            "score": abs(_bounded_score(sentiment_score)),
            "raw_value": sentiment_score,
            "detail": "Aggregated NLP sentiment from matched news rows.",
        }
    )

    volatility = _return_volatility(history[-21:])
    volatility_score = min((volatility or 0) / 0.08, 1.0)
    drivers.append(
        {
            "key": "volatility",
            "label": USER_FACING_DRIVER_LABELS["volatility"],
            "value": _volatility_label(volatility),
            "status": "negative" if volatility_score > 0.65 else "neutral",
            "score": volatility_score,
            "raw_value": volatility,
            "detail": "Recent close-to-close volatility from latest price history.",
        }
    )

    confidence = _float_or_none(prediction.get("confidence")) if prediction.get("status") == "ok" else None
    drivers.append(
        {
            "key": "model",
            "label": USER_FACING_DRIVER_LABELS["model"],
            "value": _confidence_label(confidence),
            "status": "positive" if (confidence or 0) >= 0.5 else "neutral",
            "score": confidence or 0.0,
            "raw_value": confidence,
            "detail": "Distance of model probability from neutral, based on the trained artifact.",
        }
    )

    return {
        "status": "ok" if history or prediction.get("status") == "ok" else "empty",
        "ticker": cleaned,
        "date": prediction.get("date") or _date_text(latest.get("date")),
        "sector": prediction.get("sector") or profile.get("sector") or "UNKNOWN",
        "prediction": prediction if prediction.get("status") == "ok" else None,
        "drivers": drivers,
        "summary": _driver_summary(cleaned, prediction, nlp_summary, drivers),
    }


def load_price_feature_history(
    ticker: str,
    path: str | Path = DEFAULT_PRICE_FEATURES_PATH,
    *,
    limit: int = 260,
) -> list[dict[str, Any]]:
    """Load local Parquet price features for dashboard charts."""

    data_path = Path(path)
    if not data_path.exists():
        return []

    frame = _read_tabular_file(data_path)
    frame = frame[frame["ticker"].astype(str).str.upper() == ticker.upper()].copy()
    if frame.empty:
        return []
    frame = frame.sort_values("date").tail(limit)

    wanted_columns = [
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "SMA_20",
        "SMA_50",
        "SMA_200",
        "RSI",
        "MACD",
        "BB_upper",
        "BB_lower",
    ]
    existing_columns = [column for column in wanted_columns if column in frame.columns]
    return [
        {
            column: _date_text(value) if column == "date" else _float_or_none(value)
            for column, value in row.items()
        }
        for row in frame[existing_columns].to_dict("records")
    ]


def load_recent_news_rows(
    ticker: str | None,
    path: str | Path = DEFAULT_NEWS_PATH,
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Load recent ticker-matched news rows with NLP sentiment when available."""

    data_path = Path(path)
    if not data_path.exists():
        return []

    frame = _read_tabular_file(data_path)
    frame["date"] = _require_pandas().to_datetime(frame["date"], errors="coerce").dt.normalize()
    if "image_url" not in frame.columns:
        frame["image_url"] = None
    if "sentiment_score" not in frame.columns:
        frame["sentiment_score"] = None
    frame = _merge_news_sentiment(frame)
    if ticker:
        frame = frame[frame["ticker"].astype(str).str.upper() == ticker.upper()].copy()
    if frame.empty:
        return []
    frame = frame.sort_values("date", ascending=False).head(limit)
    return [
        {
            "date": _date_text(row.get("date")),
            "title": row.get("title") or "",
            "summary": row.get("summary") or "",
            "url": row.get("url") or "",
            "source": row.get("source") or "",
            "ticker": row.get("ticker") or ticker or "",
            "sentiment_score": _news_sentiment_score(row),
            "sentiment_label": sentiment_label(_news_sentiment_score(row)),
            "image_url": row.get("image_url") or None,
        }
        for row in frame.to_dict("records")
    ]


def load_latest_nlp_summary(
    ticker: str,
    path: str | Path = DEFAULT_NLP_FEATURES_PATH,
) -> dict[str, Any]:
    """Load latest aggregated NLP feature summary for one ticker."""

    data_path = Path(path)
    if not data_path.exists():
        return {}

    frame = _read_tabular_file(data_path)
    frame = frame[frame["ticker"].astype(str).str.upper() == ticker.upper()].copy()
    if frame.empty:
        return {}
    row = frame.sort_values("date").iloc[-1].to_dict()
    news_rows = load_recent_news_rows(ticker, limit=50)
    sentiment_score = _float_or_none(row.get("sentiment_mean"))
    return {
        "date": _date_text(row.get("date")),
        "sentiment_mean": sentiment_score,
        "sentiment_std": _float_or_none(row.get("sentiment_std")),
        "news_count": _int_or_none(row.get("news_count")),
        "sentiment_momentum": _float_or_none(row.get("sentiment_momentum")),
        "overall_sentiment": sentiment_label(sentiment_score),
        "latest_news_timestamp": news_rows[0]["date"] if news_rows else None,
        "top_positive_headline": _top_headline(news_rows, positive=True),
        "top_negative_headline": _top_headline(news_rows, positive=False),
        "main_theme": _main_news_theme(news_rows),
        "summary_text": _sentiment_summary_text(ticker, sentiment_score, news_rows),
    }


def prediction_label(predicted_direction: int | None) -> str:
    """Human-readable direction label."""

    if predicted_direction == 1:
        return "Up"
    if predicted_direction == 0:
        return "Down"
    return "Unknown"


def sentiment_label(score: float | None) -> str:
    """Map a real sentiment score into a readable label."""

    if score is None:
        return "Unknown"
    if score > 0.05:
        return "Positive"
    if score < -0.05:
        return "Negative"
    return "Neutral"


def signed_status(value: float | None) -> str:
    if value is None:
        return "neutral"
    if value > 0.05:
        return "positive"
    if value < -0.05:
        return "negative"
    return "neutral"


def _watchlist_prediction_direction(prediction: dict[str, Any]) -> str:
    predicted_direction = prediction.get("predicted_direction")
    predicted_return = _float_or_none(prediction.get("predicted_return"))
    if predicted_direction == 1:
        return "UP"
    if predicted_direction == 0:
        return "DOWN"
    if predicted_return is not None and predicted_return > 0.001:
        return "UP"
    if predicted_return is not None and predicted_return < -0.001:
        return "DOWN"
    return "NEUTRAL"


def _market_bias(bullish_count: int, prediction_count: int) -> str:
    if not prediction_count:
        return "neutral"
    ratio = bullish_count / prediction_count
    if ratio >= 0.58:
        return "bullish"
    if ratio <= 0.42:
        return "bearish"
    return "neutral"


def _model_narrative(comparison: dict[str, Any]) -> str:
    accuracy = _float_or_none(comparison.get("nlp_direction_classifier_accuracy"))
    improvement = _float_or_none(comparison.get("mape_improvement_pct"))
    if accuracy is not None and accuracy >= 0.53:
        return "Direction classifier is providing a stronger signal than raw return sign in this run."
    if improvement is not None and improvement > 0:
        return "NLP features improved the return error in the latest evaluation run."
    return "Model performance is shown from the latest local evaluation report."


def _dataset_stats(path: str | Path) -> dict[str, int]:
    data_path = Path(path)
    if not data_path.exists():
        return {"rows": 0, "stocks": 0}
    try:
        pd = _require_pandas()
        frame = pd.read_parquet(data_path, columns=["ticker"])
    except Exception:
        return {"rows": 0, "stocks": 0}
    return {"rows": int(len(frame)), "stocks": int(frame["ticker"].nunique())}


def _news_stats(path: str | Path) -> dict[str, Any]:
    data_path = Path(path)
    if not data_path.exists():
        return {"rows": 0, "latest_date": None}
    try:
        pd = _require_pandas()
        frame = pd.read_parquet(data_path, columns=["date"])
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    except Exception:
        return {"rows": 0, "latest_date": None}
    return {
        "rows": int(len(frame)),
        "latest_date": _date_text(frame["date"].max()) if not frame.empty else None,
    }


def _latest_date_from_table(path: str | Path) -> str | None:
    data_path = Path(path)
    if not data_path.exists():
        return None
    try:
        pd = _require_pandas()
        if data_path.suffix.lower() == ".csv":
            frame = pd.read_csv(data_path, usecols=["date"])
        else:
            frame = pd.read_parquet(data_path, columns=["date"])
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    except Exception:
        return None
    if frame.empty:
        return None
    return _date_text(frame["date"].max())


def _mean_or_none(values: list[Any]) -> float | None:
    numbers = [_float_or_none(value) for value in values]
    valid = [value for value in numbers if value is not None]
    if not valid:
        return None
    return statistics.fmean(valid)


def _relative_position(left: float | None, right: float | None) -> float | None:
    if left is None or right is None or right == 0:
        return None
    return (left / right) - 1


def _bounded_score(value: float | None) -> float:
    if value is None:
        return 0.0
    return max(-1.0, min(1.0, float(value) / 0.08))


def _status_from_score(score: float) -> str:
    if score > 0.1:
        return "positive"
    if score < -0.1:
        return "negative"
    return "neutral"


def _technical_trend_label(close: float | None, sma20: float | None, sma50: float | None) -> str:
    if close is None:
        return "No price signal"
    if sma20 and sma50 and close > sma20 and close > sma50:
        return "Above key moving averages"
    if sma50 and close < sma50:
        return "Below SMA 50"
    if sma20 and close < sma20:
        return "Below SMA 20"
    return "Mixed trend"


def _momentum_label(momentum_return: float | None) -> str:
    if momentum_return is None:
        return "No recent momentum"
    if momentum_return > 0.03:
        return "Strong bullish"
    if momentum_return > 0.005:
        return "Mild bullish"
    if momentum_return < -0.03:
        return "Strong bearish"
    if momentum_return < -0.005:
        return "Mild bearish"
    return "Sideways"


def _volume_label(volume_ratio: float | None) -> str:
    if volume_ratio is None:
        return "No volume signal"
    if volume_ratio >= 1.5:
        return "High activity"
    if volume_ratio >= 1.05:
        return "Moderate activity"
    if volume_ratio <= 0.65:
        return "Quiet trading"
    return "Normal activity"


def _volatility_label(volatility: float | None) -> str:
    if volatility is None:
        return "No volatility signal"
    if volatility >= 0.05:
        return "High"
    if volatility >= 0.025:
        return "Moderate"
    return "Low"


def _confidence_label(confidence: float | None) -> str:
    if confidence is None:
        return "No model signal"
    if confidence >= 0.65:
        return "High"
    if confidence >= 0.35:
        return "Moderate"
    return "Low"


def _return_volatility(rows: list[dict[str, Any]]) -> float | None:
    closes = [_float_or_none(row.get("close")) for row in rows]
    valid = [close for close in closes if close is not None and close > 0]
    returns = [
        (current / previous) - 1
        for previous, current in zip(valid, valid[1:], strict=False)
        if previous > 0
    ]
    if len(returns) < 2:
        return None
    return statistics.stdev(returns)


def _driver_summary(
    ticker: str,
    prediction: dict[str, Any],
    nlp_summary: dict[str, Any],
    drivers: list[dict[str, Any]],
) -> str:
    direction = "up" if prediction.get("predicted_direction") == 1 else "down"
    confidence = _confidence_label(_float_or_none(prediction.get("confidence")))
    sentiment = nlp_summary.get("overall_sentiment") or "Unknown"
    strongest = max(drivers, key=lambda row: abs(float(row.get("score") or 0)), default={})
    if prediction.get("status") != "ok":
        return f"{ticker} prediction is not available from the current model artifact."
    return (
        f"{ticker} is currently modeled {direction} with {confidence.lower()} confidence. "
        f"The strongest available driver is {strongest.get('label', 'market context')}, "
        f"while latest news sentiment is {str(sentiment).lower()}."
    )


def _top_headline(rows: list[dict[str, Any]], *, positive: bool) -> str | None:
    scored = [
        row
        for row in rows
        if _float_or_none(row.get("sentiment_score")) is not None and row.get("title")
    ]
    if not scored:
        return rows[0]["title"] if rows else None

    def score(row: dict[str, Any]) -> float:
        return _float_or_none(row.get("sentiment_score")) or 0.0

    selected = max(scored, key=score) if positive else min(scored, key=score)
    return selected.get("title")


def _main_news_theme(rows: list[dict[str, Any]]) -> str | None:
    if not rows:
        return None
    sources = [row.get("source") for row in rows if row.get("source")]
    tickers = [row.get("ticker") for row in rows if row.get("ticker")]
    source_text = statistics.mode(sources) if sources else "market news"
    ticker_text = statistics.mode(tickers) if tickers else "IDX market"
    return f"{ticker_text} coverage from {source_text}"


def _sentiment_summary_text(
    ticker: str,
    sentiment_score: float | None,
    rows: list[dict[str, Any]],
) -> str:
    if not rows:
        return f"No recent news rows are available for {ticker} in the current news artifact."
    label = sentiment_label(sentiment_score).lower()
    return (
        f"Recent news around {ticker} is mostly {label}, based on "
        f"{len(rows)} matched article rows in the local news artifact."
    )


def build_investment_simulation(
    price_history: list[dict[str, Any]],
    *,
    amount: float,
    entry_date: str,
    exit_date: str,
    probability_up: float | None = None,
) -> dict[str, Any]:
    """Build historical/projected portfolio value rows for one stock.

    The projection is a deterministic scenario based on recent realized returns and the
    latest direction probability. It is a planning visualization, not financial advice.
    """

    if amount <= 0:
        raise ValueError("amount must be greater than zero")

    entry = date.fromisoformat(entry_date)
    exit_ = date.fromisoformat(exit_date)
    if exit_ < entry:
        raise ValueError("exit_date must be greater than or equal to entry_date")

    rows = [
        row
        for row in sorted(price_history, key=lambda item: item["date"])
        if row.get("close") is not None
    ]
    if not rows:
        raise ValueError("price_history must contain at least one close price")

    entry_index = _first_index_on_or_after(rows, entry)
    if entry_index is None:
        raise ValueError("entry_date is after the latest available price")

    entry_row = rows[entry_index]
    entry_close = float(entry_row["close"])
    shares = amount / entry_close
    actual_rows = _actual_value_rows(rows[entry_index:], shares, exit_)
    if not actual_rows:
        raise ValueError("no price rows are available for the selected date range")

    projection_rows = []
    latest_row = actual_rows[-1]
    latest_date = date.fromisoformat(latest_row["date"])
    if exit_ > latest_date:
        projection_rows = _project_value_rows(
            historical_rows=rows,
            shares=shares,
            start_date=latest_date + timedelta(days=1),
            exit_date=exit_,
            probability_up=probability_up,
        )

    all_rows = actual_rows + projection_rows
    exit_row = all_rows[-1]
    return {
        "entry_date": entry_row["date"],
        "requested_exit_date": exit_date,
        "entry_close": entry_close,
        "shares": shares,
        "initial_amount": amount,
        "exit_value": exit_row["value"],
        "profit_loss": exit_row["value"] - amount,
        "profit_loss_pct": (exit_row["value"] / amount) - 1,
        "mode": "projected" if projection_rows else "historical",
        "rows": all_rows,
    }


def load_stock_options(client: Neo4jClient) -> list[dict[str, Any]]:
    """Load stock selector options from Neo4j."""

    return client.execute_read(
        """
        MATCH (stock:Stock)
        OPTIONAL MATCH (stock)-[:IN_SECTOR]->(sector:Sector)
        OPTIONAL MATCH (stock)-[:HAS_PRICE]->(price:PricePoint {source: 'yfinance', interval: '1d'})
        RETURN stock.ticker AS ticker,
               stock.name AS name,
               coalesce(sector.name, 'UNKNOWN') AS sector,
               coalesce(stock.universe_rank, 1000000) AS universe_rank,
               count(price) AS price_points,
               count(price) > 0 AS has_price
        ORDER BY has_price DESC, universe_rank, ticker
        """
    )


def load_price_history(client: Neo4jClient, ticker: str) -> list[dict[str, Any]]:
    """Load price history for a selected ticker."""

    rows = client.execute_read(
        """
        MATCH (:Stock {ticker: $ticker})-[:HAS_PRICE]->(price:PricePoint)
        WHERE price.source = 'yfinance' AND price.interval = '1d'
        RETURN toString(price.date) AS date,
               price.open AS open,
               price.high AS high,
               price.low AS low,
               price.close AS close,
               price.volume AS volume
        ORDER BY date
        """,
        {"ticker": ticker},
    )
    return [
        {
            "date": row["date"],
            "open": _float_or_none(row.get("open")),
            "high": _float_or_none(row.get("high")),
            "low": _float_or_none(row.get("low")),
            "close": _float_or_none(row.get("close")),
            "volume": _int_or_none(row.get("volume")),
        }
        for row in rows
    ]


def load_correlations(client: Neo4jClient, ticker: str) -> list[dict[str, Any]]:
    """Load correlated peers for a selected ticker."""

    rows = client.execute_read(
        """
        MATCH (stock:Stock {ticker: $ticker})-[relationship:CORRELATED_WITH]-(peer:Stock)
        RETURN peer.ticker AS peer_ticker,
               peer.name AS peer_name,
               relationship.coefficient AS coefficient,
               relationship.observations AS observations,
               toString(relationship.first_date) AS first_date,
               toString(relationship.last_date) AS last_date
        ORDER BY relationship.abs_coefficient DESC, peer.ticker
        """,
        {"ticker": ticker},
    )
    return [
        {
            "peer_ticker": row["peer_ticker"],
            "peer_name": row["peer_name"],
            "coefficient": _float_or_none(row.get("coefficient")),
            "observations": _int_or_none(row.get("observations")),
            "first_date": row.get("first_date"),
            "last_date": row.get("last_date"),
        }
        for row in rows
    ]


def load_sector_counts(client: Neo4jClient) -> list[dict[str, Any]]:
    """Load stock counts by sector."""

    return client.execute_read(
        """
        MATCH (stock:Stock)-[:IN_SECTOR]->(sector:Sector)
        RETURN sector.name AS sector,
               count(stock) AS stocks
        ORDER BY stocks DESC, sector
        """
    )


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None

    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed:
        return None
    return parsed


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None

    parsed = _float_or_none(value)
    if parsed is None:
        return None
    return int(parsed)


def _date_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)[:10]


def _market_time_text(value: Any, *, interval: str) -> str:
    if value is None:
        return ""

    text = str(value)
    if interval.endswith("d") or interval.endswith("wk") or interval.endswith("mo"):
        return text[:10]
    return text.replace(" ", "T")


def _ticker_from_symbol(symbol: str) -> str:
    normalized = symbol.upper().strip()
    if normalized.endswith(".JK"):
        return normalized.removesuffix(".JK")
    return normalized


def _filter_price_period(frame: Any, period: str) -> Any:
    if frame.empty or period == "max":
        return frame

    latest = frame["date"].max()
    pd = _require_pandas()
    if period == "ytd":
        start = pd.Timestamp(year=latest.year, month=1, day=1)
    elif period.endswith("mo"):
        start = latest - pd.DateOffset(months=int(period.removesuffix("mo")))
    elif period.endswith("y"):
        start = latest - pd.DateOffset(years=int(period.removesuffix("y")))
    elif period.endswith("d"):
        start = latest - pd.Timedelta(days=int(period.removesuffix("d")))
    else:
        return frame
    return frame[frame["date"] >= start]


def _news_sentiment_score(row: dict[str, Any]) -> float | None:
    article_score = _float_or_none(row.get("sentiment_score"))
    if article_score is not None:
        return article_score
    return _float_or_none(row.get("sentiment_mean"))


def _read_tabular_file(path: Path) -> Any:
    pd = _require_pandas()

    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    return pd.read_parquet(path)


def _merge_news_sentiment(news_frame: Any) -> Any:
    pd = _require_pandas()
    nlp_path = DEFAULT_NLP_FEATURES_PATH
    if not nlp_path.exists() or news_frame.empty:
        news_frame["sentiment_mean"] = None
        return news_frame

    nlp_frame = pd.read_parquet(nlp_path)
    if nlp_frame.empty:
        news_frame["sentiment_mean"] = None
        return news_frame

    nlp_frame = nlp_frame.copy()
    nlp_frame["date"] = pd.to_datetime(nlp_frame["date"], errors="coerce").dt.normalize()
    sentiment_columns = ["ticker", "date", "sentiment_mean"]
    return news_frame.merge(nlp_frame[sentiment_columns], on=["ticker", "date"], how="left")


def _read_profile_cache(path: str | Path = DEFAULT_COMPANY_PROFILE_CACHE_PATH) -> dict[str, dict[str, Any]]:
    cache_path = Path(path)
    if not cache_path.exists():
        return {}
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {str(key).upper(): value for key, value in payload.items() if isinstance(value, dict)}


def _write_profile_cache(
    payload: dict[str, dict[str, Any]],
    path: str | Path = DEFAULT_COMPANY_PROFILE_CACHE_PATH,
) -> None:
    cache_path = Path(path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _resolve_price_history_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.exists():
        return candidate
    if candidate == DEFAULT_PRICE_HISTORY_PATH and LEGACY_PRICE_HISTORY_PATH.exists():
        return LEGACY_PRICE_HISTORY_PATH
    return candidate


def _with_logo_candidates(profile: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(profile)
    candidates = _logo_candidates(enriched)
    enriched["logo_candidates"] = candidates
    if not enriched.get("logo_url") and candidates:
        enriched["logo_url"] = candidates[0]
        enriched["logo_source"] = enriched.get("logo_source") or "company website icon"
    return enriched


def _logo_candidates(profile: dict[str, Any]) -> list[str]:
    candidates: list[str] = []

    def add(value: Any) -> None:
        url = _http_url(value)
        if url and url not in candidates:
            candidates.append(url)

    add(profile.get("logo_url"))
    website = _http_url(profile.get("website"))
    if website:
        add(urljoin(website, "/favicon.ico"))
        hostname = urlparse(website).hostname
        if hostname:
            add(f"https://icons.duckduckgo.com/ip3/{hostname}.ico")
        add(f"https://www.google.com/s2/favicons?domain_url={quote(website, safe='')}&sz=128")

    for candidate in profile.get("logo_candidates") or []:
        add(candidate)

    return candidates


def _fetch_yfinance_profile(symbol: str) -> dict[str, Any]:
    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError(
            "yfinance is not installed. Run: .venv\\Scripts\\python.exe -m pip install -e \".[data]\""
        ) from exc

    info = yf.Ticker(symbol).get_info()
    website = _string_or_empty(info.get("website"))
    logo_url = _http_url(info.get("logo_url"))
    logo_source = "yfinance.logo_url" if logo_url else None
    if not logo_url and website:
        logo_url = _discover_website_logo(website)
        logo_source = "company website icon" if logo_url else None

    return {
        "checked": True,
        "name": _string_or_empty(info.get("longName") or info.get("shortName")) or None,
        "sector": _string_or_empty(info.get("sector")) or None,
        "industry": _string_or_empty(info.get("industry")) or None,
        "website": website,
        "logo_url": logo_url,
        "logo_source": logo_source,
    }


def _discover_website_logo(website: str) -> str | None:
    request = Request(website, headers={"User-Agent": "IHSG-Dashboard-CompanyProfile/0.1"})
    try:
        with urlopen(request, timeout=8) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            html = response.read(250_000).decode(charset, errors="replace")
    except Exception:
        return urljoin(website, "/favicon.ico")

    parser = IconLinkParser(base_url=website)
    parser.feed(html)
    parser.close()
    return parser.icon_url or urljoin(website, "/favicon.ico")


class IconLinkParser(HTMLParser):
    """Extract a real icon URL advertised by a company website."""

    def __init__(self, *, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.icon_url: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.icon_url or tag.lower() != "link":
            return
        attributes = {key.lower(): value or "" for key, value in attrs}
        rel = attributes.get("rel", "").lower()
        if "icon" not in rel:
            return
        href = attributes.get("href", "").strip()
        icon_url = urljoin(self.base_url, href)
        if _http_url(icon_url):
            self.icon_url = icon_url


def _http_url(value: Any) -> str | None:
    text = _string_or_empty(value)
    if text.startswith("http://") or text.startswith("https://"):
        return text
    return None


def _string_or_empty(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _prediction_confidence(predicted_return: float, volatility: float) -> float:
    denominator = abs(volatility) if volatility else 0.02
    return min(abs(predicted_return) / denominator, 1.0)


def _require_pandas() -> Any:
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError(
            "pandas is not installed. Run: .venv\\Scripts\\python.exe -m pip install -e \".[data]\""
        ) from exc
    return pd


def _first_index_on_or_after(rows: list[dict[str, Any]], target_date: date) -> int | None:
    for index, row in enumerate(rows):
        if date.fromisoformat(row["date"]) >= target_date:
            return index

    return None


def _actual_value_rows(
    rows: list[dict[str, Any]],
    shares: float,
    exit_date: date,
) -> list[dict[str, Any]]:
    value_rows = []
    for row in rows:
        current_date = date.fromisoformat(row["date"])
        if current_date > exit_date:
            break

        close = float(row["close"])
        value = shares * close
        value_rows.append(
            {
                "date": row["date"],
                "close": close,
                "value": value,
                "lower_value": value,
                "upper_value": value,
                "kind": "historical",
            }
        )

    return value_rows


def _project_value_rows(
    *,
    historical_rows: list[dict[str, Any]],
    shares: float,
    start_date: date,
    exit_date: date,
    probability_up: float | None,
) -> list[dict[str, Any]]:
    closes = [float(row["close"]) for row in historical_rows if row.get("close") is not None]
    recent_closes = closes[-21:]
    returns = [
        (current / previous) - 1
        for previous, current in zip(recent_closes, recent_closes[1:], strict=False)
        if previous > 0
    ]
    average_return = statistics.fmean(returns) if returns else 0.0
    volatility = statistics.stdev(returns) if len(returns) > 1 else 0.0
    probability = 0.5 if probability_up is None else min(max(probability_up, 0.0), 1.0)
    expected_daily_return = average_return + ((probability - 0.5) * volatility)
    expected_daily_return = min(max(expected_daily_return, -0.1), 0.1)

    projected_rows = []
    projected_close = closes[-1]
    current_date = start_date
    horizon = 0
    while current_date <= exit_date:
        if current_date.weekday() >= 5:
            current_date += timedelta(days=1)
            continue

        horizon += 1
        projected_close *= 1 + expected_daily_return
        uncertainty = volatility * (horizon**0.5)
        value = shares * projected_close
        projected_rows.append(
            {
                "date": current_date.isoformat(),
                "close": projected_close,
                "value": value,
                "lower_value": value * max(0.01, 1 - uncertainty),
                "upper_value": value * (1 + uncertainty),
                "kind": "projected",
            }
        )
        current_date += timedelta(days=1)

    return projected_rows
