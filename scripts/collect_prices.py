"""Collect full available IDX price history for the global model pipeline."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys

from kag.logging import configure_logging
from kag.market_data.price_collection import fetch_price_history_frame, write_price_history_parquet
from kag.market_data.top_universe import DEFAULT_TOP100_UNIVERSE_PATH, load_stock_metadata


DEFAULT_OUTPUT_PATH = Path("data/prices_full_top100.parquet")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", type=Path, default=DEFAULT_TOP100_UNIVERSE_PATH)
    parser.add_argument("--ticker", action="append", help="Limit to selected ticker(s).")
    parser.add_argument("--limit", type=int, default=100, help="Defaults to the top 100 stocks.")
    parser.add_argument("--period", default="max")
    parser.add_argument("--interval", default="1d")
    parser.add_argument(
        "--start",
        help="Optional start date in YYYY-MM-DD format. Defaults to full available yfinance history.",
    )
    parser.add_argument("--end", help="Optional end date in YYYY-MM-DD format.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_logging()

    try:
        stocks = load_stock_metadata(args.universe, tickers=args.ticker, limit=args.limit)
        prices = fetch_price_history_frame(
            stocks,
            period=args.period,
            interval=args.interval,
            start=args.start,
            end=args.end,
        )
        rows = write_price_history_parquet(prices, args.output)
    except Exception:
        logger.exception("Price collection failed")
        return 1

    logger.info("Price collection succeeded; output=%s rows=%s tickers=%s", args.output, rows, len(stocks))
    return 0


if __name__ == "__main__":
    sys.exit(main())
