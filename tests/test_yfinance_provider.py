from kag.market_data.types import StockSymbol
from kag.market_data.yfinance_provider import price_bars_from_rows


def test_price_bars_from_rows_maps_provider_fields():
    symbol = StockSymbol(ticker="BBCA", yfinance_symbol="BBCA.JK")

    price_bars = price_bars_from_rows(
        symbol,
        [
            {
                "date": "2026-05-01",
                "Open": "100",
                "High": "110",
                "Low": "95",
                "Close": "105",
                "Adj Close": "104",
                "Volume": "1000",
            }
        ],
        interval="1d",
    )

    assert price_bars[0].ticker == "BBCA"
    assert price_bars[0].date == "2026-05-01"
    assert price_bars[0].close == 105.0
    assert price_bars[0].volume == 1000
    assert price_bars[0].source == "yfinance"


def test_price_bars_from_rows_skips_rows_without_close():
    symbol = StockSymbol(ticker="BBCA", yfinance_symbol="BBCA.JK")

    price_bars = price_bars_from_rows(
        symbol,
        [{"date": "2026-05-01", "Open": "100"}],
        interval="1d",
    )

    assert price_bars == []

