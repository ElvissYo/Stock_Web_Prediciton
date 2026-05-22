"""Stock symbol lookup helpers for market data providers."""

from __future__ import annotations

from kag.graph.client import Neo4jClient
from kag.market_data.types import StockSymbol


def load_stock_symbols(
    client: Neo4jClient,
    *,
    tickers: list[str] | None,
    limit: int | None,
) -> list[StockSymbol]:
    """Load ticker/provider-symbol mappings from Neo4j."""

    normalized_tickers = [ticker.strip().upper().removesuffix(".JK") for ticker in tickers or []]
    result = client.execute_read(
        """
        MATCH (stock:Stock)
        WHERE size($tickers) = 0 OR stock.ticker IN $tickers
        RETURN stock.ticker AS ticker,
               coalesce(stock.yfinance_symbol, stock.ticker + '.JK') AS yfinance_symbol
        ORDER BY stock.ticker
        LIMIT $limit
        """,
        {
            "tickers": normalized_tickers,
            "limit": limit if limit is not None else 100000,
        },
    )

    symbols = [
        StockSymbol(ticker=row["ticker"], yfinance_symbol=row["yfinance_symbol"]) for row in result
    ]
    if not symbols:
        raise ValueError("No Stock nodes found for historical price ingestion")

    return symbols

