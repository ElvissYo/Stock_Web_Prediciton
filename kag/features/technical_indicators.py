"""Technical price feature engineering for global stock forecasting models."""

from __future__ import annotations

from pathlib import Path
from typing import Any


PRICE_FEATURE_COLUMNS = [
    "return_1d",
    "return_5d",
    "return_10d",
    "return_20d",
    "log_return_1d",
    "volatility_5d",
    "volatility_10d",
    "volatility_20d",
    "volatility_60d",
    "SMA_20",
    "SMA_50",
    "SMA_200",
    "EMA_12",
    "EMA_26",
    "MACD",
    "MACD_signal",
    "MACD_hist",
    "RSI",
    "BB_middle",
    "BB_upper",
    "BB_lower",
    "BB_width",
    "BB_percent_b",
    "ATR",
    "atr_pct",
    "volume_sma_20",
    "volume_sma_50",
    "volume_ratio_20",
    "volume_ratio_50",
    "volume_change_1d",
    "volume_zscore_20",
    "close_to_sma_20",
    "close_to_sma_50",
    "close_to_sma_200",
    "sma20_to_sma50",
    "sma50_to_sma200",
    "momentum_5d",
    "momentum_10d",
    "momentum_20d",
    "momentum_60d",
    "drawdown_20d",
    "drawdown_60d",
    "price_position_20d",
    "price_position_60d",
    "high_low_range",
    "close_open_return",
    "gap_return",
    "true_range_pct",
    "rolling_max_20d_ratio",
    "rolling_min_20d_ratio",
    "rolling_max_60d_ratio",
    "rolling_min_60d_ratio",
    "obv",
    "obv_20d_change",
    "dollar_volume",
    "dollar_volume_sma_20",
]


def build_price_feature_frame(price_frame: Any) -> Any:
    """Build technical features from normalized OHLCV prices."""

    pd = _require_pandas()
    np = _require_numpy()
    _validate_price_frame(price_frame)

    frame = price_frame.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
    frame = frame.dropna(subset=["ticker", "date", "close"])
    frame = frame.sort_values(["ticker", "date"]).reset_index(drop=True)

    feature_frames = [
        _features_for_ticker(group.copy(), np=np)
        for _, group in frame.groupby("ticker", sort=True, group_keys=False)
    ]
    if not feature_frames:
        raise ValueError("No price rows are available for feature engineering")

    features = pd.concat(feature_frames, ignore_index=True)
    features = features.sort_values(["ticker", "date"]).reset_index(drop=True)
    return features


def build_price_features_from_parquet(input_path: str | Path, output_path: str | Path) -> int:
    """Read normalized price Parquet, build technical features, and write Parquet."""

    pd = _require_pandas()
    prices = pd.read_parquet(input_path)
    features = build_price_feature_frame(prices)

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        features.to_parquet(path, index=False)
    except ImportError as exc:
        raise RuntimeError(
            "Parquet support is not installed. Run: .venv\\Scripts\\python.exe -m pip install -e \".[data]\""
        ) from exc
    return len(features)


