"""Historical price ingestion for the knowledge graph."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from kag.graph.client import Neo4jClient
from kag.market_data.types import PriceBar


@dataclass(frozen=True)
class PriceIngestionResult:
    """Summary returned after a historical price ingestion run."""

    rows_read: int
    rows_processed: int
    batches_processed: int


def ingest_price_bars(
    client: Neo4jClient,
    price_bars: Iterable[PriceBar],
    *,
    batch_size: int = 1000,
) -> PriceIngestionResult:
    """Merge PricePoint nodes and Stock-to-PricePoint relationships into Neo4j."""

    if batch_size < 1:
        raise ValueError("batch_size must be greater than zero")

    rows = [price_bar.to_neo4j() for price_bar in price_bars]
    if not rows:
        return PriceIngestionResult(rows_read=0, rows_processed=0, batches_processed=0)

    rows_processed = 0
    batches_processed = 0
    for batch in _chunked(rows, batch_size):
        result = client.execute_write(
            """
            UNWIND $rows AS row
            MATCH (stock:Stock {ticker: row.ticker})
            WITH row, stock, date(row.date) AS price_date
            MERGE (price:PricePoint {
                ticker: row.ticker,
                date: price_date,
                source: row.source,
                interval: row.interval
            })
            ON CREATE SET price.created_at = datetime()
            SET price.open = row.open,
                price.high = row.high,
                price.low = row.low,
                price.close = row.close,
                price.adj_close = row.adj_close,
                price.volume = row.volume,
                price.updated_at = datetime()
            MERGE (stock)-[relationship:HAS_PRICE]->(price)
            ON CREATE SET relationship.created_at = datetime()
            SET relationship.updated_at = datetime()
            RETURN count(price) AS rows_processed
            """,
            {"rows": batch},
        )
        counters: dict[str, Any] = result[0] if result else {}
        rows_processed += int(counters.get("rows_processed", 0))
        batches_processed += 1

    return PriceIngestionResult(
        rows_read=len(rows),
        rows_processed=rows_processed,
        batches_processed=batches_processed,
    )


def _chunked(rows: list[dict[str, float | int | str | None]], batch_size: int) -> list[list[dict]]:
    return [rows[index : index + batch_size] for index in range(0, len(rows), batch_size)]
