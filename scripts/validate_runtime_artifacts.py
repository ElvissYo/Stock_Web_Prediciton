from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


REQUIRED_FILES = [
    "models/global_model_with_nlp.joblib",
    "reports/metrics.json",
    "data/prices_full_top100.parquet",
    "data/final_dataset.parquet",
    "data/processed/price_features.parquet",
    "data/processed/global_model_predictions.parquet",
    "data/news_raw.parquet",
    "data/nlp_features.parquet",
]


def assert_file_exists(path_str: str) -> None:
    path = Path(path_str)
    if not path.exists():
        raise FileNotFoundError(f"Missing required artifact: {path_str}")
    if path.is_file() and path.stat().st_size <= 0:
        raise ValueError(f"Artifact exists but is empty: {path_str}")


def validate_parquet(path_str: str) -> None:
    df = pd.read_parquet(path_str)
    if df.empty:
        raise ValueError(f"Parquet file is empty: {path_str}")


def validate_metrics(path_str: str) -> None:
    with open(path_str, "r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError("reports/metrics.json must contain a JSON object")


def main() -> None:
    for file_path in REQUIRED_FILES:
        assert_file_exists(file_path)

    for file_path in REQUIRED_FILES:
        if file_path.endswith(".parquet"):
            validate_parquet(file_path)

    validate_metrics("reports/metrics.json")

    predictions = pd.read_parquet("data/processed/global_model_predictions.parquet")
    required_prediction_columns = {"ticker"}

    missing_columns = required_prediction_columns - set(predictions.columns)
    if missing_columns:
        raise ValueError(
            "Prediction artifact missing required columns: "
            + ", ".join(sorted(missing_columns))
        )

    print("Runtime artifact validation passed.")


if __name__ == "__main__":
    main()