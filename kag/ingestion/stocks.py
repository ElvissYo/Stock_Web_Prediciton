"""Stock and sector ingestion for the knowledge graph."""

from __future__ import annotations

from dataclasses import dataclass
import csv
from pathlib import Path
from typing import Any, Iterable

from kag.graph.client import Neo4jClient


REQUIRED_COLUMNS = frozenset({"ticker", "name", "sector"})


@dataclass(frozen=True)
class StockRecord:
    """Canonical stock metadata used to create Stock and Sector graph nodes."""

    ticker: str
    name: str
    sector: str
    exchange: str = "IDX"
    yfinance_symbol: str | None = None

    @classmethod
    def from_csv_row(cls, row: dict[str, str], line_number: int) -> "StockRecord":
        ticker = _required_value(row, "ticker", line_number)
        canonical_ticker = normalize_ticker(ticker)

        yfinance_symbol = _optional_value(row, "yfinance_symbol")
        if yfinance_symbol is None:
            yfinance_symbol = f"{canonical_ticker}.JK"

        return cls(
            ticker=canonical_ticker,
            name=_required_value(row, "name", line_number),
            sector=_required_value(row, "sector", line_number),
            exchange=_optional_value(row, "exchange") or "IDX",
            yfinance_symbol=yfinance_symbol.upper(),
        )

    def to_neo4j(self) -> dict[str, str | None]:
        return {
            "ticker": self.ticker,
            "name": self.name,
            "sector": self.sector,
            "exchange": self.exchange,
            "yfinance_symbol": self.yfinance_symbol,
        }


@dataclass(frozen=True)
class StockIngestionResult:
    """Summary returned after a stock universe ingestion run."""

    rows_read: int
    rows_processed: int
    sectors_processed: int


def load_stock_records(csv_path: str | Path) -> list[StockRecord]:
    """Load and validate stock records from CSV."""

    path = Path(csv_path)
    with path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        _validate_header(reader.fieldnames, path)

        records = [
            StockRecord.from_csv_row(row, line_number)
            for line_number, row in enumerate(reader, start=2)
        ]

    if not records:
        raise ValueError(f"No stock records found in CSV: {path}")

    return records


def ingest_stocks(client: Neo4jClient, records: Iterable[StockRecord]) -> StockIngestionResult:
    """Merge Stock, Sector, and Stock-to-Sector relationships into Neo4j."""

    rows = [record.to_neo4j() for record in records]
    if not rows:
        return StockIngestionResult(rows_read=0, rows_processed=0, sectors_processed=0)

    result = client.execute_write(
        """
        UNWIND $rows AS row
        MERGE (sector:Sector {name: row.sector})
        ON CREATE SET sector.created_at = datetime()
        SET sector.updated_at = datetime()
        MERGE (stock:Stock {ticker: row.ticker})
        ON CREATE SET stock.created_at = datetime()
        SET stock.name = row.name,
            stock.exchange = row.exchange,
            stock.yfinance_symbol = row.yfinance_symbol,
            stock.updated_at = datetime()
        MERGE (stock)-[relationship:IN_SECTOR]->(sector)
        ON CREATE SET relationship.created_at = datetime()
        SET relationship.updated_at = datetime()
        RETURN count(row) AS rows_processed,
               count(DISTINCT row.sector) AS sectors_processed
        """,
        {"rows": rows},
    )

    counters: dict[str, Any] = result[0] if result else {}
    return StockIngestionResult(
        rows_read=len(rows),
        rows_processed=int(counters.get("rows_processed", 0)),
        sectors_processed=int(counters.get("sectors_processed", 0)),
    )


def normalize_ticker(ticker: str) -> str:
    """Normalize local IDX tickers while accepting yfinance-style symbols."""

    normalized = ticker.strip().upper()
    if normalized.endswith(".JK"):
        return normalized.removesuffix(".JK")

    return normalized


def _validate_header(fieldnames: list[str] | None, path: Path) -> None:
    if fieldnames is None:
        raise ValueError(f"CSV has no header: {path}")

    normalized_fields = {field.strip() for field in fieldnames}
    missing_columns = REQUIRED_COLUMNS - normalized_fields
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"CSV {path} is missing required columns: {missing}")


def _required_value(row: dict[str, str], column: str, line_number: int) -> str:
    value = _optional_value(row, column)
    if value is None:
        raise ValueError(f"Missing required value for '{column}' on CSV line {line_number}")

    return value


def _optional_value(row: dict[str, str], column: str) -> str | None:
    value = row.get(column)
    if value is None:
        return None

    stripped = value.strip()
    return stripped or None

