import pytest

from kag.features.technical_indicators import PRICE_FEATURE_COLUMNS, build_price_feature_frame


def test_build_price_feature_frame_adds_expected_indicators():
    pd = pytest.importorskip("pandas")

    rows = []
    for index in range(230):
        rows.append(
            {
                "ticker": "BBCA",
                "yfinance_symbol": "BBCA.JK",
                "date": pd.Timestamp("2025-01-01") + pd.Timedelta(days=index),
                "open": 100 + index,
                "high": 101 + index,
                "low": 99 + index,
                "close": 100 + index,
                "adj_close": 100 + index,
                "volume": 1000 + index,
                "source": "yfinance",
                "interval": "1d",
            }
        )

    features = build_price_feature_frame(pd.DataFrame(rows))

    assert set(PRICE_FEATURE_COLUMNS).issubset(features.columns)
    assert features.iloc[-1]["SMA_200"] > 0
    assert features.iloc[-1]["return_5d"] == pytest.approx((329 / 324) - 1)
    assert "target_return" not in features.columns
