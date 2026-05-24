"""Build technical price features for the global model pipeline."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys

from kag.features.technical_indicators import build_price_features_from_parquet
from kag.logging import configure_logging


DEFAULT_INPUT_PATH = Path("data/prices_full_top100.parquet")
LEGACY_INPUT_PATH = Path("data/prices_20y_top100.parquet")
DEFAULT_OUTPUT_PATH = Path("data/processed/price_features.parquet")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_logging()

    try:
        rows = build_price_features_from_parquet(_resolve_input_path(args.input), args.output)
    except Exception:
        logger.exception("Price feature build failed")
        return 1

    logger.info("Price feature build succeeded; output=%s rows=%s", args.output, rows)
    return 0


def _resolve_input_path(path: Path) -> Path:
    if path.exists():
        return path
    if path == DEFAULT_INPUT_PATH and LEGACY_INPUT_PATH.exists():
        logger.warning("Full price artifact missing; using legacy artifact: %s", LEGACY_INPUT_PATH)
        return LEGACY_INPUT_PATH
    return path


if __name__ == "__main__":
    sys.exit(main())
