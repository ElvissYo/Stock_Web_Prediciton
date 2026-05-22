"""Stock correlation graph construction from historical price points."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import math
from typing import Any, Iterable

from kag.graph.client import Neo4jClient


@dataclass(frozen=True)
class PriceObservation:
    """Close price observation loaded from the graph."""

    ticker: str
    date: str
    close: float


@dataclass(frozen=True)
class CorrelationRelationship:
    """Pearson correlation relationship between two stocks."""

    source_ticker: str
    target_ticker: str
    coefficient: float
    observations: int
    first_date: str
    last_date: str
    method: str
    price_source: str
    interval: str

    @property
    def abs_coefficient(self) -> float:
        return abs(self.coefficient)

    def to_neo4j(self) -> dict[str, float | int | str]:
        return {
            "source_ticker": self.source_ticker,
            "target_ticker": self.target_ticker,
            "coefficient": self.coefficient,
            "abs_coefficient": self.abs_coefficient,
            "observations": self.observations,
            "first_date": self.first_date,
            "last_date": self.last_date,
            "method": self.method,
            "price_source": self.price_source,
            "interval": self.interval,
        }


@dataclass(frozen=True)
class CorrelationWriteResult:
    """Summary returned after writing stock correlation relationships."""

    relationships_read: int
    relationships_processed: int


@dataclass(frozen=True)
class CorrelationDeleteResult:
    """Summary returned after deleting old stock correlation relationships."""

    relationships_deleted: int


def load_price_observations(
    client: Neo4jClient,
    *,
    tickers: list[str] | None = None,
    price_source: str = "yfinance",
    interval: str = "1d",
) -> list[PriceObservation]:
    """Load close price observations from Neo4j."""

    normalized_tickers = [ticker.strip().upper().removesuffix(".JK") for ticker in tickers or []]
    rows = client.execute_read(
        """
        MATCH (:Stock)-[:HAS_PRICE]->(price:PricePoint)
        WHERE price.source = $price_source
          AND price.interval = $interval
          AND (size($tickers) = 0 OR price.ticker IN $tickers)
          AND price.close IS NOT NULL
        RETURN price.ticker AS ticker,
               toString(price.date) AS date,
               price.close AS close
        ORDER BY ticker, date
        """,
        {
            "tickers": normalized_tickers,
            "price_source": price_source,
            "interval": interval,
        },
    )
    return [
        PriceObservation(ticker=row["ticker"], date=row["date"], close=float(row["close"]))
        for row in rows
    ]


def calculate_return_correlations(
    observations: Iterable[PriceObservation],
    *,
    min_observations: int = 20,
    min_abs_correlation: float = 0.3,
    method: str = "pearson_close_return",
    price_source: str = "yfinance",
    interval: str = "1d",
) -> list[CorrelationRelationship]:
    """Calculate pairwise Pearson correlations over aligned daily close returns."""

    if min_observations < 2:
        raise ValueError("min_observations must be at least 2")
    if min_abs_correlation < 0 or min_abs_correlation > 1:
        raise ValueError("min_abs_correlation must be between 0 and 1")

    returns_by_ticker = _close_returns_by_ticker(observations)
    tickers = sorted(returns_by_ticker)
    relationships: list[CorrelationRelationship] = []

    for left_index, left_ticker in enumerate(tickers):
        for right_ticker in tickers[left_index + 1 :]:
            aligned = _align_returns(returns_by_ticker[left_ticker], returns_by_ticker[right_ticker])
            if len(aligned) < min_observations:
                continue

            coefficient = _pearson([left for _, left, _ in aligned], [right for _, _, right in aligned])
            if coefficient is None or abs(coefficient) < min_abs_correlation:
                continue

            relationships.append(
                CorrelationRelationship(
                    source_ticker=left_ticker,
                    target_ticker=right_ticker,
                    coefficient=round(coefficient, 6),
                    observations=len(aligned),
                    first_date=aligned[0][0],
                    last_date=aligned[-1][0],
                    method=method,
                    price_source=price_source,
                    interval=interval,
                )
            )

    return relationships


def write_correlations(
    client: Neo4jClient,
    relationships: Iterable[CorrelationRelationship],
) -> CorrelationWriteResult:
    """Merge stock correlation relationships into Neo4j."""

    rows = [relationship.to_neo4j() for relationship in relationships]
    if not rows:
        return CorrelationWriteResult(relationships_read=0, relationships_processed=0)

    result = client.execute_write(
        """
        UNWIND $rows AS row
        MATCH (source:Stock {ticker: row.source_ticker})
        MATCH (target:Stock {ticker: row.target_ticker})
        MERGE (source)-[relationship:CORRELATED_WITH {
            method: row.method,
            price_source: row.price_source,
            interval: row.interval
        }]->(target)
        ON CREATE SET relationship.created_at = datetime()
        SET relationship.coefficient = row.coefficient,
            relationship.abs_coefficient = row.abs_coefficient,
            relationship.observations = row.observations,
            relationship.first_date = date(row.first_date),
            relationship.last_date = date(row.last_date),
            relationship.updated_at = datetime()
        RETURN count(relationship) AS relationships_processed
        """,
        {"rows": rows},
    )
    counters: dict[str, Any] = result[0] if result else {}
    return CorrelationWriteResult(
        relationships_read=len(rows),
        relationships_processed=int(counters.get("relationships_processed", 0)),
    )


def delete_correlations(
    client: Neo4jClient,
    *,
    tickers: Iterable[str],
    method: str,
    price_source: str,
    interval: str,
) -> CorrelationDeleteResult:
    """Delete existing correlation relationships for the current calculation scope."""

    normalized_tickers = sorted({ticker.strip().upper().removesuffix(".JK") for ticker in tickers})
    result = client.execute_write(
        """
        MATCH (source:Stock)-[relationship:CORRELATED_WITH {
            method: $method,
            price_source: $price_source,
            interval: $interval
        }]->(target:Stock)
        WHERE size($tickers) = 0
           OR (source.ticker IN $tickers AND target.ticker IN $tickers)
        WITH collect(relationship) AS relationships
        FOREACH (relationship IN relationships | DELETE relationship)
        RETURN size(relationships) AS relationships_deleted
        """,
        {
            "tickers": normalized_tickers,
            "method": method,
            "price_source": price_source,
            "interval": interval,
        },
    )
    counters: dict[str, Any] = result[0] if result else {}
    return CorrelationDeleteResult(
        relationships_deleted=int(counters.get("relationships_deleted", 0)),
    )


def _close_returns_by_ticker(
    observations: Iterable[PriceObservation],
) -> dict[str, dict[str, float]]:
    prices_by_ticker: dict[str, list[PriceObservation]] = defaultdict(list)
    for observation in observations:
        prices_by_ticker[observation.ticker].append(observation)

    returns_by_ticker: dict[str, dict[str, float]] = {}
    for ticker, prices in prices_by_ticker.items():
        sorted_prices = sorted(prices, key=lambda price: price.date)
        returns: dict[str, float] = {}
        previous_close: float | None = None
        for price in sorted_prices:
            if previous_close is not None and previous_close > 0:
                returns[price.date] = (price.close / previous_close) - 1
            previous_close = price.close

        if returns:
            returns_by_ticker[ticker] = returns

    return returns_by_ticker


def _align_returns(
    left_returns: dict[str, float],
    right_returns: dict[str, float],
) -> list[tuple[str, float, float]]:
    common_dates = sorted(set(left_returns) & set(right_returns))
    return [(date, left_returns[date], right_returns[date]) for date in common_dates]


def _pearson(left_values: list[float], right_values: list[float]) -> float | None:
    if len(left_values) != len(right_values) or len(left_values) < 2:
        return None

    left_mean = sum(left_values) / len(left_values)
    right_mean = sum(right_values) / len(right_values)
    numerator = sum(
        (left - left_mean) * (right - right_mean)
        for left, right in zip(left_values, right_values, strict=True)
    )
    left_denominator = math.sqrt(sum((left - left_mean) ** 2 for left in left_values))
    right_denominator = math.sqrt(sum((right - right_mean) ** 2 for right in right_values))
    denominator = left_denominator * right_denominator
    if denominator == 0:
        return None

    return numerator / denominator
