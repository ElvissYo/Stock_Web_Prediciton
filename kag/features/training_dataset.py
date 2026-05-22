"""Build supervised forecasting features from graph and price context."""

from __future__ import annotations

from collections import defaultdict
import csv
from dataclasses import asdict, dataclass
from dataclasses import field
from pathlib import Path
import statistics
from typing import Any, Iterable

from kag.graph.client import Neo4jClient


DEFAULT_CORRELATION_METHOD = "pearson_close_return"
AUTO_FEATURE_WINDOWS = (3, 5, 10, 20)


@dataclass(frozen=True)
class FeatureSourceRow:
    """Raw graph-backed input row used for feature engineering."""

    ticker: str
    date: str
    sector: str
    close: float
    volume: int | None
    correlated_peer_count: int
    correlation_avg_abs: float


@dataclass(frozen=True)
class TrainingFeatureRow:
    """One supervised training row for next-period stock return forecasting."""

    ticker: str
    date: str
    sector: str
    close: float
    volume: int | None
    return_1d: float
    return_5d: float
    rolling_mean_5d: float
    rolling_vol_5d: float
    rolling_mean_10d: float
    rolling_vol_10d: float
    sector_return_1d: float
    correlated_peer_count: int
    correlation_avg_abs: float
    target_next_return: float
    target_next_direction: int
    auto_features: dict[str, float | int | None] = field(default_factory=dict)

    def to_csv_row(self) -> dict[str, str | int | float | None]:
        row = asdict(self)
        auto_features = row.pop("auto_features")
        row.update(auto_features)
        return row


@dataclass(frozen=True)
class InferenceFeatureRow:
    """Latest feature row for prediction without future target labels."""

    ticker: str
    date: str
    sector: str
    close: float
    volume: int | None
    return_1d: float
    return_5d: float
    rolling_mean_5d: float
    rolling_vol_5d: float
    rolling_mean_10d: float
    rolling_vol_10d: float
    sector_return_1d: float
    correlated_peer_count: int
    correlation_avg_abs: float
    auto_features: dict[str, float | int | None] = field(default_factory=dict)

    def to_model_row(self) -> dict[str, str | int | float | None]:
        row = asdict(self)
        auto_features = row.pop("auto_features")
        row.update(auto_features)
        return row


def load_feature_source_rows(
    client: Neo4jClient,
    *,
    tickers: list[str] | None = None,
    price_source: str = "yfinance",
    interval: str = "1d",
    start: str | None = None,
    end: str | None = None,
    correlation_method: str = DEFAULT_CORRELATION_METHOD,
) -> list[FeatureSourceRow]:
    """Load price, sector, and correlation context from Neo4j."""

    normalized_tickers = [ticker.strip().upper().removesuffix(".JK") for ticker in tickers or []]
    rows = client.execute_read(
        """
        MATCH (stock:Stock)-[:HAS_PRICE]->(price:PricePoint)
        WHERE price.source = $price_source
          AND price.interval = $interval
          AND (size($tickers) = 0 OR stock.ticker IN $tickers)
          AND ($start IS NULL OR price.date >= date($start))
          AND ($end IS NULL OR price.date <= date($end))
          AND price.close IS NOT NULL
        OPTIONAL MATCH (stock)-[:IN_SECTOR]->(sector:Sector)
        OPTIONAL MATCH (stock)-[correlation:CORRELATED_WITH]-(peer:Stock)
        WHERE correlation.method = $correlation_method
          AND correlation.price_source = $price_source
          AND correlation.interval = $interval
        RETURN stock.ticker AS ticker,
               toString(price.date) AS date,
               coalesce(sector.name, 'UNKNOWN') AS sector,
               price.close AS close,
               price.volume AS volume,
               count(DISTINCT peer) AS correlated_peer_count,
               coalesce(avg(abs(correlation.coefficient)), 0.0) AS correlation_avg_abs
        ORDER BY ticker, date
        """,
        {
            "tickers": normalized_tickers,
            "price_source": price_source,
            "interval": interval,
            "start": start,
            "end": end,
            "correlation_method": correlation_method,
        },
    )

    return [_feature_source_row_from_neo4j(row) for row in rows]


