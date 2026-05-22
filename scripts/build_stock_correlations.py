"""Build CORRELATED_WITH relationships between stocks from price returns."""

from __future__ import annotations

import argparse
import logging
import sys

from kag.config import Settings
from kag.graph.client import Neo4jClient
from kag.graph.correlations import (
    calculate_return_correlations,
    delete_correlations,
    load_price_observations,
    write_correlations,
)
from kag.logging import configure_logging


logger = logging.getLogger(__name__)
CORRELATION_METHOD = "pearson_close_return"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ticker",
        action="append",
        help="IDX ticker to include. Can be repeated. Defaults to all stocks with price data.",
    )
    parser.add_argument("--price-source", default="yfinance", help="PricePoint source filter.")
    parser.add_argument("--interval", default="1d", help="PricePoint interval filter.")
    parser.add_argument(
        "--min-observations",
        type=int,
        default=20,
        help="Minimum aligned return observations per pair.",
    )
    parser.add_argument(
        "--min-abs-correlation",
        type=float,
        default=0.3,
        help="Minimum absolute Pearson coefficient to persist.",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append/update correlations without deleting stale relationships first.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = Settings.from_env()
    configure_logging(settings.log_level)

    try:
        with Neo4jClient(settings) as client:
            observations = load_price_observations(
                client,
                tickers=args.ticker,
                price_source=args.price_source,
                interval=args.interval,
            )
            logger.info("Loaded price observations; rows=%s", len(observations))

            relationships = calculate_return_correlations(
                observations,
                min_observations=args.min_observations,
                min_abs_correlation=args.min_abs_correlation,
                method=CORRELATION_METHOD,
                price_source=args.price_source,
                interval=args.interval,
            )
            logger.info("Calculated correlation relationships; rows=%s", len(relationships))

            if not args.append:
                tickers = sorted({observation.ticker for observation in observations})
                delete_result = delete_correlations(
                    client,
                    tickers=tickers,
                    method=CORRELATION_METHOD,
                    price_source=args.price_source,
                    interval=args.interval,
                )
                logger.info(
                    "Deleted stale correlation relationships; rows=%s",
                    delete_result.relationships_deleted,
                )

            result = write_correlations(client, relationships)
    except Exception:
        logger.exception("Stock correlation build failed")
        return 1

    logger.info(
        "Stock correlation build succeeded; relationships_read=%s relationships_processed=%s",
        result.relationships_read,
        result.relationships_processed,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
