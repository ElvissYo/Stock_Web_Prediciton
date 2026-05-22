"""Train a baseline next-period stock direction model from exported features."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys

from kag.logging import configure_logging
from kag.modeling.direction_model import train_direction_model


DEFAULT_DATASET_PATH = Path("data/processed/training_features.csv")
DEFAULT_MODEL_PATH = Path("models/direction_model.joblib")
DEFAULT_METRICS_PATH = Path("models/direction_model_metrics.json")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--model-output", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--metrics-output", type=Path, default=DEFAULT_METRICS_PATH)
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument(
        "--no-lightgbm",
        action="store_true",
        help="Use the sklearn fallback model even when LightGBM is installed.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_logging()

    try:
        result = train_direction_model(
            args.dataset,
            model_path=args.model_output,
            metrics_path=args.metrics_output,
            test_size=args.test_size,
            random_state=args.random_state,
            prefer_lightgbm=not args.no_lightgbm,
        )
    except Exception:
        logger.exception("Direction model training failed")
        return 1

    logger.info(
        "Direction model training succeeded; model_type=%s train_rows=%s test_rows=%s metrics=%s",
        result.model_type,
        result.train_rows,
        result.test_rows,
        result.metrics,
    )
    logger.info("Saved model=%s metrics=%s", result.model_path, result.metrics_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())

