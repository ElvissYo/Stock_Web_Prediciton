import pytest

from kag.market_data.symbols import load_stock_symbols
from kag.market_data.types import StockSymbol


class RecordingClient:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def execute_read(self, query, parameters=None):
        self.calls.append((query, parameters))
        return self.rows


def test_load_stock_symbols_normalizes_ticker_filters():
    client = RecordingClient(
        [{"ticker": "BBCA", "yfinance_symbol": "BBCA.JK"}],
    )

    symbols = load_stock_symbols(client, tickers=["bbca.jk"], limit=10)

    assert symbols == [StockSymbol(ticker="BBCA", yfinance_symbol="BBCA.JK")]
    assert client.calls[0][1]["tickers"] == ["BBCA"]
    assert client.calls[0][1]["limit"] == 10


def test_load_stock_symbols_rejects_empty_result():
    client = RecordingClient([])

    with pytest.raises(ValueError, match="No Stock nodes"):
        load_stock_symbols(client, tickers=None, limit=None)

