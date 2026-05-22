"""Predict latest next-period direction using graph features and a trained model."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys

from kag.config import Settings
from kag.features.training_dataset import build_latest_inference_features, load_feature_source_rows
from kag.graph.client import Neo4jClient
from kag.logging import configure_logging
from kag.modeling.inference import export_predictions, load_model_artifact, predict_directions


DEFAULT_MODEL_PATH = Path("models/direction_model.joblib")
DEFAULT_OUTPUT_PATH = Path("data/processed/latest_direction_predictions.csv")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument(
        "--ticker",
        action="append",
        help="IDX ticker to include. Can be repeated. Defaults to all stocks with price data.",
    )
    parser.add_argument("--price-source", default="yfinance", help="PricePoint source filter.")
    parser.add_argument("--interval", default="1d", help="PricePoint interval filter.")
    parser.add_argument("--short-window", type=int, default=5, help="Short rolling window.")
    parser.add_argument("--long-window", type=int, default=10, help="Long rolling window.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = Settings.from_env()
    configure_logging(settings.log_level)

    try:
        artifact = load_model_artifact(args.model)
        with Neo4jClient(settings) as client:
            source_rows = load_feature_source_rows(
                client,
                tickers=args.ticker,
                price_source=args.price_source,
                interval=args.interval,
            )
        logger.info("Loaded graph feature source rows; rows=%s", len(source_rows))

        feature_rows = build_latest_inference_features(
            source_rows,
            short_window=args.short_window,
            long_window=args.long_window,
        )
        logger.info("Built latest inference feature rows; rows=%s", len(feature_rows))

        predictions = predict_directions(artifact, feature_rows)
        exported_rows = export_predictions(predictions, args.output)
    except Exception:
        logger.exception("Latest direction prediction failed")
        return 1

    logger.info("Latest direction prediction succeeded; output=%s rows=%s", args.output, exported_rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())

