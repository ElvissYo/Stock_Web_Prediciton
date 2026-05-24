"""Fuse price, NLP, and stock metadata features into a global model dataset."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from kag.market_data.top_universe import load_stock_metadata


logger = logging.getLogger(__name__)

TARGET_COLUMNS = [
    "next_day_price",
    "target_return",
    "direction",
    "market_next_return",
    "target_excess_return",
    "outperform_market",
    "sector_next_return",
    "target_sector_excess_return",
    "outperform_sector",
]
DEFAULT_EMBEDDING_DIMENSIONS = 50
DEFAULT_NLP_LAG_TRADING_DAYS = 1


def build_final_dataset_frame(
    price_features: Any,
    nlp_features: Any | None,
    *,
    metadata_path: str | Path = "data/seeds/idx_top10_poc.csv",
    embedding_dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS,
    nlp_lag_trading_days: int = DEFAULT_NLP_LAG_TRADING_DAYS,
    encoders_path: str | Path | None = "models/encoders.pkl",
    drop_unlabeled: bool = False,
) -> Any:
    """Build one model-ready dataset using ticker/date as the fusion key."""

    pd = _require_pandas()
    _validate_price_features(price_features)

    prices = price_features.copy()
    prices["ticker"] = prices["ticker"].astype(str).str.upper().str.removesuffix(".JK")
    prices["date"] = pd.to_datetime(prices["date"], errors="coerce").dt.normalize()
    prices = prices.dropna(subset=["ticker", "date", "close"]).sort_values(["ticker", "date"])

    nlp = _prepare_nlp_features(
        nlp_features,
        embedding_dimensions=embedding_dimensions,
        price_calendar=prices[["ticker", "date"]],
        lag_trading_days=nlp_lag_trading_days,
    )
    dataset = prices.merge(nlp, on=["ticker", "date"], how="left")
    dataset = _fill_missing_nlp(dataset, embedding_dimensions=embedding_dimensions)
    dataset = _merge_metadata(dataset, metadata_path=metadata_path)
    dataset = _add_temporal_features(dataset)
    dataset = _add_metadata_encodings(dataset, encoders_path=encoders_path)
    dataset = _add_targets(dataset)
    dataset = _add_cross_sectional_targets(dataset)

    if drop_unlabeled:
        dataset = dataset.dropna(subset=["target_return", "next_day_price"]).copy()

    return dataset.sort_values(["date", "ticker"]).reset_index(drop=True)


def build_final_dataset_from_paths(
    price_features_path: str | Path,
    nlp_features_path: str | Path,
    output_path: str | Path,
    *,
    metadata_path: str | Path = "data/seeds/idx_top10_poc.csv",
    embedding_dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS,
    nlp_lag_trading_days: int = DEFAULT_NLP_LAG_TRADING_DAYS,
    encoders_path: str | Path | None = "models/encoders.pkl",
    drop_unlabeled: bool = False,
) -> int:
    """Read feature inputs, build the final dataset, and write Parquet."""

    pd = _require_pandas()
    price_features = pd.read_parquet(price_features_path)
    nlp_features = None
    nlp_path = Path(nlp_features_path)
    if nlp_path.exists():
        nlp_features = pd.read_parquet(nlp_path)
    else:
        logger.warning("NLP features file is missing; filling NLP columns with zeros: %s", nlp_path)

    dataset = build_final_dataset_frame(
        price_features,
        nlp_features,
        metadata_path=metadata_path,
        embedding_dimensions=embedding_dimensions,
        nlp_lag_trading_days=nlp_lag_trading_days,
        encoders_path=encoders_path,
        drop_unlabeled=drop_unlabeled,
    )

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        dataset.to_parquet(path, index=False)
    except ImportError as exc:
        raise RuntimeError(
            "Parquet support is not installed. Run: .venv\\Scripts\\python.exe -m pip install -e \".[data]\""
        ) from exc
    return len(dataset)


def nlp_feature_columns(embedding_dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS) -> list[str]:
    """Return stable NLP feature columns used by model A/B evaluation."""

    return [
        "sentiment_mean",
        "sentiment_std",
        "news_count",
        "sentiment_momentum",
        *[f"embedding_dim_{index}" for index in range(embedding_dimensions)],
    ]


def _prepare_nlp_features(
    nlp_features: Any | None,
    *,
    embedding_dimensions: int,
    price_calendar: Any,
    lag_trading_days: int,
) -> Any:
    pd = _require_pandas()
    columns = ["ticker", "date", *nlp_feature_columns(embedding_dimensions)]
    if nlp_features is None or nlp_features.empty:
        return pd.DataFrame(columns=columns)
    if lag_trading_days < 0:
        raise ValueError("nlp_lag_trading_days must be zero or greater")

    nlp = nlp_features.copy()
    nlp["ticker"] = nlp["ticker"].astype(str).str.upper().str.removesuffix(".JK")
    nlp["date"] = pd.to_datetime(nlp["date"], errors="coerce").dt.normalize()
    for column in columns:
        if column not in nlp.columns:
            nlp[column] = 0.0
    nlp = nlp[columns].dropna(subset=["ticker", "date"])
    if lag_trading_days:
        nlp = _lag_nlp_to_available_price_dates(
            nlp,
            price_calendar=price_calendar,
            lag_trading_days=lag_trading_days,
            embedding_dimensions=embedding_dimensions,
        )
    return _collapse_duplicate_nlp_dates(nlp, embedding_dimensions=embedding_dimensions)


def _lag_nlp_to_available_price_dates(
    nlp: Any,
    *,
    price_calendar: Any,
    lag_trading_days: int,
    embedding_dimensions: int,
) -> Any:
    """Map news dates to future tradable feature dates to avoid same-day leakage."""

    pd = _require_pandas()
    if nlp.empty:
        return nlp

    calendar = price_calendar.copy()
    calendar["ticker"] = calendar["ticker"].astype(str).str.upper().str.removesuffix(".JK")
    calendar["date"] = pd.to_datetime(calendar["date"], errors="coerce").dt.normalize()
    calendar = calendar.dropna(subset=["ticker", "date"]).sort_values(["ticker", "date"])
    calendar_by_ticker = {
        ticker: list(group["date"].drop_duplicates())
        for ticker, group in calendar.groupby("ticker", sort=False)
    }

    shifted_rows = []
    for row in nlp.to_dict("records"):
        dates = calendar_by_ticker.get(str(row.get("ticker", "")).upper())
        if not dates:
            continue
        news_date = pd.Timestamp(row["date"]).normalize()
        insertion_index = _first_calendar_index_on_or_after(dates, news_date)
        target_index = insertion_index + lag_trading_days
        if target_index >= len(dates):
            continue
        shifted = dict(row)
        shifted["date"] = dates[target_index]
        shifted_rows.append(shifted)

    if not shifted_rows:
        return pd.DataFrame(columns=["ticker", "date", *nlp_feature_columns(embedding_dimensions)])
    return pd.DataFrame(shifted_rows)


def _first_calendar_index_on_or_after(dates: list[Any], target_date: Any) -> int:
    for index, current_date in enumerate(dates):
        if current_date >= target_date:
            return index
    return len(dates)


def _collapse_duplicate_nlp_dates(nlp: Any, *, embedding_dimensions: int) -> Any:
    pd = _require_pandas()
    columns = ["ticker", "date", *nlp_feature_columns(embedding_dimensions)]
    if nlp.empty:
        return pd.DataFrame(columns=columns)

    frame = nlp.copy()
    numeric_columns = nlp_feature_columns(embedding_dimensions)
    for column in numeric_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)

    aggregations = {
        "sentiment_mean": ("sentiment_mean", "mean"),
        "sentiment_std": ("sentiment_std", "mean"),
        "news_count": ("news_count", "sum"),
        "sentiment_momentum": ("sentiment_momentum", "mean"),
    }
    for index in range(embedding_dimensions):
        column = f"embedding_dim_{index}"
        aggregations[column] = (column, "mean")
    return frame.groupby(["ticker", "date"], as_index=False).agg(**aggregations)[columns]


def _fill_missing_nlp(dataset: Any, *, embedding_dimensions: int) -> Any:
    for column in nlp_feature_columns(embedding_dimensions):
        if column not in dataset.columns:
            dataset[column] = 0.0
        dataset[column] = dataset[column].fillna(0.0)
    return dataset


def _merge_metadata(dataset: Any, *, metadata_path: str | Path) -> Any:
    pd = _require_pandas()
    records = load_stock_metadata(metadata_path)
    metadata = pd.DataFrame([record.to_csv_row() for record in records])
    metadata["ticker"] = metadata["ticker"].astype(str).str.upper().str.removesuffix(".JK")
    metadata["market_cap_rank"] = pd.to_numeric(metadata["market_cap_rank"], errors="coerce")
    metadata["beta"] = pd.to_numeric(metadata["beta"], errors="coerce")

    merged = dataset.merge(
        metadata[["ticker", "name", "sector", "market_cap_rank", "beta"]],
        on="ticker",
        how="left",
        suffixes=("", "_metadata"),
    )
    if "sector_metadata" in merged.columns:
        merged["sector"] = merged["sector_metadata"].combine_first(merged.get("sector"))
        merged = merged.drop(columns=["sector_metadata"])

    merged["name"] = merged["name"].fillna(merged["ticker"])
    merged["sector"] = merged["sector"].fillna("UNKNOWN")
    merged["beta_missing"] = merged["beta"].isna().astype(int)
    merged["beta"] = merged["beta"].fillna(1.0)
    return merged


def _add_temporal_features(dataset: Any) -> Any:
    dataset["day"] = dataset["date"].dt.day
    dataset["week"] = dataset["date"].dt.isocalendar().week.astype(int)
    dataset["month"] = dataset["date"].dt.month
    dataset["day_of_week"] = dataset["date"].dt.dayofweek
    return dataset


def _add_metadata_encodings(dataset: Any, *, encoders_path: str | Path | None) -> Any:
    joblib = _require_joblib()
    ticker_values = sorted(dataset["ticker"].dropna().astype(str).unique())
    sector_values = sorted(dataset["sector"].dropna().astype(str).unique())
    ticker_to_id = {ticker: index for index, ticker in enumerate(ticker_values)}
    sector_to_id = {sector: index for index, sector in enumerate(sector_values)}

    dataset["ticker_encoded"] = dataset["ticker"].map(ticker_to_id).fillna(-1).astype(int)
    dataset["sector_encoded"] = dataset["sector"].map(sector_to_id).fillna(-1).astype(int)
    dataset["market_cap_encoded"] = _market_cap_score(dataset["market_cap_rank"])

    if encoders_path is not None:
        path = Path(encoders_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "ticker_to_id": ticker_to_id,
                "sector_to_id": sector_to_id,
                "market_cap_encoding": "1_minus_rank_percentile",
            },
            path,
        )

    return dataset


def _market_cap_score(rank_series: Any) -> Any:
    pd = _require_pandas()
    rank = pd.to_numeric(rank_series, errors="coerce")
    valid_rank = rank.dropna()
    if valid_rank.empty:
        return rank.fillna(0.0)

    max_rank = float(valid_rank.max())
    if max_rank <= 1:
        return rank.fillna(max_rank).map(lambda value: 1.0 if value else 0.0)
    return (1 - ((rank - 1) / (max_rank - 1))).fillna(0.0)


def _add_targets(dataset: Any) -> Any:
    dataset = dataset.sort_values(["ticker", "date"]).copy()
    dataset["next_day_price"] = dataset.groupby("ticker")["close"].shift(-1)
    dataset["target_return"] = (dataset["next_day_price"] / dataset["close"]) - 1
    dataset["direction"] = (dataset["target_return"] > 0).astype("Int64")
    dataset.loc[dataset["target_return"].isna(), "direction"] = None
    return dataset


def _add_cross_sectional_targets(dataset: Any) -> Any:
    """Add target-only market/sector relative labels for ranking evaluation."""

    frame = dataset.copy()
    frame["market_next_return"] = frame.groupby("date")["target_return"].transform("mean")
    frame["target_excess_return"] = frame["target_return"] - frame["market_next_return"]
    frame["outperform_market"] = (frame["target_excess_return"] > 0).astype("Int64")
    frame.loc[frame["target_excess_return"].isna(), "outperform_market"] = None

    frame["sector_next_return"] = frame.groupby(["date", "sector"])["target_return"].transform("mean")
    frame["target_sector_excess_return"] = frame["target_return"] - frame["sector_next_return"]
    frame["outperform_sector"] = (frame["target_sector_excess_return"] > 0).astype("Int64")
    frame.loc[frame["target_sector_excess_return"].isna(), "outperform_sector"] = None
    return frame


def _validate_price_features(frame: Any) -> None:
    required_columns = {"ticker", "date", "close"}
    missing = required_columns - set(frame.columns)
    if missing:
        raise ValueError(f"price features are missing required columns: {', '.join(sorted(missing))}")
    if frame.empty:
        raise ValueError("price features are empty")


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
