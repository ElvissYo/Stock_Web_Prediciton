from types import SimpleNamespace

from kag.config import Settings
from kag.pipeline.daily_update import DailyUpdateConfig, run_daily_update


class FakeNeo4jClient:
    def __init__(self, settings):
        self.settings = settings

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None


def test_run_daily_update_orchestrates_default_lightweight_pipeline(monkeypatch, tmp_path):
    model_path = tmp_path / "direction_model.joblib"
    model_path.write_text("model", encoding="utf-8")
    training_dataset_path = tmp_path / "training_features.csv"
    prediction_output_path = tmp_path / "predictions.csv"

    calls = []

    monkeypatch.setattr("kag.pipeline.daily_update.Neo4jClient", FakeNeo4jClient)
    monkeypatch.setattr("kag.pipeline.daily_update.apply_schema", lambda client: 6)
    monkeypatch.setattr("kag.pipeline.daily_update.load_stock_records", lambda path: ["stock"])
    monkeypatch.setattr(
        "kag.pipeline.daily_update.ingest_stocks",
        lambda client, records: SimpleNamespace(rows_processed=2, sectors_processed=1),
    )
    monkeypatch.setattr("kag.pipeline.daily_update.load_stock_symbols", lambda *args, **kwargs: ["symbol"])
    monkeypatch.setattr(
        "kag.pipeline.daily_update.fetch_historical_prices",
        lambda symbols, **kwargs: ["price_bar"],
    )
    monkeypatch.setattr(
        "kag.pipeline.daily_update.ingest_price_bars",
        lambda client, bars, batch_size: SimpleNamespace(rows_processed=5),
    )
    monkeypatch.setattr(
        "kag.pipeline.daily_update.load_price_observations",
        lambda client, **kwargs: [SimpleNamespace(ticker="BBCA")],
    )
    monkeypatch.setattr(
        "kag.pipeline.daily_update.calculate_return_correlations",
        lambda observations, **kwargs: ["correlation"],
    )
    monkeypatch.setattr(
        "kag.pipeline.daily_update.delete_correlations",
        lambda client, **kwargs: calls.append("delete_correlations"),
    )
    monkeypatch.setattr(
        "kag.pipeline.daily_update.write_correlations",
        lambda client, correlations: SimpleNamespace(relationships_processed=1),
    )
    monkeypatch.setattr(
        "kag.pipeline.daily_update.load_feature_source_rows",
        lambda client, **kwargs: ["source_row"],
    )
    monkeypatch.setattr(
        "kag.pipeline.daily_update.build_training_features",
        lambda source_rows: ["feature_row"],
    )
    monkeypatch.setattr(
        "kag.pipeline.daily_update.export_feature_dataset",
        lambda rows, output_path: 1,
    )
    monkeypatch.setattr("kag.pipeline.daily_update.load_model_artifact", lambda path: {"model": "x"})
    monkeypatch.setattr(
        "kag.pipeline.daily_update.build_latest_inference_features",
        lambda source_rows: ["inference_row"],
    )
    monkeypatch.setattr(
        "kag.pipeline.daily_update.predict_directions",
        lambda artifact, rows: ["prediction"],
    )
    monkeypatch.setattr("kag.pipeline.daily_update.export_predictions", lambda rows, output_path: 1)

    settings = Settings(
        app_env="test",
        log_level="INFO",
        neo4j_uri="bolt://localhost:7687",
        neo4j_username="neo4j",
        neo4j_password="secret",
    )
    config = DailyUpdateConfig(
        model_path=model_path,
        training_dataset_path=training_dataset_path,
        prediction_output_path=prediction_output_path,
    )

    summary = run_daily_update(settings, config)

    assert summary.schema_statements == 6
    assert summary.stock_rows == 2
    assert summary.stock_sectors == 1
    assert summary.price_rows == 5
    assert summary.correlation_rows == 1
    assert summary.feature_rows == 1
    assert summary.prediction_rows == 1
    assert summary.trained_model is False
    assert "model_training" in summary.skipped_steps
    assert calls == ["delete_correlations"]
