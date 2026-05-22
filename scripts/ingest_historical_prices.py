"""Fetch historical prices from yfinance and ingest them into Neo4j."""

from __future__ import annotations

import argparse
import logging
import sys

from kag.config import Settings
from kag.graph.client import Neo4jClient
from kag.graph.schema import apply_schema
from kag.ingestion.prices import ingest_price_bars
from kag.logging import configure_logging
from kag.market_data.symbols import load_stock_symbols
from kag.market_data.yfinance_provider import fetch_historical_prices


logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ticker",
        action="append",
        help="IDX ticker to fetch. Can be repeated. Defaults to all Stock nodes.",
    )
    parser.add_argument("--period", default="1mo", help="yfinance period when --start is omitted.")
    parser.add_argument("--start", help="Start date in YYYY-MM-DD format.")
    parser.add_argument("--end", help="End date in YYYY-MM-DD format.")
    parser.add_argument("--interval", default="1d", help="yfinance interval, e.g. 1d, 1wk, 1mo.")
    parser.add_argument("--limit", type=int, help="Limit number of Stock nodes fetched from Neo4j.")
    parser.add_argument("--batch-size", type=int, default=1000, help="Neo4j write batch size.")
    parser.add_argument(
        "--skip-schema",
        action="store_true",
        help="Skip idempotent Neo4j schema setup before ingestion.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = Settings.from_env()
    configure_logging(settings.log_level)

    try:
        with Neo4jClient(settings) as client:
            if not args.skip_schema:
                apply_schema(client)

            symbols = load_stock_symbols(client, tickers=args.ticker, limit=args.limit)
            logger.info("Fetching historical prices from yfinance; symbols=%s", len(symbols))

            price_bars = fetch_historical_prices(
                symbols,
                period=args.period,
                interval=args.interval,
                start=args.start,
                end=args.end,
            )
            logger.info("Fetched price bars; rows=%s", len(price_bars))

            result = ingest_price_bars(client, price_bars, batch_size=args.batch_size)
    except Exception:
        logger.exception("Historical price ingestion failed")
        return 1

    logger.info(
        "Historical price ingestion succeeded; rows_read=%s rows_processed=%s batches_processed=%s",
        result.rows_read,
        result.rows_processed,
        result.batches_processed,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
