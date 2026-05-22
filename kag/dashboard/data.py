"""Data access and formatting helpers for the Streamlit dashboard."""

from __future__ import annotations

import csv
from datetime import date
from datetime import timedelta
import json
from pathlib import Path
import statistics
from typing import Any

from kag.graph.client import Neo4jClient


DEFAULT_PREDICTIONS_PATH = Path("data/processed/latest_direction_predictions.csv")
DEFAULT_METRICS_PATH = Path("models/direction_model_metrics.json")


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


def prediction_label(predicted_direction: int | None) -> str:
    """Human-readable direction label."""

    if predicted_direction == 1:
        return "Up"
    if predicted_direction == 0:
        return "Down"
    return "Unknown"


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

    return float(value)


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None

    return int(float(value))


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
