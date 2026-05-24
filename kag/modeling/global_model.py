"""Single global stock return model and A/B evaluation utilities."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
from typing import Any
import warnings

from kag.features.fusion import nlp_feature_columns


DATE_COLUMN = "date"
RETURN_TARGET = "target_return"
PRICE_TARGET = "next_day_price"
DIRECTION_TARGET = "direction"
MARKET_RETURN_TARGET = "market_next_return"
EXCESS_RETURN_TARGET = "target_excess_return"
MARKET_OUTPERFORM_TARGET = "outperform_market"
SECTOR_RETURN_TARGET = "sector_next_return"
SECTOR_EXCESS_RETURN_TARGET = "target_sector_excess_return"
SECTOR_OUTPERFORM_TARGET = "outperform_sector"
CATEGORICAL_FEATURES = ["ticker", "sector"]
NON_FEATURE_COLUMNS = {
    DATE_COLUMN,
    RETURN_TARGET,
    PRICE_TARGET,
    DIRECTION_TARGET,
    MARKET_RETURN_TARGET,
    EXCESS_RETURN_TARGET,
    MARKET_OUTPERFORM_TARGET,
    SECTOR_RETURN_TARGET,
    SECTOR_EXCESS_RETURN_TARGET,
    SECTOR_OUTPERFORM_TARGET,
    "name",
    "yfinance_symbol",
    "source",
    "interval",
}


@dataclass(frozen=True)
class GlobalModelResult:
    """Training and evaluation summary for a global return model."""

    model_name: str
    model_type: str
    include_nlp: bool
    target_column: str
    include_direction_classifier: bool
    direction_model_type: str | None
    model_path: str
    artifact_path: str
    train_rows: int
    evaluation_rows: int
    feature_count: int
    train_start_date: str
    train_end_date: str
    cv_gap_dates: int
    selection_top_n: int
    metrics: dict[str, float | int]
    direction_metrics: dict[str, float | int]
    top_feature_importance: list[dict[str, float | str]]


def train_global_return_model(
    dataset_path: str | Path,
    *,
    include_nlp: bool,
    model_name: str,
    model_output_path: str | Path,
    metrics_output_path: str | Path | None = None,
    feature_importance_output_path: str | Path | None = None,
    predictions_output_path: str | Path | None = None,
    target_column: str = RETURN_TARGET,
    n_splits: int = 5,
    cv_gap_dates: int = 1,
    selection_top_n: int = 10,
    random_state: int = 42,
    prefer_lightgbm: bool = True,
    train_direction_classifier: bool = True,
) -> GlobalModelResult:
    """Train one global next-day return model across all ticker rows."""

    pd = _require_pandas()
    joblib = _require_joblib()

    dataset = pd.read_parquet(dataset_path)
    training_frame = _training_rows(dataset, target_column=target_column)
    categorical_features, numeric_features = infer_feature_columns(
        training_frame,
        include_nlp=include_nlp,
    )
    feature_columns = categorical_features + numeric_features

    cv_metrics = evaluate_time_series_cv(
        training_frame,
        feature_columns=feature_columns,
        categorical_features=categorical_features,
        numeric_features=numeric_features,
        target_column=target_column,
        n_splits=n_splits,
        gap_dates=cv_gap_dates,
        selection_top_n=selection_top_n,
        random_state=random_state,
        prefer_lightgbm=prefer_lightgbm,
    )

    model, model_type = build_regression_pipeline(
        categorical_features=categorical_features,
        numeric_features=numeric_features,
        random_state=random_state,
        prefer_lightgbm=prefer_lightgbm,
    )
    model.fit(training_frame[feature_columns], training_frame[target_column])

    direction_model = None
    direction_model_type = None
    direction_metrics: dict[str, float | int] = {}
    if train_direction_classifier:
        direction_frame = training_frame.dropna(subset=[DIRECTION_TARGET]).copy()
        if not direction_frame.empty and direction_frame[DIRECTION_TARGET].nunique() > 1:
            direction_metrics = evaluate_direction_time_series_cv(
                direction_frame,
                feature_columns=feature_columns,
                categorical_features=categorical_features,
                numeric_features=numeric_features,
                n_splits=n_splits,
                gap_dates=cv_gap_dates,
                random_state=random_state,
                prefer_lightgbm=prefer_lightgbm,
            )
            direction_model, direction_model_type = build_classification_pipeline(
                categorical_features=categorical_features,
                numeric_features=numeric_features,
                random_state=random_state,
                prefer_lightgbm=prefer_lightgbm,
            )
            direction_model.fit(
                direction_frame[feature_columns],
                direction_frame[DIRECTION_TARGET].astype(int),
            )
            cv_metrics.update(
                {
                    f"direction_classifier_{key}": value
                    for key, value in direction_metrics.items()
                }
            )

    feature_importance = extract_feature_importance(model)[:20]
    artifact_path = persist_model_artifact(
        model,
        Path(model_output_path),
        {
            "model": model,
            "model_name": model_name,
            "model_type": model_type,
            "direction_model": direction_model,
            "direction_model_type": direction_model_type,
            "include_nlp": include_nlp,
            "feature_columns": feature_columns,
            "categorical_features": categorical_features,
            "numeric_features": numeric_features,
            "target_column": target_column,
            "cv_gap_dates": cv_gap_dates,
            "selection_top_n": selection_top_n,
        },
        joblib=joblib,
    )

    if feature_importance_output_path is not None:
        write_feature_importance_plot(feature_importance, feature_importance_output_path)

    if predictions_output_path is not None:
        predictions = predict_latest_returns(
            model,
            dataset,
            feature_columns=feature_columns,
            model_name=model_name,
            model_type=model_type,
            direction_model=direction_model,
        )
        write_predictions_parquet(predictions, predictions_output_path)

    result = GlobalModelResult(
        model_name=model_name,
        model_type=model_type,
        include_nlp=include_nlp,
        target_column=target_column,
        include_direction_classifier=direction_model is not None,
        direction_model_type=direction_model_type,
        model_path=str(model_output_path),
        artifact_path=str(artifact_path),
        train_rows=len(training_frame),
        evaluation_rows=int(cv_metrics["evaluation_rows"]),
        feature_count=len(feature_columns),
        train_start_date=str(training_frame[DATE_COLUMN].min().date()),
        train_end_date=str(training_frame[DATE_COLUMN].max().date()),
        cv_gap_dates=cv_gap_dates,
        selection_top_n=selection_top_n,
        metrics=cv_metrics,
        direction_metrics=direction_metrics,
        top_feature_importance=feature_importance,
    )

    if metrics_output_path is not None:
        path = Path(metrics_output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")

    return result


def evaluate_time_series_cv(
    frame: Any,
    *,
    feature_columns: list[str],
    categorical_features: list[str],
    numeric_features: list[str],
    target_column: str = RETURN_TARGET,
    n_splits: int = 5,
    gap_dates: int = 1,
    selection_top_n: int = 10,
    random_state: int = 42,
    prefer_lightgbm: bool = True,
) -> dict[str, float | int]:
    """Evaluate a return model with TimeSeriesSplit over unique trading dates."""

    pd = _require_pandas()
    np = _require_numpy()
    from sklearn.model_selection import TimeSeriesSplit

    dataset = frame.sort_values([DATE_COLUMN, "ticker"]).copy()
    if target_column not in dataset.columns:
        raise ValueError(f"dataset is missing target column: {target_column}")
    if gap_dates < 0:
        raise ValueError("gap_dates must be zero or greater")
    if selection_top_n < 1:
        raise ValueError("selection_top_n must be at least 1")

    unique_dates = pd.Series(dataset[DATE_COLUMN].dropna().unique()).sort_values().to_numpy()
    if len(unique_dates) < 3:
        raise ValueError("dataset must contain at least 3 unique dates for time-series evaluation")

    effective_splits = min(max(2, n_splits), len(unique_dates) - 1)
    splitter = TimeSeriesSplit(n_splits=effective_splits)

    fold_metrics = []
    for train_date_indices, test_date_indices in splitter.split(unique_dates):
        first_test_index = int(min(test_date_indices))
        allowed_train_indices = [
            int(index) for index in train_date_indices if int(index) < first_test_index - gap_dates
        ]
        if not allowed_train_indices:
            continue

        train_dates = set(unique_dates[allowed_train_indices])
        test_dates = set(unique_dates[test_date_indices])
        train_frame = dataset[dataset[DATE_COLUMN].isin(train_dates)]
        test_frame = dataset[dataset[DATE_COLUMN].isin(test_dates)]
        if train_frame.empty or test_frame.empty:
            continue

        model, _ = build_regression_pipeline(
            categorical_features=categorical_features,
            numeric_features=numeric_features,
            random_state=random_state,
            prefer_lightgbm=prefer_lightgbm,
        )
        model.fit(train_frame[feature_columns], train_frame[target_column])
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="X does not have valid feature names")
            predicted_values = model.predict(test_frame[feature_columns])
        fold_metrics.append(
            _regression_metrics(
                test_frame,
                predicted_values,
                target_column=target_column,
                selection_top_n=selection_top_n,
                np=np,
                pd=pd,
            )
        )

    if not fold_metrics:
        raise ValueError("time-series evaluation produced no valid folds")

    metrics = {
        "mape": _mean_metric(fold_metrics, "mape", np=np),
        "rmse": _mean_metric(fold_metrics, "rmse", np=np),
        "mae": _mean_metric(fold_metrics, "mae", np=np),
        "target_rmse": _mean_metric(fold_metrics, "target_rmse", np=np),
        "target_mae": _mean_metric(fold_metrics, "target_mae", np=np),
        "directional_accuracy": _mean_metric(fold_metrics, "directional_accuracy", np=np),
        "up_precision": _mean_metric(fold_metrics, "up_precision", np=np),
        "down_precision": _mean_metric(fold_metrics, "down_precision", np=np),
        "rank_ic": _mean_metric(fold_metrics, "rank_ic", np=np),
        "top_n_avg_return": _mean_metric(fold_metrics, "top_n_avg_return", np=np),
        "top_n_hit_rate": _mean_metric(fold_metrics, "top_n_hit_rate", np=np),
        "top_n_excess_return": _mean_metric(fold_metrics, "top_n_excess_return", np=np),
        "top_n_outperform_rate": _mean_metric(fold_metrics, "top_n_outperform_rate", np=np),
        "long_short_return": _mean_metric(fold_metrics, "long_short_return", np=np),
        "folds": len(fold_metrics),
        "evaluation_rows": int(sum(metric["rows"] for metric in fold_metrics)),
        "selection_dates": int(sum(metric["selection_dates"] for metric in fold_metrics)),
        "gap_dates": gap_dates,
        "selection_top_n": selection_top_n,
    }
    return metrics


def evaluate_direction_time_series_cv(
    frame: Any,
    *,
    feature_columns: list[str],
    categorical_features: list[str],
    numeric_features: list[str],
    n_splits: int = 5,
    gap_dates: int = 1,
    random_state: int = 42,
    prefer_lightgbm: bool = True,
) -> dict[str, float | int]:
    """Evaluate a direction classifier with the same purged date splits."""

    pd = _require_pandas()
    np = _require_numpy()
    from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
    from sklearn.model_selection import TimeSeriesSplit

    dataset = frame.sort_values([DATE_COLUMN, "ticker"]).dropna(subset=[DIRECTION_TARGET]).copy()
    dataset[DIRECTION_TARGET] = dataset[DIRECTION_TARGET].astype(int)
    if dataset[DIRECTION_TARGET].nunique() < 2:
        raise ValueError("direction target must contain at least two classes")

    unique_dates = pd.Series(dataset[DATE_COLUMN].dropna().unique()).sort_values().to_numpy()
    if len(unique_dates) < 3:
        raise ValueError("dataset must contain at least 3 unique dates for direction evaluation")

    effective_splits = min(max(2, n_splits), len(unique_dates) - 1)
    splitter = TimeSeriesSplit(n_splits=effective_splits)
    fold_metrics = []

    for train_date_indices, test_date_indices in splitter.split(unique_dates):
        first_test_index = int(min(test_date_indices))
        allowed_train_indices = [
            int(index) for index in train_date_indices if int(index) < first_test_index - gap_dates
        ]
        if not allowed_train_indices:
            continue

        train_dates = set(unique_dates[allowed_train_indices])
        test_dates = set(unique_dates[test_date_indices])
        train_frame = dataset[dataset[DATE_COLUMN].isin(train_dates)]
        test_frame = dataset[dataset[DATE_COLUMN].isin(test_dates)]
        if train_frame.empty or test_frame.empty or train_frame[DIRECTION_TARGET].nunique() < 2:
            continue

        classifier, _ = build_classification_pipeline(
            categorical_features=categorical_features,
            numeric_features=numeric_features,
            random_state=random_state,
            prefer_lightgbm=prefer_lightgbm,
        )
        classifier.fit(train_frame[feature_columns], train_frame[DIRECTION_TARGET])
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="X does not have valid feature names")
            predictions = classifier.predict(test_frame[feature_columns])
            probabilities = classifier.predict_proba(test_frame[feature_columns])[:, 1]

        target = test_frame[DIRECTION_TARGET]
        metric = {
            "accuracy": float(accuracy_score(target, predictions)),
            "precision": float(precision_score(target, predictions, zero_division=0)),
            "recall": float(recall_score(target, predictions, zero_division=0)),
            "f1": float(f1_score(target, predictions, zero_division=0)),
            "rows": int(len(test_frame)),
        }
        if target.nunique() > 1:
            metric["roc_auc"] = float(roc_auc_score(target, probabilities))
        fold_metrics.append(metric)

    if not fold_metrics:
        raise ValueError("direction evaluation produced no valid folds")

    return {
        "accuracy": _mean_metric(fold_metrics, "accuracy", np=np),
        "precision": _mean_metric(fold_metrics, "precision", np=np),
        "recall": _mean_metric(fold_metrics, "recall", np=np),
        "f1": _mean_metric(fold_metrics, "f1", np=np),
        "roc_auc": _mean_metric(fold_metrics, "roc_auc", np=np),
        "folds": len(fold_metrics),
        "evaluation_rows": int(sum(metric["rows"] for metric in fold_metrics)),
        "gap_dates": gap_dates,
    }


def infer_feature_columns(frame: Any, *, include_nlp: bool) -> tuple[list[str], list[str]]:
    """Infer model features while keeping the global model single-artifact."""

    nlp_columns = set(nlp_feature_columns())
    categorical_features = [column for column in CATEGORICAL_FEATURES if column in frame.columns]
    numeric_features = []
    for column in frame.columns:
        if column in NON_FEATURE_COLUMNS or column in categorical_features:
            continue
        if not include_nlp and column in nlp_columns:
            continue
        if _is_numeric_series(frame[column]):
            numeric_features.append(column)

    if not numeric_features:
        raise ValueError("dataset has no numeric feature columns")
    return categorical_features, numeric_features


def build_regression_pipeline(
    *,
    categorical_features: list[str],
    numeric_features: list[str],
    random_state: int,
    prefer_lightgbm: bool,
) -> tuple[Any, str]:
    """Build a sklearn pipeline around LightGBM with a sklearn fallback."""

    from sklearn.compose import ColumnTransformer
    from sklearn.ensemble import RandomForestRegressor
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
            ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
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
            from lightgbm import LGBMRegressor

            estimator = LGBMRegressor(
                objective="regression",
                n_estimators=400,
                learning_rate=0.03,
                num_leaves=31,
                subsample=0.9,
                colsample_bytree=0.9,
                random_state=random_state,
                verbosity=-1,
            )
            return Pipeline([("preprocessor", preprocessor), ("model", estimator)]), "lightgbm"
        except ImportError:
            pass

    estimator = RandomForestRegressor(
        n_estimators=250,
        min_samples_leaf=5,
        random_state=random_state,
        n_jobs=-1,
    )
    return Pipeline([("preprocessor", preprocessor), ("model", estimator)]), "random_forest"


def build_classification_pipeline(
    *,
    categorical_features: list[str],
    numeric_features: list[str],
    random_state: int,
    prefer_lightgbm: bool,
) -> tuple[Any, str]:
    """Build a classifier for next-day direction using the same feature surface."""

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
            ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
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

            estimator = LGBMClassifier(
                objective="binary",
                n_estimators=300,
                learning_rate=0.03,
                num_leaves=15,
                subsample=0.9,
                colsample_bytree=0.9,
                class_weight="balanced",
                random_state=random_state,
                verbosity=-1,
            )
            return Pipeline([("preprocessor", preprocessor), ("model", estimator)]), "lightgbm"
        except ImportError:
            pass

    estimator = RandomForestClassifier(
        n_estimators=250,
        min_samples_leaf=5,
        class_weight="balanced_subsample",
        random_state=random_state,
        n_jobs=-1,
    )
    return Pipeline([("preprocessor", preprocessor), ("model", estimator)]), "random_forest"


def predict_latest_returns(
    model: Any,
    dataset: Any,
    *,
    feature_columns: list[str],
    model_name: str,
    model_type: str,
    direction_model: Any | None = None,
) -> Any:
    """Predict next-day returns for the latest feature row of each ticker."""

    pd = _require_pandas()
    np = _require_numpy()

    frame = dataset.copy()
    frame[DATE_COLUMN] = pd.to_datetime(frame[DATE_COLUMN], errors="coerce").dt.normalize()
    latest_rows = (
        frame.dropna(subset=["ticker", DATE_COLUMN, "close"])
        .sort_values(["ticker", DATE_COLUMN])
        .groupby("ticker", as_index=False)
        .tail(1)
        .copy()
    )
    if latest_rows.empty:
        return pd.DataFrame()

    for column in feature_columns:
        if column not in latest_rows.columns:
            latest_rows[column] = np.nan

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="X does not have valid feature names")
        predicted_returns = model.predict(latest_rows[feature_columns])

    if direction_model is not None:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="X does not have valid feature names")
            direction_probabilities = direction_model.predict_proba(latest_rows[feature_columns])[:, 1]
            predicted_directions = direction_model.predict(latest_rows[feature_columns]).astype(int)
        confidence = pd.Series(abs(direction_probabilities - 0.5) * 2, index=latest_rows.index).clip(
            upper=1.0
        )
    else:
        volatility = latest_rows.get("volatility_20d")
        if volatility is None:
            volatility = pd.Series([0.02] * len(latest_rows), index=latest_rows.index)
        confidence = (
            abs(pd.Series(predicted_returns, index=latest_rows.index))
            / volatility.abs().replace(0, np.nan).fillna(0.02)
        ).clip(upper=1.0)
        predicted_directions = (predicted_returns > 0).astype(int)
        direction_probabilities = [None] * len(latest_rows)

    predictions = pd.DataFrame(
        {
            "ticker": latest_rows["ticker"].values,
            "date": latest_rows[DATE_COLUMN].dt.strftime("%Y-%m-%d").values,
            "sector": latest_rows.get("sector", "UNKNOWN"),
            "close": latest_rows["close"].values,
            "predicted_return": predicted_returns,
            "predicted_direction": predicted_directions,
            "probability_up": direction_probabilities,
            "confidence": confidence.values,
            "model_name": model_name,
            "model_type": model_type,
        }
    )
    return predictions.sort_values("predicted_return", ascending=False).reset_index(drop=True)


def write_predictions_parquet(predictions: Any, output_path: str | Path) -> int:
    """Write latest global model predictions to Parquet."""

    if predictions.empty:
        raise ValueError("No predictions to write")

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        predictions.to_parquet(path, index=False)
    except ImportError as exc:
        raise RuntimeError(
            "Parquet support is not installed. Run: .venv\\Scripts\\python.exe -m pip install -e \".[data]\""
        ) from exc
    return len(predictions)


def persist_model_artifact(
    model: Any,
    model_path: Path,
    artifact: dict[str, Any],
    *,
    joblib: Any,
) -> Path:
    """Persist a runnable joblib artifact plus a LightGBM text model when possible."""

    model_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path = model_path if model_path.suffix == ".joblib" else model_path.with_suffix(".joblib")
    joblib.dump(artifact, artifact_path)

    estimator = model.named_steps["model"]
    if model_path.suffix != ".joblib":
        if hasattr(estimator, "booster_"):
            estimator.booster_.save_model(str(model_path))
        else:
            model_path.write_text(
                "The runnable sklearn pipeline is stored in "
                f"{artifact_path.as_posix()}. This text file records the requested model slot.",
                encoding="utf-8",
            )

    return artifact_path


def extract_feature_importance(model: Any) -> list[dict[str, float | str]]:
    """Extract sorted feature importances from the fitted estimator."""

    estimator = model.named_steps["model"]
    if not hasattr(estimator, "feature_importances_"):
        return []

    preprocessor = model.named_steps["preprocessor"]
    try:
        feature_names = list(preprocessor.get_feature_names_out())
    except Exception:
        feature_names = [f"feature_{index}" for index in range(len(estimator.feature_importances_))]

    rows = [
        {
            "feature": _clean_feature_name(name),
            "importance": float(importance),
        }
        for name, importance in zip(feature_names, estimator.feature_importances_, strict=False)
    ]
    rows.sort(key=lambda row: float(row["importance"]), reverse=True)
    return rows


def write_feature_importance_plot(
    feature_importance: list[dict[str, float | str]],
    output_path: str | Path,
) -> None:
    """Write a top-feature-importance PNG for reports."""

    if not feature_importance:
        return

    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError(
            "matplotlib is not installed. Run: .venv\\Scripts\\python.exe -m pip install -e \".[ml]\""
        ) from exc

    rows = list(reversed(feature_importance[:20]))
    labels = [str(row["feature"]) for row in rows]
    values = [float(row["importance"]) for row in rows]

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, 7))
    ax.barh(labels, values, color="#2563eb")
    ax.set_title("Top 20 Feature Importance")
    ax.set_xlabel("Importance")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def build_model_comparison(
    baseline_result: dict[str, Any],
    nlp_result: dict[str, Any],
) -> dict[str, Any]:
    """Build A/B comparison metrics between baseline and NLP global models."""

    baseline_metrics = baseline_result.get("metrics", {})
    nlp_metrics = nlp_result.get("metrics", {})
    baseline_mape = float(baseline_metrics.get("mape", 0.0) or 0.0)
    nlp_mape = float(nlp_metrics.get("mape", 0.0) or 0.0)
    improvement = 0.0
    if baseline_mape:
        improvement = ((baseline_mape - nlp_mape) / baseline_mape) * 100
    baseline_directional_accuracy = baseline_metrics.get("directional_accuracy")
    nlp_directional_accuracy = nlp_metrics.get("directional_accuracy")
    baseline_direction_classifier_accuracy = baseline_metrics.get("direction_classifier_accuracy")
    nlp_direction_classifier_accuracy = nlp_metrics.get("direction_classifier_accuracy")
    baseline_top_n_excess_return = float(baseline_metrics.get("top_n_excess_return", 0.0) or 0.0)
    nlp_top_n_excess_return = float(nlp_metrics.get("top_n_excess_return", 0.0) or 0.0)
    baseline_rank_ic = float(baseline_metrics.get("rank_ic", 0.0) or 0.0)
    nlp_rank_ic = float(nlp_metrics.get("rank_ic", 0.0) or 0.0)

    return {
        "baseline": baseline_result,
        "nlp_model": nlp_result,
        "comparison": {
            "baseline_mape": baseline_mape,
            "nlp_model_mape": nlp_mape,
            "mape_improvement_pct": round(improvement, 6),
            "baseline_directional_accuracy": baseline_directional_accuracy,
            "nlp_directional_accuracy": nlp_directional_accuracy,
            "directional_accuracy_delta": _numeric_delta(
                nlp_directional_accuracy,
                baseline_directional_accuracy,
            ),
            "baseline_direction_classifier_accuracy": baseline_direction_classifier_accuracy,
            "nlp_direction_classifier_accuracy": nlp_direction_classifier_accuracy,
            "direction_classifier_accuracy_delta": _numeric_delta(
                nlp_direction_classifier_accuracy,
                baseline_direction_classifier_accuracy,
            ),
            "baseline_rank_ic": baseline_rank_ic,
            "nlp_rank_ic": nlp_rank_ic,
            "rank_ic_delta": round(nlp_rank_ic - baseline_rank_ic, 6),
            "baseline_top_n_excess_return": baseline_top_n_excess_return,
            "nlp_top_n_excess_return": nlp_top_n_excess_return,
            "top_n_excess_return_delta": round(
                nlp_top_n_excess_return - baseline_top_n_excess_return,
                6,
            ),
            "nlp_helped": nlp_mape < baseline_mape if baseline_mape else False,
        },
    }


def write_model_comparison_markdown(payload: dict[str, Any], output_path: str | Path) -> None:
    """Write a human-readable A/B comparison report."""

    comparison = payload["comparison"]
    helped = "Yes" if comparison["nlp_helped"] else "No"
    lines = [
        "# Baseline vs NLP Global Model",
        "",
        f"- Baseline MAPE: {comparison['baseline_mape']:.6f}",
        f"- NLP Model MAPE: {comparison['nlp_model_mape']:.6f}",
        f"- Improvement: {comparison['mape_improvement_pct']:.2f}%",
        f"- Baseline directional accuracy: {comparison['baseline_directional_accuracy']}",
        f"- NLP directional accuracy: {comparison['nlp_directional_accuracy']}",
        f"- Directional accuracy delta: {comparison['directional_accuracy_delta']}",
        f"- Baseline direction classifier accuracy: {comparison['baseline_direction_classifier_accuracy']}",
        f"- NLP direction classifier accuracy: {comparison['nlp_direction_classifier_accuracy']}",
        f"- Direction classifier accuracy delta: {comparison['direction_classifier_accuracy_delta']}",
        f"- Baseline rank IC: {comparison['baseline_rank_ic']:.6f}",
        f"- NLP rank IC: {comparison['nlp_rank_ic']:.6f}",
        f"- Baseline top-N excess return: {comparison['baseline_top_n_excess_return']:.6f}",
        f"- NLP top-N excess return: {comparison['nlp_top_n_excess_return']:.6f}",
        f"- Did NLP improve MAPE: {helped}",
        "",
    ]
    if not comparison["nlp_helped"]:
        lines.extend(
            [
                "## Notes",
                "",
                "NLP did not improve this run. Common causes include limited news volume,",
                "news dates not aligning with market dates, sentiment model mismatch,",
                "data leakage checks removing useful rows, or feature engineering that needs refinement.",
                "",
            ]
        )

    top_features = payload.get("nlp_model", {}).get("top_feature_importance", [])[:20]
    if top_features:
        lines.extend(["## Top 20 Feature Importance", ""])
        for row in top_features:
            lines.append(f"- {row['feature']}: {row['importance']}")
        lines.append("")

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def load_result_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(payload: dict[str, Any], path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _numeric_delta(left: Any, right: Any) -> float | None:
    if left is None or right is None:
        return None
    return round(float(left) - float(right), 6)


def _training_rows(dataset: Any, *, target_column: str = RETURN_TARGET) -> Any:
    frame = dataset.copy()
    frame[DATE_COLUMN] = _require_pandas().to_datetime(frame[DATE_COLUMN], errors="coerce")
    required_columns = [DATE_COLUMN, "ticker", "close", target_column]
    if target_column == RETURN_TARGET:
        required_columns.append(PRICE_TARGET)
    frame = frame.dropna(subset=required_columns)
    if frame.empty:
        raise ValueError("final dataset has no labeled rows for model training")
    return frame.sort_values([DATE_COLUMN, "ticker"]).reset_index(drop=True)


def _regression_metrics(
    test_frame: Any,
    predicted_values: Any,
    *,
    target_column: str,
    selection_top_n: int,
    np: Any,
    pd: Any,
) -> dict[str, float | int]:
    prediction_series = pd.Series(predicted_values, index=test_frame.index, dtype=float)
    actual_target = test_frame[target_column].astype(float)
    target_errors = actual_target - prediction_series

    if target_column == RETURN_TARGET:
        predicted_returns = prediction_series
    else:
        predicted_returns = prediction_series

    actual_next_price = test_frame[PRICE_TARGET].astype(float)
    current_close = test_frame["close"].astype(float)
    predicted_next_price = current_close * (1 + predicted_returns)

    nonzero_mask = actual_next_price != 0
    if nonzero_mask.any():
        mape = np.mean(
            np.abs(
                (actual_next_price[nonzero_mask] - predicted_next_price[nonzero_mask])
                / actual_next_price[nonzero_mask]
            )
        )
    else:
        mape = 0.0

    errors = actual_next_price - predicted_next_price
    actual_returns = test_frame[RETURN_TARGET].astype(float)
    predicted_direction = predicted_returns > 0
    actual_direction = actual_returns > 0
    predicted_up_mask = predicted_direction
    predicted_down_mask = ~predicted_direction
    up_precision = (
        float(np.mean(actual_direction[predicted_up_mask]))
        if bool(predicted_up_mask.any())
        else 0.0
    )
    down_precision = (
        float(np.mean(~actual_direction[predicted_down_mask]))
        if bool(predicted_down_mask.any())
        else 0.0
    )
    selection = _selection_metrics(
        test_frame,
        predicted_returns,
        top_n=selection_top_n,
        np=np,
        pd=pd,
    )
    return {
        "mape": float(mape),
        "rmse": float(np.sqrt(np.mean(np.square(errors)))),
        "mae": float(np.mean(np.abs(errors))),
        "target_rmse": float(np.sqrt(np.mean(np.square(target_errors)))),
        "target_mae": float(np.mean(np.abs(target_errors))),
        "directional_accuracy": float(np.mean(predicted_direction == actual_direction)),
        "up_precision": up_precision,
        "down_precision": down_precision,
        "rows": int(len(test_frame)),
        **selection,
    }


def _selection_metrics(
    test_frame: Any,
    predicted_returns: Any,
    *,
    top_n: int,
    np: Any,
    pd: Any,
) -> dict[str, float | int]:
    frame = test_frame[[DATE_COLUMN, RETURN_TARGET]].copy()
    frame["predicted_return"] = pd.Series(predicted_returns, index=test_frame.index, dtype=float)
    frame = frame.dropna(subset=[DATE_COLUMN, RETURN_TARGET, "predicted_return"])
    if frame.empty:
        return {
            "rank_ic": 0.0,
            "top_n_avg_return": 0.0,
            "top_n_hit_rate": 0.0,
            "top_n_excess_return": 0.0,
            "top_n_outperform_rate": 0.0,
            "long_short_return": 0.0,
            "selection_dates": 0,
        }

    rank_ic_values = []
    top_returns = []
    top_hit_rates = []
    top_excess_returns = []
    top_outperform_rates = []
    long_short_returns = []
    selection_dates = 0

    for _, group in frame.groupby(DATE_COLUMN, sort=True):
        if len(group) < 2:
            continue
        selection_dates += 1
        actual = group[RETURN_TARGET].astype(float)
        predicted = group["predicted_return"].astype(float)
        if predicted.nunique() > 1 and actual.nunique() > 1:
            rank_ic = predicted.rank(method="average").corr(actual.rank(method="average"))
            if rank_ic == rank_ic:
                rank_ic_values.append(float(rank_ic))

        k = min(top_n, len(group))
        top = group.nlargest(k, "predicted_return")
        bottom = group.nsmallest(k, "predicted_return")
        market_return = float(actual.mean())
        top_avg_return = float(top[RETURN_TARGET].mean())
        bottom_avg_return = float(bottom[RETURN_TARGET].mean())

        top_returns.append(top_avg_return)
        top_hit_rates.append(float((top[RETURN_TARGET] > 0).mean()))
        top_excess_returns.append(top_avg_return - market_return)
        top_outperform_rates.append(float((top[RETURN_TARGET] > market_return).mean()))
        long_short_returns.append(top_avg_return - bottom_avg_return)

    return {
        "rank_ic": _safe_mean(rank_ic_values, np=np),
        "top_n_avg_return": _safe_mean(top_returns, np=np),
        "top_n_hit_rate": _safe_mean(top_hit_rates, np=np),
        "top_n_excess_return": _safe_mean(top_excess_returns, np=np),
        "top_n_outperform_rate": _safe_mean(top_outperform_rates, np=np),
        "long_short_return": _safe_mean(long_short_returns, np=np),
        "selection_dates": selection_dates,
    }


def _mean_metric(fold_metrics: list[dict[str, float | int]], key: str, *, np: Any) -> float:
    values = [
        float(metric[key])
        for metric in fold_metrics
        if key in metric and not math.isnan(float(metric[key]))
    ]
    return round(_safe_mean(values, np=np), 6)


def _safe_mean(values: list[float], *, np: Any) -> float:
    if not values:
        return 0.0
    return float(np.mean(values))


def _clean_feature_name(name: str) -> str:
    for prefix in ("categorical__", "numeric__"):
        if name.startswith(prefix):
            return name.removeprefix(prefix)
    return name


def _is_numeric_series(series: Any) -> bool:
    try:
        return bool(series.dtype.kind in "biufc")
    except AttributeError:
        return False


def _require_pandas() -> Any:
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError(
            "pandas is not installed. Run: .venv\\Scripts\\python.exe -m pip install -e \".[data]\""
        ) from exc
    return pd


def _require_numpy() -> Any:
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(
            "numpy is not installed. Run: .venv\\Scripts\\python.exe -m pip install -e \".[data]\""
        ) from exc
    return np


def _require_joblib() -> Any:
    try:
        import joblib
    except ImportError as exc:
        raise RuntimeError(
            "joblib is not installed. Run: .venv\\Scripts\\python.exe -m pip install -e \".[ml]\""
        ) from exc
    return joblib
