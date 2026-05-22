import pytest

from kag.ingestion.stocks import StockRecord, ingest_stocks, load_stock_records, normalize_ticker


class RecordingClient:
    def __init__(self):
        self.calls = []

    def execute_write(self, query, parameters=None):
        self.calls.append((query, parameters))
        rows = parameters["rows"]
        return [
            {
                "rows_processed": len(rows),
                "sectors_processed": len({row["sector"] for row in rows}),
            }
        ]


def test_normalize_ticker_accepts_idx_and_yfinance_symbols():
    assert normalize_ticker("bbca") == "BBCA"
    assert normalize_ticker("BBCA.JK") == "BBCA"


def test_load_stock_records_normalizes_required_values(tmp_path):
    csv_path = tmp_path / "stocks.csv"
    csv_path.write_text(
        "ticker,name,sector\n"
        "bbca.jk,Bank Central Asia Tbk,Financials\n",
        encoding="utf-8",
    )

    records = load_stock_records(csv_path)

    assert records == [
        StockRecord(
            ticker="BBCA",
            name="Bank Central Asia Tbk",
            sector="Financials",
            exchange="IDX",
            yfinance_symbol="BBCA.JK",
            universe_rank=None,
        )
    ]


def test_load_stock_records_accepts_optional_universe_rank(tmp_path):
    csv_path = tmp_path / "stocks.csv"
    csv_path.write_text(
        "ticker,name,sector,universe_rank\n"
        "BBRI,Bank Rakyat Indonesia Tbk,Financials,3\n",
        encoding="utf-8",
    )

    records = load_stock_records(csv_path)

    assert records[0].universe_rank == 3


def test_load_stock_records_rejects_missing_columns(tmp_path):
    csv_path = tmp_path / "stocks.csv"
    csv_path.write_text("ticker,name\nBBCA,Bank Central Asia Tbk\n", encoding="utf-8")

    with pytest.raises(ValueError, match="missing required columns: sector"):
        load_stock_records(csv_path)


def test_ingest_stocks_sends_rows_to_neo4j():
    client = RecordingClient()
    records = [
        StockRecord(ticker="BBCA", name="Bank Central Asia Tbk", sector="Financials"),
        StockRecord(ticker="TLKM", name="Telkom Indonesia Tbk", sector="Infrastructures"),
    ]

    result = ingest_stocks(client, records)

    assert result.rows_read == 2
    assert result.rows_processed == 2
    assert result.sectors_processed == 2
    assert len(client.calls) == 1
    assert client.calls[0][1]["rows"][0]["ticker"] == "BBCA"
    assert client.calls[0][1]["rows"][0]["universe_rank"] is None
