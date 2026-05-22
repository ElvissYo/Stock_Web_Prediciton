"""Fetch an expanded IDX stock universe CSV for graph ingestion."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys

from kag.logging import configure_logging
from kag.market_data.stock_universe import (
    STOCKANALYSIS_IDX_URL,
    fetch_stockanalysis_idx_universe,
    write_stock_universe_csv,
)


DEFAULT_OUTPUT_PATH = Path("data/seeds/idx_stock_universe.csv")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument(
        "--source",
        choices=["stockanalysis"],
        default="stockanalysis",
        help="Stock universe source. The module boundary keeps this replaceable later.",
    )
    parser.add_argument("--url", default=STOCKANALYSIS_IDX_URL)
    parser.add_argument("--max-pages", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument(
        "--limit",
        type=int,
        help="Optional record limit for quick smoke runs. Omit for the full universe.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_logging()

    try:
        records = fetch_stockanalysis_idx_universe(
            url=args.url,
            max_pages=args.max_pages,
            timeout=args.timeout,
        )
        if args.limit is not None:
            records = records[: args.limit]

        rows_written = write_stock_universe_csv(records, args.output)
    except Exception:
        logger.exception("IDX stock universe fetch failed")
        return 1

    logger.info(
        "IDX stock universe CSV written; source=%s rows=%s output=%s",
        args.source,
        rows_written,
        args.output,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
