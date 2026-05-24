"""Fuse price, NLP, and metadata features into final_dataset.parquet."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys

from kag.features.fusion import (
    DEFAULT_EMBEDDING_DIMENSIONS,
    DEFAULT_NLP_LAG_TRADING_DAYS,
    build_final_dataset_from_paths,
)
from kag.logging import configure_logging
from kag.market_data.top_universe import DEFAULT_TOP10_UNIVERSE_PATH


DEFAULT_PRICE_FEATURES_PATH = Path("data/processed/price_features.parquet")
DEFAULT_NLP_FEATURES_PATH = Path("data/nlp_features.parquet")
DEFAULT_OUTPUT_PATH = Path("data/final_dataset.parquet")
DEFAULT_ENCODERS_PATH = Path("models/encoders.pkl")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--price-features", type=Path, default=DEFAULT_PRICE_FEATURES_PATH)
    parser.add_argument("--nlp-features", type=Path, default=DEFAULT_NLP_FEATURES_PATH)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_TOP10_UNIVERSE_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--encoders-output", type=Path, default=DEFAULT_ENCODERS_PATH)
    parser.add_argument("--embedding-dimensions", type=int, default=DEFAULT_EMBEDDING_DIMENSIONS)
    parser.add_argument(
        "--nlp-lag-trading-days",
        type=int,
        default=DEFAULT_NLP_LAG_TRADING_DAYS,
        help=(
            "How many trading rows after a news date the NLP feature becomes available. "
            "Default avoids same-day news leakage when only dates, not timestamps, are known."
        ),
    )
    parser.add_argument(
        "--drop-unlabeled",
        action="store_true",
        help="Drop latest rows without next-day target labels. Default keeps them for prediction.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_logging()

    try:
        rows = build_final_dataset_from_paths(
            args.price_features,
            args.nlp_features,
            args.output,
            metadata_path=args.metadata,
            embedding_dimensions=args.embedding_dimensions,
            nlp_lag_trading_days=args.nlp_lag_trading_days,
            encoders_path=args.encoders_output,
            drop_unlabeled=args.drop_unlabeled,
        )
    except Exception:
        logger.exception("Final dataset build failed")
        return 1

    logger.info("Final dataset build succeeded; output=%s rows=%s", args.output, rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
