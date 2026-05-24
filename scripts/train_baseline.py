"""Train Model A: single global return model without NLP features."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys

from kag.logging import configure_logging
from kag.modeling.global_model import train_global_return_model


DEFAULT_DATASET_PATH = Path("data/final_dataset.parquet")
DEFAULT_MODEL_PATH = Path("models/baseline_model.txt")
DEFAULT_METRICS_PATH = Path("reports/baseline_metrics.json")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--model-output", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--metrics-output", type=Path, default=DEFAULT_METRICS_PATH)
    parser.add_argument("--n-splits", type=int, default=5)
    parser.add_argument("--cv-gap-dates", type=int, default=1)
    parser.add_argument("--selection-top-n", type=int, default=10)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--no-lightgbm", action="store_true")
    parser.add_argument("--no-direction-classifier", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_logging()

    try:
        result = train_global_return_model(
            args.dataset,
            include_nlp=False,
            model_name="baseline_price_metadata",
            model_output_path=args.model_output,
            metrics_output_path=args.metrics_output,
            n_splits=args.n_splits,
            cv_gap_dates=args.cv_gap_dates,
            selection_top_n=args.selection_top_n,
            random_state=args.random_state,
            prefer_lightgbm=not args.no_lightgbm,
            train_direction_classifier=not args.no_direction_classifier,
        )
    except Exception:
        logger.exception("Baseline global model training failed")
        return 1

    logger.info("Baseline training succeeded; metrics=%s", result.metrics)
    return 0


if __name__ == "__main__":
    sys.exit(main())
