import json

import pytest

from kag.modeling.direction_model import FEATURE_COLUMNS, TARGET_COLUMN, split_by_date, train_direction_model


def test_split_by_date_uses_chronological_cutoff():
    pd = pytest.importorskip("pandas")
    dataset = pd.DataFrame(
        {
            "date": ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"],
            "value": [1, 2, 3, 4],
        }
    )

    train_frame, test_frame = split_by_date(dataset, test_size=0.25)

    assert train_frame["date"].tolist() == ["2026-01-01", "2026-01-02", "2026-01-03"]
    assert test_frame["date"].tolist() == ["2026-01-04"]


def test_split_by_date_validates_test_size():
    pd = pytest.importorskip("pandas")
    dataset = pd.DataFrame({"date": ["2026-01-01", "2026-01-02", "2026-01-03"]})

    with pytest.raises(ValueError, match="test_size"):
        split_by_date(dataset, test_size=1)


def test_train_direction_model_persists_model_and_metrics(tmp_path):
    pytest.importorskip("sklearn")
    rows = []
    for day in range(1, 31):
        for ticker, sector, offset in [
            ("AAA", "Financials", 0.001),
            ("BBB", "Energy", -0.001),
        ]:
            direction = 1 if (day + (ticker == "AAA")) % 2 == 0 else 0
            row = {
                "ticker": ticker,
                "date": f"2026-01-{day:02d}",
                "sector": sector,
                "close": 100 + day,
                "volume": 1000 + day,
                "return_1d": offset + (0.001 * day),
                "return_5d": offset + (0.002 * day),
                "rolling_mean_5d": offset,
                "rolling_vol_5d": 0.01,
                "rolling_mean_10d": offset,
                "rolling_vol_10d": 0.02,
                "sector_return_1d": offset,
                "correlated_peer_count": 2,
                "correlation_avg_abs": 0.5,
                "target_next_return": 0.01 if direction else -0.01,
                TARGET_COLUMN: direction,
            }
            rows.append(row)

    pd = pytest.importorskip("pandas")
    dataset_path = tmp_path / "features.csv"
    pd.DataFrame(rows).to_csv(dataset_path, index=False)
    model_path = tmp_path / "model.joblib"
    metrics_path = tmp_path / "metrics.json"

    result = train_direction_model(
        dataset_path,
        model_path=model_path,
        metrics_path=metrics_path,
        prefer_lightgbm=False,
    )

    metrics_payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    assert model_path.exists()
    assert metrics_path.exists()
    assert result.model_type == "random_forest"
    assert result.train_rows > result.test_rows
    assert "accuracy" in result.metrics
    assert metrics_payload["model_type"] == "random_forest"


def test_train_direction_model_rejects_missing_columns(tmp_path):
    pd = pytest.importorskip("pandas")
    dataset_path = tmp_path / "features.csv"
    pd.DataFrame({"date": ["2026-01-01"], "ticker": ["AAA"]}).to_csv(dataset_path, index=False)

    with pytest.raises(ValueError, match="dataset is missing required columns"):
        train_direction_model(dataset_path, prefer_lightgbm=False)


def test_feature_columns_do_not_include_target():
    assert TARGET_COLUMN not in FEATURE_COLUMNS
