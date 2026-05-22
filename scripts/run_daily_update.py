"""Run the incremental KAG update pipeline."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys

from kag.config import Settings
from kag.logging import configure_logging
from kag.pipeline.daily_update import DailyUpdateConfig, run_daily_update


logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock-csv", type=Path, default=Path("data/seeds/ihsg_stocks_sample.csv"))
    parser.add_argument("--ticker", action="append", help="Limit pipeline to selected IDX ticker(s).")
    parser.add_argument("--limit", type=int, help="Limit number of Stock nodes for price fetch.")
    parser.add_argument("--price-period", default="1mo")
    parser.add_argument("--price-start")
    parser.add_argument("--price-end")
    parser.add_argument("--price-interval", default="1d")
    parser.add_argument("--min-correlation-observations", type=int, default=20)
    parser.add_argument("--min-abs-correlation", type=float, default=0.3)
    parser.add_argument(
        "--training-dataset",
        type=Path,
        default=Path("data/processed/training_features.csv"),
    )
    parser.add_argument(
        "--prediction-output",
        type=Path,
        default=Path("data/processed/latest_direction_predictions.csv"),
    )
    parser.add_argument("--model-path", type=Path, default=Path("models/direction_model.joblib"))
    parser.add_argument("--metrics-path", type=Path, default=Path("models/direction_model_metrics.json"))
    parser.add_argument("--skip-schema", action="store_true")
    parser.add_argument("--skip-stock-ingestion", action="store_true")
    parser.add_argument("--skip-price-ingestion", action="store_true")
    parser.add_argument("--skip-correlations", action="store_true")
    parser.add_argument("--skip-feature-dataset", action="store_true")
    parser.add_argument("--skip-prediction", action="store_true")
    parser.add_argument(
        "--train-model",
        action="store_true",
        help="Opt-in retraining. Disabled by default to keep daily updates light.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = Settings.from_env()
    configure_logging(settings.log_level)

    config = DailyUpdateConfig(
        stock_csv=args.stock_csv,
        price_period=args.price_period,
        price_interval=args.price_interval,
        price_start=args.price_start,
        price_end=args.price_end,
        tickers=args.ticker,
        limit=args.limit,
        min_correlation_observations=args.min_correlation_observations,
        min_abs_correlation=args.min_abs_correlation,
        training_dataset_path=args.training_dataset,
        prediction_output_path=args.prediction_output,
        model_path=args.model_path,
        metrics_path=args.metrics_path,
        skip_schema=args.skip_schema,
        skip_stock_ingestion=args.skip_stock_ingestion,
        skip_price_ingestion=args.skip_price_ingestion,
        skip_correlations=args.skip_correlations,
        skip_feature_dataset=args.skip_feature_dataset,
        skip_prediction=args.skip_prediction,
        train_model=args.train_model,
    )

    try:
        summary = run_daily_update(settings, config)
    except Exception:
        logger.exception("Daily update pipeline failed")
        return 1

    logger.info("Daily update pipeline succeeded; summary=%s", json.dumps(summary.to_dict()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
