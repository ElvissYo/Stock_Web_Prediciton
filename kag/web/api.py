"""HTTP API for the custom non-Streamlit market dashboard."""

from __future__ import annotations

from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from kag.dashboard.data import (
    build_investment_simulation,
    generate_latest_global_prediction,
    load_global_prediction_rows,
    load_company_profile,
    load_last_updated,
    load_latest_nlp_summary,
    load_local_price_ohlcv,
    load_market_movers,
    load_market_overview,
    load_market_symbols,
    load_market_watchlist,
    load_model_comparison,
    load_model_performance_summary,
    load_price_feature_history,
    load_prediction_drivers,
    load_recent_news_rows,
    load_top_prediction_rankings,
    load_yfinance_ohlcv,
)


ALLOWED_PERIODS = {"1d", "5d", "1mo", "3mo", "6mo", "ytd", "1y", "2y", "5y", "10y", "20y", "max"}
ALLOWED_INTERVALS = {"1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "5d", "1wk", "1mo"}


def create_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    static_dir: str | Path = "web",
) -> ThreadingHTTPServer:
    """Create a local HTTP server for static assets and JSON API routes."""

    handler = partial(DashboardRequestHandler, directory=str(Path(static_dir).resolve()))
    return ThreadingHTTPServer((host, port), handler)


