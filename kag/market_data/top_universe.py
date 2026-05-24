"""Local IDX ticker universe helpers for Parquet-based forecasting pipelines."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from kag.ingestion.stocks import normalize_ticker


DEFAULT_TOP10_UNIVERSE_PATH = Path("data/seeds/idx_top10_poc.csv")
DEFAULT_TOP100_UNIVERSE_PATH = Path("data/seeds/idx_stock_universe.csv")


@dataclass(frozen=True)
class StockMetadata:
    """Stock metadata used by local Parquet pipelines."""

    ticker: str
    yfinance_symbol: str
    name: str = ""
    sector: str = "UNKNOWN"
    market_cap_rank: int | None = None
    beta: float | None = None

    @classmethod
    def from_csv_row(cls, row: dict[str, str], line_number: int) -> "StockMetadata":
        ticker = normalize_ticker(_required_value(row, "ticker", line_number))
        yfinance_symbol = _optional_value(row, "yfinance_symbol") or f"{ticker}.JK"

        return cls(
            ticker=ticker,
            yfinance_symbol=yfinance_symbol.upper(),
            name=_optional_value(row, "name") or ticker,
            sector=_optional_value(row, "sector") or "UNKNOWN",
            market_cap_rank=_optional_int(row, "market_cap_rank")
            or _optional_int(row, "universe_rank"),
            beta=_optional_float(row, "beta"),
        )

    def to_csv_row(self) -> dict[str, str]:
        return {
            "ticker": self.ticker,
            "yfinance_symbol": self.yfinance_symbol,
            "name": self.name,
            "sector": self.sector,
            "market_cap_rank": "" if self.market_cap_rank is None else str(self.market_cap_rank),
            "beta": "" if self.beta is None else str(self.beta),
        }


def load_stock_metadata(
    csv_path: str | Path = DEFAULT_TOP10_UNIVERSE_PATH,
    *,
    tickers: Iterable[str] | None = None,
    limit: int | None = None,
) -> list[StockMetadata]:
    """Load ticker metadata for local price/news pipelines."""

    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Stock universe CSV does not exist: {path}")

    selected_tickers = {normalize_ticker(ticker) for ticker in tickers or []}
    with path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        _validate_header(reader.fieldnames, path)
        records = [
            StockMetadata.from_csv_row(row, line_number)
            for line_number, row in enumerate(reader, start=2)
        ]

    if selected_tickers:
        records = [record for record in records if record.ticker in selected_tickers]

    records = sorted(records, key=lambda record: record.market_cap_rank or 1000000)
    if limit is not None:
        records = records[:limit]

    if not records:
        raise ValueError(f"No stock metadata records found in {path}")

    return records


def write_stock_metadata_csv(records: Iterable[StockMetadata], csv_path: str | Path) -> int:
    """Write local stock metadata in the POC CSV format."""

    rows = [record.to_csv_row() for record in records]
    path = Path(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["ticker", "yfinance_symbol", "name", "sector", "market_cap_rank", "beta"],
        )
        writer.writeheader()
        writer.writerows(rows)

    return len(rows)


def ticker_aliases(records: Iterable[StockMetadata]) -> dict[str, set[str]]:
    """Build simple ticker aliases used by RSS article matching."""

    aliases: dict[str, set[str]] = {}
    for record in records:
        ticker = normalize_ticker(record.ticker)
        aliases[ticker] = {
            ticker,
            f"{ticker}.JK",
            record.yfinance_symbol.upper(),
        }
    return aliases


def _validate_header(fieldnames: list[str] | None, path: Path) -> None:
    if fieldnames is None:
        raise ValueError(f"CSV has no header: {path}")

    normalized = {field.strip() for field in fieldnames}
    if "ticker" not in normalized:
        raise ValueError(f"CSV {path} is missing required column: ticker")


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


def _optional_int(row: dict[str, str], column: str) -> int | None:
    value = _optional_value(row, column)
    if value is None:
        return None
    return int(float(value))


def _optional_float(row: dict[str, str], column: str) -> float | None:
    value = _optional_value(row, column)
    if value is None:
        return None
    return float(value)
