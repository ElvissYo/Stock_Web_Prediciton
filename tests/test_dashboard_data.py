import pytest

from kag.dashboard.data import (
    build_investment_simulation,
    load_model_metrics,
    load_stock_options,
    normalize_prediction_rows,
    prediction_label,
)


def test_normalize_prediction_rows_casts_values():
    rows = normalize_prediction_rows(
        [
            {
                "ticker": "BBCA",
                "date": "2026-05-22",
                "sector": "Financials",
                "close": "5875.0",
                "probability_up": "0.554636",
                "predicted_direction": "1",
                "model_type": "lightgbm",
            }
        ]
    )

    assert rows == [
        {
            "ticker": "BBCA",
            "date": "2026-05-22",
            "sector": "Financials",
            "close": 5875.0,
            "probability_up": 0.554636,
            "predicted_direction": 1,
            "model_type": "lightgbm",
        }
    ]


def test_prediction_label_maps_known_values():
    assert prediction_label(1) == "Up"
    assert prediction_label(0) == "Down"
    assert prediction_label(None) == "Unknown"


def test_load_model_metrics_returns_empty_for_missing_file(tmp_path):
    assert load_model_metrics(tmp_path / "missing.json") == {}


def test_load_stock_options_orders_priced_stocks_first():
    class RecordingClient:
        def execute_read(self, query, parameters=None):
            assert "count(price) > 0 AS has_price" in query
            assert "ORDER BY has_price DESC, coalesce(stock.universe_rank, 1000000), ticker" in query
            return [
                {"ticker": "BBCA", "has_price": True, "price_points": 20},
                {"ticker": "AADI", "has_price": False, "price_points": 0},
            ]

    assert load_stock_options(RecordingClient())[0]["ticker"] == "BBCA"


def test_build_investment_simulation_uses_historical_values():
    simulation = build_investment_simulation(
        [
            {"date": "2026-01-01", "close": 100.0},
            {"date": "2026-01-02", "close": 110.0},
            {"date": "2026-01-05", "close": 121.0},
        ],
        amount=1_000_000,
        entry_date="2026-01-01",
        exit_date="2026-01-05",
    )

    assert simulation["mode"] == "historical"
    assert simulation["entry_close"] == 100.0
    assert simulation["exit_value"] == 1_210_000
    assert len(simulation["rows"]) == 3


def test_build_investment_simulation_projects_future_weekdays():
    simulation = build_investment_simulation(
        [
            {"date": "2026-01-01", "close": 100.0},
            {"date": "2026-01-02", "close": 101.0},
            {"date": "2026-01-05", "close": 102.0},
            {"date": "2026-01-06", "close": 103.0},
        ],
        amount=1_000_000,
        entry_date="2026-01-02",
        exit_date="2026-01-09",
        probability_up=0.6,
    )

    assert simulation["mode"] == "projected"
    assert simulation["rows"][-1]["kind"] == "projected"
    assert simulation["rows"][-1]["date"] == "2026-01-09"


def test_build_investment_simulation_validates_inputs():
    with pytest.raises(ValueError, match="amount"):
        build_investment_simulation([], amount=0, entry_date="2026-01-01", exit_date="2026-01-02")