def build_training_features(
    source_rows: Iterable[FeatureSourceRow],
    *,
    short_window: int = 5,
    long_window: int = 10,
    feature_windows: tuple[int, ...] = AUTO_FEATURE_WINDOWS,
) -> list[TrainingFeatureRow]:
    """Build next-period supervised features from graph-backed source rows."""

    _validate_windows(short_window, long_window, feature_windows)
    minimum_window = max(long_window, max(feature_windows))

    rows_by_ticker = _rows_by_ticker(source_rows)
    returns_by_ticker = _returns_by_ticker(rows_by_ticker)
    sector_returns = _sector_returns(rows_by_ticker, returns_by_ticker)

    feature_rows: list[TrainingFeatureRow] = []
    for ticker, rows in sorted(rows_by_ticker.items()):
        returns = returns_by_ticker[ticker]
        for index in range(minimum_window, len(rows) - 1):
            current = rows[index]
            next_row = rows[index + 1]
            if current.date not in returns:
                continue

            trailing_returns = [
                returns[rows[trailing_index].date]
                for trailing_index in range(index - long_window + 1, index + 1)
                if rows[trailing_index].date in returns
            ]
            if len(trailing_returns) < long_window:
                continue

            short_returns = trailing_returns[-short_window:]
            target_next_return = (next_row.close / current.close) - 1
            auto_features = _auto_features(
                rows=rows,
                returns=returns,
                index=index,
                feature_windows=feature_windows,
            )
            feature_rows.append(
                TrainingFeatureRow(
                    ticker=ticker,
                    date=current.date,
                    sector=current.sector,
                    close=current.close,
                    volume=current.volume,
                    return_1d=round(returns[current.date], 8),
                    return_5d=round((current.close / rows[index - short_window].close) - 1, 8),
                    rolling_mean_5d=round(statistics.fmean(short_returns), 8),
                    rolling_vol_5d=round(_sample_stdev(short_returns), 8),
                    rolling_mean_10d=round(statistics.fmean(trailing_returns), 8),
                    rolling_vol_10d=round(_sample_stdev(trailing_returns), 8),
                    sector_return_1d=round(
                        sector_returns.get((current.sector, current.date), 0.0),
                        8,
                    ),
                    correlated_peer_count=current.correlated_peer_count,
                    correlation_avg_abs=round(current.correlation_avg_abs, 8),
                    target_next_return=round(target_next_return, 8),
                    target_next_direction=1 if target_next_return > 0 else 0,
                    auto_features=auto_features,
                )
            )

    return feature_rows


def build_latest_inference_features(
    source_rows: Iterable[FeatureSourceRow],
    *,
    short_window: int = 5,
    long_window: int = 10,
    feature_windows: tuple[int, ...] = AUTO_FEATURE_WINDOWS,
) -> list[InferenceFeatureRow]:
    """Build one latest prediction feature row per ticker."""

    _validate_windows(short_window, long_window, feature_windows)
    minimum_window = max(long_window, max(feature_windows))

    rows_by_ticker = _rows_by_ticker(source_rows)
    returns_by_ticker = _returns_by_ticker(rows_by_ticker)
    sector_returns = _sector_returns(rows_by_ticker, returns_by_ticker)

    inference_rows: list[InferenceFeatureRow] = []
    for ticker, rows in sorted(rows_by_ticker.items()):
        if len(rows) <= minimum_window:
            continue

        index = len(rows) - 1
        current = rows[index]
        returns = returns_by_ticker[ticker]
        if current.date not in returns:
            continue

        trailing_returns = [
            returns[rows[trailing_index].date]
            for trailing_index in range(index - long_window + 1, index + 1)
            if rows[trailing_index].date in returns
        ]
        if len(trailing_returns) < long_window:
            continue

        short_returns = trailing_returns[-short_window:]
        auto_features = _auto_features(
            rows=rows,
            returns=returns,
            index=index,
            feature_windows=feature_windows,
        )
        inference_rows.append(
            InferenceFeatureRow(
                ticker=ticker,
                date=current.date,
                sector=current.sector,
                close=current.close,
                volume=current.volume,
                return_1d=round(returns[current.date], 8),
                return_5d=round((current.close / rows[index - short_window].close) - 1, 8),
                rolling_mean_5d=round(statistics.fmean(short_returns), 8),
                rolling_vol_5d=round(_sample_stdev(short_returns), 8),
                rolling_mean_10d=round(statistics.fmean(trailing_returns), 8),
                rolling_vol_10d=round(_sample_stdev(trailing_returns), 8),
                sector_return_1d=round(
                    sector_returns.get((current.sector, current.date), 0.0),
                    8,
                ),
                correlated_peer_count=current.correlated_peer_count,
                correlation_avg_abs=round(current.correlation_avg_abs, 8),
                auto_features=auto_features,
            )
        )

    return inference_rows


def export_feature_dataset(feature_rows: Iterable[TrainingFeatureRow], output_path: str | Path) -> int:
    """Write feature rows to CSV and return row count."""

    rows = [row.to_csv_row() for row in feature_rows]
    if not rows:
        raise ValueError("No feature rows to export")

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    return len(rows)