class DashboardRequestHandler(SimpleHTTPRequestHandler):
    """Serve static dashboard files and real-data JSON endpoints."""

    server_version = "IHSGDashboardHTTP/0.1"

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self._handle_api(parsed.path, parse_qs(parsed.query))
            return
        if parsed.path == "/":
            self.path = "/index.html"
        super().do_GET()

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _handle_api(self, path: str, query: dict[str, list[str]]) -> None:
        try:
            status, payload = api_response(path, query)
        except Exception as exc:
            status = HTTPStatus.INTERNAL_SERVER_ERROR
            payload = {"status": "error", "message": str(exc)}
        self._send_json(payload, status=status)

    def _send_json(self, payload: dict[str, Any], *, status: HTTPStatus) -> None:
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def api_response(path: str, query: dict[str, list[str]]) -> tuple[HTTPStatus, dict[str, Any]]:
    """Return a JSON-serializable API payload for one route."""

    if path == "/api/health":
        return HTTPStatus.OK, {"status": "ok"}

    if path == "/api/market/symbols":
        limit = _query_int(query, "limit", 100)
        return HTTPStatus.OK, {
            "status": "ok",
            "symbols": load_market_symbols(limit=limit),
        }

    if path == "/api/stocks/metadata":
        limit = _query_int(query, "limit", 100)
        return HTTPStatus.OK, {
            "status": "ok",
            "source": "data/company_metadata.json",
            "stocks": [row for row in load_market_symbols(limit=limit) if row["ticker"] != "IHSG"],
        }

    if path == "/api/stocks":
        limit = _query_int(query, "limit", 100)
        watchlist = load_market_watchlist(limit=limit)
        return HTTPStatus.OK, {
            "status": "ok" if watchlist["stocks"] else "empty",
            **watchlist,
        }

    if path == "/api/market/overview":
        return HTTPStatus.OK, load_market_overview()

    if path == "/api/market/movers":
        limit = _query_int(query, "limit", 10)
        movers = load_market_movers(limit=limit)
        return HTTPStatus.OK, {
            "status": "ok" if movers["available_tickers"] else "empty",
            **movers,
        }

    if path == "/api/market/profile":
        ticker = _query_value(query, "ticker", "BBCA")
        return HTTPStatus.OK, {
            "status": "ok",
            "profile": load_company_profile(ticker),
        }

    if path == "/api/market/candles":
        symbol = _query_value(query, "symbol", "^JKSE")
        period = _query_value(query, "period", "1y")
        interval = _query_value(query, "interval", "1d")
        if period not in ALLOWED_PERIODS:
            return HTTPStatus.BAD_REQUEST, {"status": "error", "message": "Unsupported period"}
        if interval not in ALLOWED_INTERVALS:
            return HTTPStatus.BAD_REQUEST, {"status": "error", "message": "Unsupported interval"}
        if interval == "1d":
            try:
                candles = load_local_price_ohlcv(symbol, period=period, interval=interval)
            except Exception:
                candles = []
            if not candles:
                candles = load_yfinance_ohlcv(symbol, period=period, interval=interval)
        else:
            candles = load_yfinance_ohlcv(symbol, period=period, interval=interval)
        return HTTPStatus.OK, {
            "status": "ok",
            "symbol": symbol,
            "period": period,
            "interval": interval,
            "source": candles[0].get("source") if candles else "Yahoo Finance / yfinance",
            "candles": candles,
        }

    if path == "/api/chart":
        ticker = _query_value(query, "ticker", "IHSG").upper()
        period = _query_value(query, "range", _query_value(query, "period", "1y"))
        interval = _query_value(query, "interval", "1d")
        symbol = "^JKSE" if ticker in {"IHSG", "^JKSE"} else _symbol_for_ticker(ticker)
        return api_response(
            "/api/market/candles",
            {
                "symbol": [symbol],
                "period": [_range_to_period(period)],
                "interval": [interval],
            },
        )

    if path == "/api/predictions":
        rows = load_global_prediction_rows()
        return HTTPStatus.OK, {
            "status": "ok",
            "source": "data/processed/global_model_predictions.parquet",
            "predictions": rows,
        }

    if path == "/api/predictions/top":
        limit = _query_int(query, "limit", 10)
        return HTTPStatus.OK, load_top_prediction_rankings(limit=limit)

    if path == "/api/prediction":
        ticker = _query_value(query, "ticker", "BBCA").upper()
        payload = generate_latest_global_prediction(ticker)
        status = (
            HTTPStatus.OK
            if payload.get("status") in {"ok", "technical_snapshot"}
            else HTTPStatus.NOT_FOUND
        )
        return status, payload

    if path == "/api/prediction-drivers":
        ticker = _query_value(query, "ticker", "BBCA").upper()
        return HTTPStatus.OK, load_prediction_drivers(ticker)

    if path == "/api/projection":
        ticker = _query_value(query, "ticker", "BBCA").upper().replace(".JK", "")
        if ticker in {"IHSG", "^JKSE"}:
            return HTTPStatus.BAD_REQUEST, {
                "status": "error",
                "message": "Projection requires a stock ticker, not IHSG.",
            }

        try:
            amount = _query_float(query, "amount")
        except ValueError as exc:
            return HTTPStatus.BAD_REQUEST, {"status": "error", "message": str(exc)}

        entry_date = _query_value(query, "entry_date", "")
        exit_date = _query_value(query, "exit_date", "")
        if not entry_date or not exit_date:
            return HTTPStatus.BAD_REQUEST, {
                "status": "error",
                "message": "entry_date and exit_date are required.",
            }

        symbol = _symbol_for_ticker(ticker)
        candles = load_local_price_ohlcv(symbol, period="max", interval="1d")
        if not candles:
            candles = load_yfinance_ohlcv(symbol, period="max", interval="1d")

        prediction = generate_latest_global_prediction(ticker)
        try:
            projection = build_investment_simulation(
                candles,
                amount=amount,
                entry_date=entry_date,
                exit_date=exit_date,
                probability_up=_probability_up_from_prediction(prediction),
            )
        except ValueError as exc:
            return HTTPStatus.BAD_REQUEST, {"status": "error", "message": str(exc)}

        return HTTPStatus.OK, {
            "status": "ok",
            "ticker": ticker,
            "symbol": symbol,
            "projection": projection,
            "prediction": prediction if prediction.get("status") == "ok" else None,
        }

    if path == "/api/price-features":
        ticker = _query_value(query, "ticker", "BBCA").upper()
        return HTTPStatus.OK, {
            "status": "ok",
            "ticker": ticker,
            "source": "data/processed/price_features.parquet",
            "history": load_price_feature_history(ticker),
        }

    if path == "/api/news":
        ticker = _optional_query_value(query, "ticker")
        limit = _query_int(query, "limit", 12)
        news = load_recent_news_rows(ticker.upper() if ticker else None, limit=limit)
        return HTTPStatus.OK, {
            "status": "ok",
            "source": "data/news_raw.parquet",
            "sentiment_source": "data/nlp_features.parquet",
            "context_message": _news_context_message(ticker.upper() if ticker else None, news),
            "news": news,
        }

    if path == "/api/nlp-summary":
        ticker = _query_value(query, "ticker", "BBCA").upper()
        return HTTPStatus.OK, {
            "status": "ok",
            "ticker": ticker,
            "source": "data/nlp_features.parquet",
            "summary": load_latest_nlp_summary(ticker),
        }

    if path == "/api/metrics":
        payload = load_model_comparison()
        return HTTPStatus.OK, {
            "status": "ok" if payload else "empty",
            "source": "reports/metrics.json",
            "metrics": payload,
        }

    if path == "/api/model/performance":
        return HTTPStatus.OK, load_model_performance_summary()

    if path == "/api/last-updated":
        return HTTPStatus.OK, {"status": "ok", **load_last_updated()}

    if path == "/api/artifacts":
        return HTTPStatus.OK, {"status": "ok", "artifacts": artifact_status()}

    return HTTPStatus.NOT_FOUND, {"status": "error", "message": "Unknown API route"}


