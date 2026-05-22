"""Train a baseline next-period direction forecasting model."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any
import warnings


DATE_COLUMN = "date"
TARGET_COLUMN = "target_next_direction"
CATEGORICAL_FEATURES = ["ticker", "sector"]
NUMERIC_FEATURES = [
    "close",
    "volume",
    "return_1d",
    "return_5d",
    "rolling_mean_5d",
    "rolling_vol_5d",
    "rolling_mean_10d",
    "rolling_vol_10d",
    "sector_return_1d",
    "correlated_peer_count",
    "correlation_avg_abs",
]
FEATURE_COLUMNS = CATEGORICAL_FEATURES + NUMERIC_FEATURES
EXCLUDED_MODEL_COLUMNS = {DATE_COLUMN, "target_next_return", TARGET_COLUMN}


@dataclass(frozen=True)
class TrainingResult:
    """Training summary and persisted artifact locations."""

    model_path: str
    metrics_path: str
    model_type: str
    train_rows: int
    test_rows: int
    train_start_date: str
    train_end_date: str
    test_start_date: str
    test_end_date: str
    metrics: dict[str, float]


def train_direction_model(
    dataset_path: str | Path,
    *,
    model_path: str | Path = "models/direction_model.joblib",
    metrics_path: str | Path = "models/direction_model_metrics.json",
    test_size: float = 0.2,
    random_state: int = 42,
    prefer_lightgbm: bool = True,
) -> TrainingResult:
    """Train and persist a baseline classifier for next-period direction."""

    pd = _require_pandas()
    joblib = _require_joblib()

    dataset = pd.read_csv(dataset_path)
    _validate_dataset(dataset)
    categorical_features, numeric_features = infer_feature_columns(dataset)
    feature_columns = categorical_features + numeric_features
    train_frame, test_frame = split_by_date(dataset, test_size=test_size)

    model, model_type = _build_pipeline(
        random_state=random_state,
        prefer_lightgbm=prefer_lightgbm,
        categorical_features=categorical_features,
        numeric_features=numeric_features,
    )
    model.fit(train_frame[feature_columns], train_frame[TARGET_COLUMN])

    metrics = _evaluate_model(model, test_frame[feature_columns], test_frame[TARGET_COLUMN])
    result = TrainingResult(
        model_path=str(model_path),
        metrics_path=str(metrics_path),
        model_type=model_type,
        train_rows=len(train_frame),
        test_rows=len(test_frame),
        train_start_date=str(train_frame[DATE_COLUMN].min()),
        train_end_date=str(train_frame[DATE_COLUMN].max()),
        test_start_date=str(test_frame[DATE_COLUMN].min()),
        test_end_date=str(test_frame[DATE_COLUMN].max()),
        metrics=metrics,
    )

    model_artifact = {
        "model": model,
        "model_type": model_type,
        "feature_columns": feature_columns,
        "categorical_features": categorical_features,
        "numeric_features": numeric_features,
        "target_column": TARGET_COLUMN,
        "training_result": asdict(result),
    }

    model_output_path = Path(model_path)
    model_output_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model_artifact, model_output_path)

    metrics_output_path = Path(metrics_path)
    metrics_output_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_output_path.write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")

    return result


def split_by_date(dataset: Any, *, test_size: float) -> tuple[Any, Any]:
    """Split a feature dataset chronologically to avoid look-ahead leakage."""

    if test_size <= 0 or test_size >= 1:
        raise ValueError("test_size must be between 0 and 1")

    sorted_dates = sorted(dataset[DATE_COLUMN].dropna().unique())
    if len(sorted_dates) < 3:
        raise ValueError("dataset must contain at least 3 unique dates")

    split_index = int(len(sorted_dates) * (1 - test_size))
    split_index = min(max(split_index, 1), len(sorted_dates) - 1)
    first_test_date = sorted_dates[split_index]

    train_frame = dataset[dataset[DATE_COLUMN] < first_test_date].copy()
    test_frame = dataset[dataset[DATE_COLUMN] >= first_test_date].copy()
    if train_frame.empty or test_frame.empty:
        raise ValueError("date split produced an empty train or test set")

    return train_frame, test_frame


def infer_feature_columns(dataset: Any) -> tuple[list[str], list[str]]:
    """Infer categorical and numeric feature columns from a training dataset."""

    categorical_features = [column for column in CATEGORICAL_FEATURES if column in dataset.columns]
    numeric_features = [
        column
        for column in dataset.columns
        if column not in EXCLUDED_MODEL_COLUMNS
        and column not in categorical_features
        and _is_numeric_series(dataset[column])
    ]
    if not numeric_features:
        raise ValueError("dataset has no numeric feature columns")

    return categorical_features, numeric_features


def _validate_dataset(dataset: Any) -> None:
    required_columns = set(CATEGORICAL_FEATURES + [DATE_COLUMN, TARGET_COLUMN])
    missing_columns = required_columns - set(dataset.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"dataset is missing required columns: {missing}")

    if dataset.empty:
        raise ValueError("dataset is empty")


def _build_pipeline(
    *,
    random_state: int,
    prefer_lightgbm: bool,
    categorical_features: list[str],
    numeric_features: list[str],
) -> tuple[Any, str]:
    from sklearn.compose import ColumnTransformer
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    categorical_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]
    )
    numeric_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )
    preprocessor = ColumnTransformer(
        transformers=[
            ("categorical", categorical_pipeline, categorical_features),
            ("numeric", numeric_pipeline, numeric_features),
        ],
        remainder="drop",
    )

    if prefer_lightgbm:
        try:
            from lightgbm import LGBMClassifier
        except ImportError:
            estimator = RandomForestClassifier(
                n_estimators=200,
                min_samples_leaf=5,
                class_weight="balanced_subsample",
                random_state=random_state,
            )
            return Pipeline([("preprocessor", preprocessor), ("model", estimator)]), "random_forest"

        estimator = LGBMClassifier(
            objective="binary",
            n_estimators=250,
            learning_rate=0.03,
            num_leaves=15,
            subsample=0.9,
            colsample_bytree=0.9,
            random_state=random_state,
            verbosity=-1,
        )
        return Pipeline([("preprocessor", preprocessor), ("model", estimator)]), "lightgbm"

    estimator = RandomForestClassifier(
        n_estimators=200,
        min_samples_leaf=5,
        class_weight="balanced_subsample",
        random_state=random_state,
    )
    return Pipeline([("preprocessor", preprocessor), ("model", estimator)]), "random_forest"


def _evaluate_model(model: Any, features: Any, target: Any) -> dict[str, float]:
    from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="X does not have valid feature names")
        predictions = model.predict(features)
    metrics = {
        "accuracy": round(float(accuracy_score(target, predictions)), 6),
        "precision": round(float(precision_score(target, predictions, zero_division=0)), 6),
        "recall": round(float(recall_score(target, predictions, zero_division=0)), 6),
        "f1": round(float(f1_score(target, predictions, zero_division=0)), 6),
    }

    if len(set(target)) > 1 and hasattr(model, "predict_proba"):
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="X does not have valid feature names")
            probabilities = model.predict_proba(features)[:, 1]
        metrics["roc_auc"] = round(float(roc_auc_score(target, probabilities)), 6)

    return metrics


def _require_pandas() -> Any:
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError(
            "pandas is not installed. Run: .venv\\Scripts\\python.exe -m pip install -e \".[data]\""
        ) from exc

    return pd


def _require_joblib() -> Any:
    try:
        import joblib
    except ImportError as exc:
        raise RuntimeError(
            "joblib is not installed. Run: .venv\\Scripts\\python.exe -m pip install -e \".[ml]\""
        ) from exc

    return joblib


def _is_numeric_series(series: Any) -> bool:
    try:
        return bool(series.dtype.kind in "biufc")
    except AttributeError:
        return False
