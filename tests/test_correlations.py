import pytest

from kag.graph.correlations import (
    CorrelationRelationship,
    PriceObservation,
    calculate_return_correlations,
    delete_correlations,
    write_correlations,
)


class RecordingClient:
    def __init__(self):
        self.calls = []

    def execute_write(self, query, parameters=None):
        self.calls.append((query, parameters))
        if "relationships_deleted" in query:
            return [{"relationships_deleted": 3}]
        return [{"relationships_processed": len(parameters["rows"])}]


def test_calculate_return_correlations_creates_canonical_relationships():
    observations = [
        PriceObservation(ticker="AAA", date="2026-01-01", close=100),
        PriceObservation(ticker="AAA", date="2026-01-02", close=110),
        PriceObservation(ticker="AAA", date="2026-01-03", close=132),
        PriceObservation(ticker="BBB", date="2026-01-01", close=200),
        PriceObservation(ticker="BBB", date="2026-01-02", close=220),
        PriceObservation(ticker="BBB", date="2026-01-03", close=264),
        PriceObservation(ticker="CCC", date="2026-01-01", close=100),
        PriceObservation(ticker="CCC", date="2026-01-02", close=100),
        PriceObservation(ticker="CCC", date="2026-01-03", close=100),
    ]

    relationships = calculate_return_correlations(
        observations,
        min_observations=2,
        min_abs_correlation=0,
    )

    assert [(item.source_ticker, item.target_ticker) for item in relationships] == [
        ("AAA", "BBB")
    ]
    assert relationships[0].coefficient == 1.0
    assert relationships[0].observations == 2


def test_calculate_return_correlations_validates_thresholds():
    with pytest.raises(ValueError, match="min_observations"):
        calculate_return_correlations([], min_observations=1)

    with pytest.raises(ValueError, match="min_abs_correlation"):
        calculate_return_correlations([], min_abs_correlation=1.1)


def test_write_correlations_sends_rows_to_neo4j():
    client = RecordingClient()
    relationships = [
        CorrelationRelationship(
            source_ticker="AAA",
            target_ticker="BBB",
            coefficient=0.8,
            observations=20,
            first_date="2026-01-01",
            last_date="2026-01-31",
            method="pearson_close_return",
            price_source="yfinance",
            interval="1d",
        )
    ]

    result = write_correlations(client, relationships)

    assert result.relationships_read == 1
    assert result.relationships_processed == 1
    assert client.calls[0][1]["rows"][0]["abs_coefficient"] == 0.8


def test_delete_correlations_scopes_by_ticker_and_metadata():
    client = RecordingClient()

    result = delete_correlations(
        client,
        tickers=["bbca.jk", "tlkm"],
        method="pearson_close_return",
        price_source="yfinance",
        interval="1d",
    )

    assert result.relationships_deleted == 3
    assert client.calls[0][1]["tickers"] == ["BBCA", "TLKM"]
    assert client.calls[0][1]["price_source"] == "yfinance"
