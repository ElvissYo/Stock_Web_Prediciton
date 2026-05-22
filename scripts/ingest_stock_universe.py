"""Ingest Stock and Sector nodes into Neo4j from a CSV file."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys

from kag.config import Settings
from kag.graph.client import Neo4jClient
from kag.graph.schema import apply_schema
from kag.ingestion.stocks import ingest_stocks, load_stock_records
from kag.logging import configure_logging


DEFAULT_CSV_PATH = Path("data/seeds/idx_stock_universe.csv")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--csv",
        default=DEFAULT_CSV_PATH,
        type=Path,
        help="Path to stock universe CSV. Required columns: ticker, name, sector.",
    )
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

    logger.info("Loading stock universe from csv=%s", args.csv)

    try:
        records = load_stock_records(args.csv)
        with Neo4jClient(settings) as client:
            if not args.skip_schema:
                apply_schema(client)

            result = ingest_stocks(client, records)
    except Exception:
        logger.exception("Stock universe ingestion failed")
        return 1

    logger.info(
        "Stock universe ingestion succeeded; rows_read=%s rows_processed=%s sectors_processed=%s",
        result.rows_read,
        result.rows_processed,
        result.sectors_processed,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
