"""Fetch historical market data from Yahoo Finance via yfinance."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import math
from typing import Any

from kag.market_data.types import PriceBar, StockSymbol


YFINANCE_SOURCE = "yfinance"


def fetch_historical_prices(
    symbols: Iterable[StockSymbol],
    *,
    period: str = "1mo",
    interval: str = "1d",
    start: str | None = None,
    end: str | None = None,
) -> list[PriceBar]:
    """Fetch OHLCV price bars from yfinance.

    Uses one request per ticker to keep IDX symbol failures isolated.
    """

    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError(
            "yfinance is not installed. Run: .venv\\Scripts\\python.exe -m pip install -e \".[data]\""
        ) from exc

    price_bars: list[PriceBar] = []
    for symbol in symbols:
        ticker = yf.Ticker(symbol.yfinance_symbol)
        frame = ticker.history(
            period=None if start else period,
            start=start,
            end=end,
            interval=interval,
            auto_adjust=False,
            actions=False,
        )
        rows = _rows_from_frame(frame)
        price_bars.extend(price_bars_from_rows(symbol, rows, interval=interval))

    return price_bars


def price_bars_from_rows(
    symbol: StockSymbol,
    rows: Iterable[Mapping[str, Any]],
    *,
    interval: str,
) -> list[PriceBar]:
    """Convert provider rows into canonical price bars.

    Rows without a date or close value are skipped because they cannot support forecasting.
    """

    price_bars: list[PriceBar] = []
    for row in rows:
        date = _date_to_iso(row.get("date"))
        close = _float_or_none(row.get("Close"))
        if date is None or close is None:
            continue

        price_bars.append(
            PriceBar(
                ticker=symbol.ticker,
                date=date,
                open=_float_or_none(row.get("Open")),
                high=_float_or_none(row.get("High")),
                low=_float_or_none(row.get("Low")),
                close=close,
                adj_close=_float_or_none(row.get("Adj Close")),
                volume=_int_or_none(row.get("Volume")),
                source=YFINANCE_SOURCE,
                interval=interval,
            )
        )

    return price_bars


def _rows_from_frame(frame: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, row in frame.iterrows():
        values = row.to_dict()
        values["date"] = index
        rows.append(values)

    return rows


def _date_to_iso(value: Any) -> str | None:
    if value is None:
        return None

    if hasattr(value, "date"):
        return value.date().isoformat()

    text = str(value).strip()
    if not text:
        return None

    return text[:10]


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None

    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(parsed):
        return None

    return parsed


def _int_or_none(value: Any) -> int | None:
    parsed = _float_or_none(value)
    if parsed is None:
        return None

    return int(parsed)