def _feature_source_row_from_neo4j(row: dict[str, Any]) -> FeatureSourceRow:
    return FeatureSourceRow(
        ticker=row["ticker"],
        date=row["date"],
        sector=row["sector"],
        close=float(row["close"]),
        volume=None if row["volume"] is None else int(row["volume"]),
        correlated_peer_count=int(row["correlated_peer_count"]),
        correlation_avg_abs=float(row["correlation_avg_abs"] or 0.0),
    )


def _rows_by_ticker(source_rows: Iterable[FeatureSourceRow]) -> dict[str, list[FeatureSourceRow]]:
    rows_by_ticker: dict[str, list[FeatureSourceRow]] = defaultdict(list)
    for row in source_rows:
        rows_by_ticker[row.ticker].append(row)

    return {
        ticker: sorted(rows, key=lambda row: row.date)
        for ticker, rows in rows_by_ticker.items()
        if rows
    }


def _returns_by_ticker(
    rows_by_ticker: dict[str, list[FeatureSourceRow]],
) -> dict[str, dict[str, float]]:
    returns_by_ticker: dict[str, dict[str, float]] = {}
    for ticker, rows in rows_by_ticker.items():
        returns: dict[str, float] = {}
        for previous, current in zip(rows, rows[1:], strict=False):
            if previous.close > 0:
                returns[current.date] = (current.close / previous.close) - 1
        returns_by_ticker[ticker] = returns

    return returns_by_ticker


def _sector_returns(
    rows_by_ticker: dict[str, list[FeatureSourceRow]],
    returns_by_ticker: dict[str, dict[str, float]],
) -> dict[tuple[str, str], float]:
    values_by_sector_date: dict[tuple[str, str], list[float]] = defaultdict(list)
    for ticker, rows in rows_by_ticker.items():
        returns = returns_by_ticker[ticker]
        for row in rows:
            if row.date in returns:
                values_by_sector_date[(row.sector, row.date)].append(returns[row.date])

    return {
        sector_date: statistics.fmean(values)
        for sector_date, values in values_by_sector_date.items()
        if values
    }


def _sample_stdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0

    return statistics.stdev(values)


def _validate_windows(
    short_window: int,
    long_window: int,
    feature_windows: tuple[int, ...],
) -> None:
    if short_window < 2:
        raise ValueError("short_window must be at least 2")
    if long_window < short_window:
        raise ValueError("long_window must be greater than or equal to short_window")
    if not feature_windows:
        raise ValueError("feature_windows must not be empty")
    if min(feature_windows) < 2:
        raise ValueError("feature_windows must contain values of at least 2")


def _auto_features(
    *,
    rows: list[FeatureSourceRow],
    returns: dict[str, float],
    index: int,
    feature_windows: tuple[int, ...],
) -> dict[str, float | int | None]:
    current = rows[index]
    features: dict[str, float | int | None] = {}

    previous_volume = rows[index - 1].volume if index > 0 else None
    features["volume_change_1d"] = _ratio_change(current.volume, previous_volume)

    for window in feature_windows:
        trailing_rows = rows[index - window + 1 : index + 1]
        trailing_returns = [
            returns[row.date]
            for row in trailing_rows
            if row.date in returns
        ]
        trailing_closes = [row.close for row in trailing_rows]
        trailing_volumes = [row.volume for row in trailing_rows if row.volume is not None]

        if len(trailing_returns) == window:
            features[f"return_{window}d"] = round((current.close / rows[index - window].close) - 1, 8)
            features[f"rolling_mean_{window}d"] = round(statistics.fmean(trailing_returns), 8)
            features[f"rolling_vol_{window}d"] = round(_sample_stdev(trailing_returns), 8)
            features[f"rolling_min_return_{window}d"] = round(min(trailing_returns), 8)
            features[f"rolling_max_return_{window}d"] = round(max(trailing_returns), 8)

        high = max(trailing_closes)
        low = min(trailing_closes)
        features[f"drawdown_{window}d"] = round((current.close / high) - 1, 8) if high else 0.0
        if high == low:
            features[f"price_position_{window}d"] = 0.5
        else:
            features[f"price_position_{window}d"] = round((current.close - low) / (high - low), 8)

        if current.volume is None or not trailing_volumes:
            features[f"volume_ratio_{window}d"] = None
        else:
            average_volume = statistics.fmean(trailing_volumes)
            features[f"volume_ratio_{window}d"] = (
                round(current.volume / average_volume, 8) if average_volume else None
            )

    return features


def _ratio_change(current: int | None, previous: int | None) -> float | None:
    if current is None or previous is None or previous == 0:
        return None

    return round((current / previous) - 1, 8)
