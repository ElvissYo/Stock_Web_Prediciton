import csv

import pytest

from kag.features.training_dataset import (
    FeatureSourceRow,
    build_latest_inference_features,
    build_training_features,
    export_feature_dataset,
    load_feature_source_rows,
)


class RecordingReadClient:
    def __init__(self):
        self.calls = []

    def execute_read(self, query, parameters=None):
        self.calls.append((query, parameters))
        return [
            {
                "ticker": "BBCA",
                "date": "2026-05-01",
                "sector": "Financials",
                "close": 100,
                "volume": 1000,
                "correlated_peer_count": 3,
                "correlation_avg_abs": 0.5,
            }
        ]


def test_load_feature_source_rows_normalizes_neo4j_rows():
    client = RecordingReadClient()

    rows = load_feature_source_rows(client, tickers=["bbca.jk"], start="2026-01-01")

    assert rows == [
        FeatureSourceRow(
            ticker="BBCA",
            date="2026-05-01",
            sector="Financials",
            close=100.0,
            volume=1000,
            correlated_peer_count=3,
            correlation_avg_abs=0.5,
        )
    ]
    assert client.calls[0][1]["tickers"] == ["BBCA"]
    assert client.calls[0][1]["start"] == "2026-01-01"


def test_build_training_features_uses_price_and_graph_context():
    source_rows = [
        FeatureSourceRow("AAA", "2026-01-01", "Financials", 100, 1000, 2, 0.4),
        FeatureSourceRow("AAA", "2026-01-02", "Financials", 101, 1000, 2, 0.4),
        FeatureSourceRow("AAA", "2026-01-03", "Financials", 103, 1000, 2, 0.4),
        FeatureSourceRow("AAA", "2026-01-04", "Financials", 102, 1000, 2, 0.4),
        FeatureSourceRow("AAA", "2026-01-05", "Financials", 104, 1000, 2, 0.4),
        FeatureSourceRow("BBB", "2026-01-01", "Financials", 200, 2000, 1, 0.3),
        FeatureSourceRow("BBB", "2026-01-02", "Financials", 202, 2000, 1, 0.3),
        FeatureSourceRow("BBB", "2026-01-03", "Financials", 206, 2000, 1, 0.3),
        FeatureSourceRow("BBB", "2026-01-04", "Financials", 204, 2000, 1, 0.3),
        FeatureSourceRow("BBB", "2026-01-05", "Financials", 208, 2000, 1, 0.3),
    ]

    feature_rows = build_training_features(
        source_rows,
        short_window=2,
        long_window=2,
        feature_windows=(2,),
    )

    first = feature_rows[0]
    assert first.ticker == "AAA"
    assert first.date == "2026-01-03"
    assert first.return_1d == round((103 / 101) - 1, 8)
    assert first.correlated_peer_count == 2
    assert first.correlation_avg_abs == 0.4
    assert first.target_next_direction == 0
    assert first.sector_return_1d == first.return_1d


def test_build_training_features_validates_windows():
    with pytest.raises(ValueError, match="short_window"):
        build_training_features([], short_window=1)

    with pytest.raises(ValueError, match="long_window"):
        build_training_features([], short_window=5, long_window=4)


def test_build_latest_inference_features_returns_latest_row_per_ticker():
    source_rows = [
        FeatureSourceRow("AAA", "2026-01-01", "Financials", 100, 1000, 2, 0.4),
        FeatureSourceRow("AAA", "2026-01-02", "Financials", 101, 1000, 2, 0.4),
        FeatureSourceRow("AAA", "2026-01-03", "Financials", 103, 1000, 2, 0.4),
        FeatureSourceRow("AAA", "2026-01-04", "Financials", 102, 1000, 2, 0.4),
        FeatureSourceRow("BBB", "2026-01-01", "Energy", 200, 2000, 1, 0.3),
        FeatureSourceRow("BBB", "2026-01-02", "Energy", 202, 2000, 1, 0.3),
        FeatureSourceRow("BBB", "2026-01-03", "Energy", 206, 2000, 1, 0.3),
        FeatureSourceRow("BBB", "2026-01-04", "Energy", 204, 2000, 1, 0.3),
    ]

    rows = build_latest_inference_features(
        source_rows,
        short_window=2,
        long_window=2,
        feature_windows=(2,),
    )

    assert [row.ticker for row in rows] == ["AAA", "BBB"]
    assert rows[0].date == "2026-01-04"
    assert rows[0].correlated_peer_count == 2


def test_export_feature_dataset_writes_csv(tmp_path):
    output_path = tmp_path / "features.csv"
    feature_rows = build_training_features(
        [
            FeatureSourceRow("AAA", "2026-01-01", "Financials", 100, 1000, 2, 0.4),
            FeatureSourceRow("AAA", "2026-01-02", "Financials", 101, 1000, 2, 0.4),
            FeatureSourceRow("AAA", "2026-01-03", "Financials", 103, 1000, 2, 0.4),
            FeatureSourceRow("AAA", "2026-01-04", "Financials", 102, 1000, 2, 0.4),
        ],
        short_window=2,
        long_window=2,
        feature_windows=(2,),
    )

    exported_rows = export_feature_dataset(feature_rows, output_path)

    with output_path.open("r", encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))

    assert exported_rows == 1
    assert rows[0]["ticker"] == "AAA"


def test_export_feature_dataset_rejects_empty_rows(tmp_path):
    with pytest.raises(ValueError, match="No feature rows"):
        export_feature_dataset([], tmp_path / "features.csv")
