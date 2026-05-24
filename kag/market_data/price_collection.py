"""Collect and persist historical IDX prices for local Parquet pipelines."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable

from kag.market_data.top_universe import StockMetadata


logger = logging.getLogger(__name__)


def fetch_price_history_frame(
    records: Iterable[StockMetadata],
    *,
    period: str = "max",
    interval: str = "1d",
    start: str | None = None,
    end: str | None = None,
) -> Any:
    """Fetch OHLCV price history and return one normalized pandas DataFrame."""

    pd = _require_pandas()
    yf = _require_yfinance()

    frames = []
    for record in records:
        try:
            raw_frame = yf.Ticker(record.yfinance_symbol).history(
                period=None if start else period,
                start=start,
                end=end,
                interval=interval,
                auto_adjust=False,
                actions=False,
            )
        except Exception:
            logger.exception("Failed to fetch price data; ticker=%s", record.yfinance_symbol)
            continue

        normalized = normalize_yfinance_frame(raw_frame, record, interval=interval)
        if normalized.empty:
            logger.warning("No usable price rows returned; ticker=%s", record.yfinance_symbol)
            continue
        frames.append(normalized)

    if not frames:
        raise ValueError("No price data was collected for the requested ticker universe")

    prices = pd.concat(frames, ignore_index=True)
    prices = prices.sort_values(["ticker", "date"]).reset_index(drop=True)
    return prices


def normalize_yfinance_frame(frame: Any, record: StockMetadata, *, interval: str) -> Any:
    """Normalize one yfinance history frame into canonical price columns."""

    pd = _require_pandas()
    if frame is None or frame.empty:
        return pd.DataFrame()

    raw = frame.reset_index()
    date_column = _detect_date_column(raw)
    if date_column is None:
        logger.warning("Could not detect date column in yfinance frame; ticker=%s", record.ticker)
        return pd.DataFrame()

    output = pd.DataFrame(
        {
            "ticker": record.ticker,
            "yfinance_symbol": record.yfinance_symbol,
            "date": _normalize_dates(raw[date_column]),
            "open": _numeric(raw.get("Open")),
            "high": _numeric(raw.get("High")),
            "low": _numeric(raw.get("Low")),
            "close": _numeric(raw.get("Close")),
            "adj_close": _numeric(raw.get("Adj Close")),
            "volume": _numeric(raw.get("Volume")),
            "source": "yfinance",
            "interval": interval,
        }
    )
    output = output.dropna(subset=["date", "close"])
    output["volume"] = output["volume"].fillna(0).astype("int64")
    return output


def write_price_history_parquet(frame: Any, output_path: str | Path) -> int:
    """Write normalized prices to Parquet and return row count."""

    if frame.empty:
        raise ValueError("Cannot write an empty price DataFrame")

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        frame.to_parquet(path, index=False)
    except ImportError as exc:
        raise RuntimeError(
            "Parquet support is not installed. Run: .venv\\Scripts\\python.exe -m pip install -e \".[data]\""
        ) from exc
    return len(frame)


def _detect_date_column(frame: Any) -> str | None:
    for column in ("Date", "Datetime", "date", "datetime"):
        if column in frame.columns:
            return column
    if len(frame.columns) > 0:
        return str(frame.columns[0])
    return None


def _normalize_dates(values: Any) -> Any:
    pd = _require_pandas()
    dates = pd.to_datetime(values, errors="coerce")
    try:
        dates = dates.dt.tz_localize(None)
    except (AttributeError, TypeError):
        pass
    return dates.dt.normalize()


def _numeric(values: Any) -> Any:
    pd = _require_pandas()
    if values is None:
        return pd.Series(dtype="float64")
    return pd.to_numeric(values, errors="coerce")


def _require_pandas() -> Any:
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError(
            "pandas is not installed. Run: .venv\\Scripts\\python.exe -m pip install -e \".[data]\""
        ) from exc
    return pd


def _require_yfinance() -> Any:
    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError(
            "yfinance is not installed. Run: .venv\\Scripts\\python.exe -m pip install -e \".[data]\""
        ) from exc
    return yf
