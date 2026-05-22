import csv

import pytest

from kag.features.training_dataset import InferenceFeatureRow
from kag.modeling.inference import DirectionPrediction, export_predictions, predict_directions


class DummyModel:
    def predict_proba(self, features):
        return [[0.2, 0.8] for _ in range(len(features))]

    def predict(self, features):
        return [1 for _ in range(len(features))]


def test_predict_directions_uses_model_artifact():
    pytest.importorskip("pandas")
    artifact = {"model": DummyModel(), "model_type": "dummy", "feature_columns": []}
    feature_rows = [
        InferenceFeatureRow(
            ticker="BBCA",
            date="2026-05-22",
            sector="Financials",
            close=9000.0,
            volume=1000,
            return_1d=0.01,
            return_5d=0.02,
            rolling_mean_5d=0.01,
            rolling_vol_5d=0.02,
            rolling_mean_10d=0.01,
            rolling_vol_10d=0.02,
            sector_return_1d=0.01,
            correlated_peer_count=3,
            correlation_avg_abs=0.5,
        )
    ]

    predictions = predict_directions(artifact, feature_rows)

    assert predictions == [
        DirectionPrediction(
            ticker="BBCA",
            date="2026-05-22",
            sector="Financials",
            close=9000.0,
            probability_up=0.8,
            predicted_direction=1,
            model_type="dummy",
        )
    ]


def test_export_predictions_writes_csv(tmp_path):
    output_path = tmp_path / "predictions.csv"
    predictions = [
        DirectionPrediction(
            ticker="BBCA",
            date="2026-05-22",
            sector="Financials",
            close=9000.0,
            probability_up=0.8,
            predicted_direction=1,
            model_type="dummy",
        )
    ]

    exported_rows = export_predictions(predictions, output_path)

    with output_path.open("r", encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))

    assert exported_rows == 1
    assert rows[0]["ticker"] == "BBCA"


def test_export_predictions_rejects_empty_rows(tmp_path):
    with pytest.raises(ValueError, match="No predictions"):
        export_predictions([], tmp_path / "predictions.csv")