def _features_for_ticker(group: Any, *, np: Any) -> Any:
    close = group["close"].astype(float)
    open_ = group["open"].astype(float)
    high = group["high"].astype(float)
    low = group["low"].astype(float)
    volume = group["volume"].fillna(0).astype(float)
    previous_close = close.shift(1)

    group["return_1d"] = close.pct_change(1)
    group["return_5d"] = close.pct_change(5)
    group["return_10d"] = close.pct_change(10)
    group["return_20d"] = close.pct_change(20)
    group["log_return_1d"] = np.log(close / previous_close)

    for window in (5, 10, 20, 60):
        group[f"volatility_{window}d"] = group["return_1d"].rolling(window).std()

    group["SMA_20"] = close.rolling(20).mean()
    group["SMA_50"] = close.rolling(50).mean()
    group["SMA_200"] = close.rolling(200).mean()
    group["EMA_12"] = close.ewm(span=12, adjust=False).mean()
    group["EMA_26"] = close.ewm(span=26, adjust=False).mean()
    group["MACD"] = group["EMA_12"] - group["EMA_26"]
    group["MACD_signal"] = group["MACD"].ewm(span=9, adjust=False).mean()
    group["MACD_hist"] = group["MACD"] - group["MACD_signal"]
    group["RSI"] = _rsi(close)

    group["BB_middle"] = group["SMA_20"]
    bb_std = close.rolling(20).std()
    group["BB_upper"] = group["BB_middle"] + (2 * bb_std)
    group["BB_lower"] = group["BB_middle"] - (2 * bb_std)
    group["BB_width"] = _safe_divide(group["BB_upper"] - group["BB_lower"], group["BB_middle"])
    group["BB_percent_b"] = _safe_divide(close - group["BB_lower"], group["BB_upper"] - group["BB_lower"])

    true_range = _true_range(high, low, previous_close)
    group["ATR"] = true_range.rolling(14).mean()
    group["atr_pct"] = _safe_divide(group["ATR"], close)
    group["true_range_pct"] = _safe_divide(true_range, close)

    group["volume_sma_20"] = volume.rolling(20).mean()
    group["volume_sma_50"] = volume.rolling(50).mean()
    group["volume_ratio_20"] = _safe_divide(volume, group["volume_sma_20"])
    group["volume_ratio_50"] = _safe_divide(volume, group["volume_sma_50"])
    group["volume_change_1d"] = volume.pct_change(1)
    volume_std_20 = volume.rolling(20).std()
    group["volume_zscore_20"] = _safe_divide(volume - group["volume_sma_20"], volume_std_20)

    group["close_to_sma_20"] = _safe_divide(close, group["SMA_20"]) - 1
    group["close_to_sma_50"] = _safe_divide(close, group["SMA_50"]) - 1
    group["close_to_sma_200"] = _safe_divide(close, group["SMA_200"]) - 1
    group["sma20_to_sma50"] = _safe_divide(group["SMA_20"], group["SMA_50"]) - 1
    group["sma50_to_sma200"] = _safe_divide(group["SMA_50"], group["SMA_200"]) - 1

    for window in (5, 10, 20, 60):
        group[f"momentum_{window}d"] = close.pct_change(window)

    for window in (20, 60):
        rolling_max = close.rolling(window).max()
        rolling_min = close.rolling(window).min()
        group[f"drawdown_{window}d"] = _safe_divide(close, rolling_max) - 1
        group[f"price_position_{window}d"] = _safe_divide(close - rolling_min, rolling_max - rolling_min)
        group[f"rolling_max_{window}d_ratio"] = _safe_divide(close, rolling_max) - 1
        group[f"rolling_min_{window}d_ratio"] = _safe_divide(close, rolling_min) - 1

    group["high_low_range"] = _safe_divide(high - low, close)
    group["close_open_return"] = _safe_divide(close, open_) - 1
    group["gap_return"] = _safe_divide(open_, previous_close) - 1

    price_direction = np.sign(close.diff()).fillna(0)
    group["obv"] = (price_direction * volume).cumsum()
    group["obv_20d_change"] = group["obv"].pct_change(20)
    group["dollar_volume"] = close * volume
    group["dollar_volume_sma_20"] = group["dollar_volume"].rolling(20).mean()

    group[PRICE_FEATURE_COLUMNS] = group[PRICE_FEATURE_COLUMNS].replace([np.inf, -np.inf], np.nan)
    return group


def _rsi(close: Any, window: int = 14) -> Any:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    average_gain = gain.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    average_loss = loss.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    relative_strength = _safe_divide(average_gain, average_loss)
    return 100 - (100 / (1 + relative_strength))


def _true_range(high: Any, low: Any, previous_close: Any) -> Any:
    pd = _require_pandas()
    ranges = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    )
    return ranges.max(axis=1)


def _safe_divide(numerator: Any, denominator: Any) -> Any:
    np = _require_numpy()
    return numerator / denominator.replace(0, np.nan)


def _validate_price_frame(frame: Any) -> None:
    required_columns = {"ticker", "date", "open", "high", "low", "close", "volume"}
    missing = required_columns - set(frame.columns)
    if missing:
        raise ValueError(f"price data is missing required columns: {', '.join(sorted(missing))}")
    if frame.empty:
        raise ValueError("price data is empty")


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
