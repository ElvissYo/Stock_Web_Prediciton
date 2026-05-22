"""Export a supervised forecasting feature dataset from Neo4j graph context."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys

from kag.config import Settings
from kag.features.training_dataset import (
    build_training_features,
    export_feature_dataset,
    load_feature_source_rows,
)
from kag.graph.client import Neo4jClient
from kag.logging import configure_logging


DEFAULT_OUTPUT_PATH = Path("data/processed/training_features.csv")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ticker",
        action="append",
        help="IDX ticker to include. Can be repeated. Defaults to all stocks with price data.",
    )
    parser.add_argument("--price-source", default="yfinance", help="PricePoint source filter.")
    parser.add_argument("--interval", default="1d", help="PricePoint interval filter.")
    parser.add_argument("--start", help="Start date in YYYY-MM-DD format.")
    parser.add_argument("--end", help="End date in YYYY-MM-DD format.")
    parser.add_argument("--short-window", type=int, default=5, help="Short rolling window.")
    parser.add_argument("--long-window", type=int, default=10, help="Long rolling window.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH, help="Output CSV path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = Settings.from_env()
    configure_logging(settings.log_level)

    try:
        with Neo4jClient(settings) as client:
            source_rows = load_feature_source_rows(
                client,
                tickers=args.ticker,
                price_source=args.price_source,
                interval=args.interval,
                start=args.start,
                end=args.end,
            )
        logger.info("Loaded feature source rows; rows=%s", len(source_rows))

        feature_rows = build_training_features(
            source_rows,
            short_window=args.short_window,
            long_window=args.long_window,
        )
        logger.info("Built training feature rows; rows=%s", len(feature_rows))

        exported_rows = export_feature_dataset(feature_rows, args.output)
    except Exception:
        logger.exception("Training dataset build failed")
        return 1

    logger.info("Training dataset export succeeded; output=%s rows=%s", args.output, exported_rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
