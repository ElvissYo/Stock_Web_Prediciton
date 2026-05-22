"""Orchestrate an incremental KAG market update pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import logging
from pathlib import Path
from typing import Any

from kag.config import Settings
from kag.features.training_dataset import (
    build_latest_inference_features,
    build_training_features,
    export_feature_dataset,
    load_feature_source_rows,
)
from kag.graph.client import Neo4jClient
from kag.graph.correlations import (
    calculate_return_correlations,
    delete_correlations,
    load_price_observations,
    write_correlations,
)
from kag.graph.schema import apply_schema
from kag.ingestion.prices import ingest_price_bars
from kag.ingestion.stocks import ingest_stocks, load_stock_records
from kag.market_data.symbols import load_stock_symbols
from kag.market_data.yfinance_provider import fetch_historical_prices
from kag.modeling.direction_model import train_direction_model
from kag.modeling.inference import export_predictions, load_model_artifact, predict_directions


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DailyUpdateConfig:
    """Configuration for local/scheduled incremental update runs."""

    stock_csv: Path = Path("data/seeds/idx_stock_universe.csv")
    price_period: str = "1mo"
    price_interval: str = "1d"
    price_start: str | None = None
    price_end: str | None = None
    tickers: list[str] | None = None
    limit: int | None = None
    batch_size: int = 1000
    min_correlation_observations: int = 20
    min_abs_correlation: float = 0.3
    training_dataset_path: Path = Path("data/processed/training_features.csv")
    prediction_output_path: Path = Path("data/processed/latest_direction_predictions.csv")
    model_path: Path = Path("models/direction_model.joblib")
    metrics_path: Path = Path("models/direction_model_metrics.json")
    skip_schema: bool = False
    skip_stock_ingestion: bool = False
    skip_price_ingestion: bool = False
    skip_correlations: bool = False
    skip_feature_dataset: bool = False
    skip_prediction: bool = False
    train_model: bool = False


@dataclass(frozen=True)
class DailyUpdateSummary:
    """Structured summary from a daily update run."""

    schema_statements: int = 0
    stock_rows: int = 0
    stock_sectors: int = 0
    price_rows: int = 0
    correlation_rows: int = 0
    feature_rows: int = 0
    trained_model: bool = False
    prediction_rows: int = 0
    skipped_steps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_daily_update(settings: Settings, config: DailyUpdateConfig) -> DailyUpdateSummary:
    """Run the incremental update pipeline against Neo4j and local artifacts."""

    skipped_steps: list[str] = []
    schema_statements = 0
    stock_rows = 0
    stock_sectors = 0
    price_rows = 0
    correlation_rows = 0
    feature_rows = 0
    trained_model = False
    prediction_rows = 0

    with Neo4jClient(settings) as client:
        if config.skip_schema:
            skipped_steps.append("schema")
        else:
            schema_statements = apply_schema(client)
            logger.info("Applied schema; statements=%s", schema_statements)

        if config.skip_stock_ingestion:
            skipped_steps.append("stock_ingestion")
        else:
            stock_records = load_stock_records(config.stock_csv)
            stock_result = ingest_stocks(client, stock_records)
            stock_rows = stock_result.rows_processed
            stock_sectors = stock_result.sectors_processed
            logger.info("Ingested stock universe; rows=%s sectors=%s", stock_rows, stock_sectors)

        if config.skip_price_ingestion:
            skipped_steps.append("price_ingestion")
        else:
            symbols = load_stock_symbols(client, tickers=config.tickers, limit=config.limit)
            price_bars = fetch_historical_prices(
                symbols,
                period=config.price_period,
                interval=config.price_interval,
                start=config.price_start,
                end=config.price_end,
            )
            price_result = ingest_price_bars(client, price_bars, batch_size=config.batch_size)
            price_rows = price_result.rows_processed
            logger.info("Ingested historical prices; rows=%s", price_rows)

        if config.skip_correlations:
            skipped_steps.append("correlations")
        else:
            observations = load_price_observations(
                client,
                tickers=config.tickers,
                interval=config.price_interval,
            )
            correlations = calculate_return_correlations(
                observations,
                min_observations=config.min_correlation_observations,
                min_abs_correlation=config.min_abs_correlation,
                interval=config.price_interval,
            )
            correlation_tickers = sorted({observation.ticker for observation in observations})
            delete_correlations(
                client,
                tickers=correlation_tickers,
                method="pearson_close_return",
                price_source="yfinance",
                interval=config.price_interval,
            )
            correlation_result = write_correlations(client, correlations)
            correlation_rows = correlation_result.relationships_processed
            logger.info("Built stock correlations; rows=%s", correlation_rows)

        if config.skip_feature_dataset and config.skip_prediction:
            source_rows = []
        else:
            source_rows = load_feature_source_rows(
                client,
                tickers=config.tickers,
                interval=config.price_interval,
            )

    if config.skip_feature_dataset:
        skipped_steps.append("feature_dataset")
    else:
        feature_rows_data = build_training_features(source_rows)
        feature_rows = export_feature_dataset(feature_rows_data, config.training_dataset_path)
        logger.info("Exported feature dataset; rows=%s", feature_rows)

    if config.train_model:
        train_direction_model(
            config.training_dataset_path,
            model_path=config.model_path,
            metrics_path=config.metrics_path,
        )
        trained_model = True
        logger.info("Trained direction model; model=%s", config.model_path)
    else:
        skipped_steps.append("model_training")

    if config.skip_prediction:
        skipped_steps.append("prediction")
    elif config.model_path.exists():
        artifact = load_model_artifact(config.model_path)
        inference_rows = build_latest_inference_features(source_rows)
        predictions = predict_directions(artifact, inference_rows)
        prediction_rows = export_predictions(predictions, config.prediction_output_path)
        logger.info("Exported latest predictions; rows=%s", prediction_rows)
    else:
        skipped_steps.append("prediction_missing_model")
        logger.warning("Skipping prediction because model artifact is missing: %s", config.model_path)

    return DailyUpdateSummary(
        schema_statements=schema_statements,
        stock_rows=stock_rows,
        stock_sectors=stock_sectors,
        price_rows=price_rows,
        correlation_rows=correlation_rows,
        feature_rows=feature_rows,
        trained_model=trained_model,
        prediction_rows=prediction_rows,
        skipped_steps=skipped_steps,
    )
