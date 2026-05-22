"""Prediction utilities for trained direction models."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable
import warnings

from kag.features.training_dataset import InferenceFeatureRow
from kag.modeling.direction_model import FEATURE_COLUMNS


@dataclass(frozen=True)
class DirectionPrediction:
    """One stock direction prediction."""

    ticker: str
    date: str
    sector: str
    close: float
    probability_up: float
    predicted_direction: int
    model_type: str

    def to_csv_row(self) -> dict[str, str | int | float]:
        return asdict(self)


def load_model_artifact(model_path: str | Path) -> dict[str, Any]:
    """Load a persisted model artifact."""

    joblib = _require_joblib()
    artifact = joblib.load(model_path)
    if "model" not in artifact or "feature_columns" not in artifact:
        raise ValueError(f"Invalid model artifact: {model_path}")

    return artifact


def predict_directions(
    artifact: dict[str, Any],
    feature_rows: Iterable[InferenceFeatureRow],
) -> list[DirectionPrediction]:
    """Generate direction predictions from latest feature rows."""

    pd = _require_pandas()
    rows = list(feature_rows)
    if not rows:
        return []

    model = artifact["model"]
    model_type = artifact.get("model_type", "unknown")
    feature_columns = artifact.get("feature_columns") or FEATURE_COLUMNS
    feature_frame = pd.DataFrame([row.to_model_row() for row in rows])

    for column in feature_columns:
        if column not in feature_frame.columns:
            raise ValueError(f"Missing model feature column: {column}")

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="X does not have valid feature names")
        probabilities = [row[1] for row in model.predict_proba(feature_frame[feature_columns])]
        predictions = model.predict(feature_frame[feature_columns])

    return [
        DirectionPrediction(
            ticker=row.ticker,
            date=row.date,
            sector=row.sector,
            close=row.close,
            probability_up=round(float(probability), 6),
            predicted_direction=int(prediction),
            model_type=model_type,
        )
        for row, probability, prediction in zip(rows, probabilities, predictions, strict=True)
    ]


def export_predictions(predictions: Iterable[DirectionPrediction], output_path: str | Path) -> int:
    """Write predictions to CSV and return row count."""

    rows = [prediction.to_csv_row() for prediction in predictions]
    if not rows:
        raise ValueError("No predictions to export")

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    return len(rows)


def _require_joblib() -> Any:
    try:
        import joblib
    except ImportError as exc:
        raise RuntimeError(
            "joblib is not installed. Run: .venv\\Scripts\\python.exe -m pip install -e \".[ml]\""
        ) from exc

    return joblib


def _require_pandas() -> Any:
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError(
            "pandas is not installed. Run: .venv\\Scripts\\python.exe -m pip install -e \".[data]\""
        ) from exc

    return pd
