"""Shared market data types."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StockSymbol:
    """Ticker mapping used by external market data providers."""

    ticker: str
    yfinance_symbol: str


@dataclass(frozen=True)
class PriceBar:
    """Daily or intraday OHLCV market data for one stock."""

    ticker: str
    date: str
    open: float | None
    high: float | None
    low: float | None
    close: float
    adj_close: float | None
    volume: int | None
    source: str
    interval: str

    def to_neo4j(self) -> dict[str, float | int | str | None]:
        return {
            "ticker": self.ticker,
            "date": self.date,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "adj_close": self.adj_close,
            "volume": self.volume,
            "source": self.source,
            "interval": self.interval,
        }

