import pytest

from kag.modeling.global_model import evaluate_time_series_cv, infer_feature_columns


def test_infer_feature_columns_supports_baseline_and_nlp_modes():
    pd = pytest.importorskip("pandas")
    frame = pd.DataFrame(
        {
            "date": ["2026-01-01"],
            "ticker": ["BBCA"],
            "sector": ["Financials"],
            "close": [100.0],
            "return_1d": [0.01],
            "sentiment_mean": [0.5],
            "embedding_dim_0": [0.1],
            "target_return": [0.02],
            "next_day_price": [102.0],
            "direction": [1],
        }
    )

    _, baseline_numeric = infer_feature_columns(frame, include_nlp=False)
    _, nlp_numeric = infer_feature_columns(frame, include_nlp=True)

    assert "return_1d" in baseline_numeric
    assert "sentiment_mean" not in baseline_numeric
    assert "sentiment_mean" in nlp_numeric
    assert "embedding_dim_0" in nlp_numeric


def test_evaluate_time_series_cv_uses_date_order():
    pd = pytest.importorskip("pandas")
    pytest.importorskip("sklearn")

    rows = []
    for day in range(1, 9):
        for ticker, sector, offset in [("AAA", "Financials", 0.01), ("BBB", "Energy", -0.01)]:
            close = 100 + day
            target_return = offset + (day * 0.001)
            rows.append(
                {
                    "date": f"2026-01-{day:02d}",
                    "ticker": ticker,
                    "sector": sector,
                    "close": close,
                    "return_1d": target_return / 2,
                    "target_return": target_return,
                    "next_day_price": close * (1 + target_return),
                    "direction": int(target_return > 0),
                }
            )
    frame = pd.DataFrame(rows)
    categorical, numeric = infer_feature_columns(frame, include_nlp=False)
    metrics = evaluate_time_series_cv(
        frame,
        feature_columns=categorical + numeric,
        categorical_features=categorical,
        numeric_features=numeric,
        n_splits=2,
        prefer_lightgbm=False,
    )

    assert metrics["folds"] == 2
    assert metrics["evaluation_rows"] > 0
    assert "mape" in metrics
    assert "rank_ic" in metrics
    assert "top_n_excess_return" in metrics
    assert metrics["gap_dates"] == 1


def test_evaluate_time_series_cv_supports_purged_gap_dates():
    pd = pytest.importorskip("pandas")
    pytest.importorskip("sklearn")

    rows = []
    for day in range(1, 12):
        for ticker, sector, offset in [("AAA", "Financials", 0.01), ("BBB", "Energy", -0.01)]:
            close = 100 + day
            target_return = offset + (day * 0.001)
            rows.append(
                {
                    "date": f"2026-01-{day:02d}",
                    "ticker": ticker,
                    "sector": sector,
                    "close": close,
                    "return_1d": target_return / 2,
                    "target_return": target_return,
                    "next_day_price": close * (1 + target_return),
                    "direction": int(target_return > 0),
                }
            )
    frame = pd.DataFrame(rows)
    categorical, numeric = infer_feature_columns(frame, include_nlp=False)

    metrics = evaluate_time_series_cv(
        frame,
        feature_columns=categorical + numeric,
        categorical_features=categorical,
        numeric_features=numeric,
        n_splits=2,
        gap_dates=2,
        selection_top_n=1,
        prefer_lightgbm=False,
    )

    assert metrics["folds"] == 2
    assert metrics["gap_dates"] == 2
    assert metrics["selection_top_n"] == 1
    assert metrics["selection_dates"] > 0
