import pytest

from kag.features.fusion import build_final_dataset_frame


def test_build_final_dataset_frame_left_joins_nlp_and_adds_targets(tmp_path):
    pd = pytest.importorskip("pandas")
    pytest.importorskip("joblib")

    metadata_path = tmp_path / "universe.csv"
    metadata_path.write_text(
        "\n".join(
            [
                "ticker,yfinance_symbol,name,sector,market_cap_rank,beta",
                "BBCA,BBCA.JK,PT Bank Central Asia Tbk,Financials,1,",
            ]
        ),
        encoding="utf-8",
    )
    price_features = pd.DataFrame(
        [
            {"ticker": "BBCA", "date": "2026-01-01", "close": 100.0, "return_1d": 0.01},
            {"ticker": "BBCA", "date": "2026-01-02", "close": 110.0, "return_1d": 0.10},
            {"ticker": "BBCA", "date": "2026-01-03", "close": 105.0, "return_1d": -0.045},
        ]
    )
    nlp_features = pd.DataFrame(
        [
            {
                "ticker": "BBCA",
                "date": "2026-01-02",
                "sentiment_mean": 0.5,
                "sentiment_std": 0.0,
                "news_count": 2,
                "sentiment_momentum": 0.5,
                **{f"embedding_dim_{index}": 0.0 for index in range(50)},
            }
        ]
    )

    dataset = build_final_dataset_frame(
        price_features,
        nlp_features,
        metadata_path=metadata_path,
        encoders_path=tmp_path / "encoders.pkl",
    )

    first_row = dataset[dataset["date"] == pd.Timestamp("2026-01-01")].iloc[0]
    second_row = dataset[dataset["date"] == pd.Timestamp("2026-01-02")].iloc[0]
    third_row = dataset[dataset["date"] == pd.Timestamp("2026-01-03")].iloc[0]
    assert first_row["news_count"] == 0
    assert second_row["news_count"] == 0
    assert third_row["news_count"] == 2
    assert first_row["target_return"] == pytest.approx(0.10)
    assert second_row["direction"] == 0
    assert "target_excess_return" in dataset.columns
    assert "outperform_market" in dataset.columns
    assert (tmp_path / "encoders.pkl").exists()


def test_build_final_dataset_frame_can_use_same_day_nlp(tmp_path):
    pd = pytest.importorskip("pandas")
    pytest.importorskip("joblib")

    metadata_path = tmp_path / "universe.csv"
    metadata_path.write_text(
        "\n".join(
            [
                "ticker,yfinance_symbol,name,sector,market_cap_rank,beta",
                "BBCA,BBCA.JK,PT Bank Central Asia Tbk,Financials,1,",
            ]
        ),
        encoding="utf-8",
    )
    price_features = pd.DataFrame(
        [
            {"ticker": "BBCA", "date": "2026-01-01", "close": 100.0, "return_1d": 0.01},
            {"ticker": "BBCA", "date": "2026-01-02", "close": 110.0, "return_1d": 0.10},
        ]
    )
    nlp_features = pd.DataFrame(
        [
            {
                "ticker": "BBCA",
                "date": "2026-01-02",
                "sentiment_mean": 0.5,
                "sentiment_std": 0.0,
                "news_count": 2,
                "sentiment_momentum": 0.5,
                **{f"embedding_dim_{index}": 0.0 for index in range(50)},
            }
        ]
    )

    dataset = build_final_dataset_frame(
        price_features,
        nlp_features,
        metadata_path=metadata_path,
        encoders_path=tmp_path / "encoders.pkl",
        nlp_lag_trading_days=0,
    )

    second_row = dataset[dataset["date"] == pd.Timestamp("2026-01-02")].iloc[0]
    assert second_row["news_count"] == 2