def artifact_status() -> list[dict[str, Any]]:
    """Return existence and file sizes for real pipeline artifacts."""

    paths = [
        "data/prices_full_top100.parquet",
        "data/prices_20y_top100.parquet",
        "data/news_raw.parquet",
        "data/nlp_features.parquet",
        "data/processed/price_features.parquet",
        "data/final_dataset.parquet",
        "data/processed/global_model_predictions.parquet",
        "models/global_model_with_nlp.joblib",
        "reports/metrics.json",
        "reports/feature_importance.png",
    ]
    rows = []
    for raw_path in paths:
        path = Path(raw_path)
        rows.append(
            {
                "path": raw_path,
                "exists": path.exists(),
                "bytes": path.stat().st_size if path.exists() else None,
            }
        )
    return rows


def _query_value(query: dict[str, list[str]], name: str, default: str) -> str:
    values = query.get(name)
    if not values:
        return default
    value = values[0].strip()
    return value or default


def _optional_query_value(query: dict[str, list[str]], name: str) -> str | None:
    values = query.get(name)
    if not values:
        return None
    value = values[0].strip()
    return value or None


def _query_int(query: dict[str, list[str]], name: str, default: int) -> int:
    value = _query_value(query, name, str(default))
    try:
        return max(1, min(int(value), 100))
    except ValueError:
        return default


def _query_float(query: dict[str, list[str]], name: str) -> float:
    value = _query_value(query, name, "")
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number.") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be greater than zero.")
    return parsed


def _symbol_for_ticker(ticker: str) -> str:
    cleaned = ticker.upper().replace(".JK", "").strip()
    for row in load_market_symbols(limit=1000):
        if row["ticker"] == cleaned:
            return row["symbol"]
    return f"{cleaned}.JK"


def _probability_up_from_prediction(prediction: dict[str, Any]) -> float | None:
    if prediction.get("status") != "ok":
        return None
    confidence = _bounded_float(prediction.get("confidence"))
    if confidence is None:
        return None
    if prediction.get("predicted_direction") == 1:
        return 0.5 + confidence * 0.5
    if prediction.get("predicted_direction") == 0:
        return 0.5 - confidence * 0.5
    return None


def _news_context_message(ticker: str | None, rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "Using latest available market news"
    if ticker and any(row.get("scope") == "market" for row in rows):
        return "Showing recent market news when ticker-specific news is limited"
    if ticker:
        return "Using latest available market news"
    return "Using latest available market news"


def _bounded_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return min(max(parsed, 0.0), 1.0)


def _range_to_period(value: str) -> str:
    normalized = value.strip().lower()
    mapping = {
        "1d": "1d",
        "5d": "5d",
        "1m": "1mo",
        "1mo": "1mo",
        "3m": "3mo",
        "3mo": "3mo",
        "6m": "6mo",
        "6mo": "6mo",
        "ytd": "ytd",
        "1y": "1y",
        "5y": "5y",
        "all": "max",
        "max": "max",
    }
    return mapping.get(normalized, "1y")
