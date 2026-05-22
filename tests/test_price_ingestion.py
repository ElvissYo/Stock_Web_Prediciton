import pytest

from kag.ingestion.prices import ingest_price_bars
from kag.market_data.types import PriceBar


class RecordingClient:
    def __init__(self):
        self.calls = []

    def execute_write(self, query, parameters=None):
        self.calls.append((query, parameters))
        return [{"rows_processed": len(parameters["rows"])}]


def test_ingest_price_bars_batches_rows():
    client = RecordingClient()
    price_bars = [
        PriceBar(
            ticker="BBCA",
            date=f"2026-05-{day:02d}",
            open=100.0,
            high=110.0,
            low=95.0,
            close=105.0,
            adj_close=105.0,
            volume=1000,
            source="yfinance",
            interval="1d",
        )
        for day in range(1, 4)
    ]

    result = ingest_price_bars(client, price_bars, batch_size=2)

    assert result.rows_read == 3
    assert result.rows_processed == 3
    assert result.batches_processed == 2
    assert len(client.calls) == 2
    assert client.calls[0][1]["rows"][0]["ticker"] == "BBCA"


def test_ingest_price_bars_rejects_invalid_batch_size():
    client = RecordingClient()

    with pytest.raises(ValueError, match="batch_size"):
        ingest_price_bars(client, [], batch_size=0)

