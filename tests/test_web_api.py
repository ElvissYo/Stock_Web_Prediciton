from http import HTTPStatus

import kag.web.api as web_api
from kag.web.api import api_response, artifact_status


def test_api_health_route():
    status, payload = api_response("/api/health", {})

    assert status == HTTPStatus.OK
    assert payload == {"status": "ok"}


def test_api_symbols_route_includes_jkse():
    status, payload = api_response("/api/market/symbols", {})

    assert status == HTTPStatus.OK
    assert any(row["ticker"] == "IHSG" and row["symbol"] == "^JKSE" for row in payload["symbols"])
    assert len(payload["symbols"]) == 101
    assert any(row["ticker"] == "BBCA" and row["name"] for row in payload["symbols"])
    bbri = next(row for row in payload["symbols"] if row["ticker"] == "BBRI")
    assert bbri["domain"] == "bri.co.id"
    assert bbri["logo_url"].startswith("https://")


def test_api_stocks_metadata_route():
    status, payload = api_response("/api/stocks/metadata", {"limit": ["30"]})

    assert status == HTTPStatus.OK
    assert payload["status"] == "ok"
    assert payload["source"] == "data/company_metadata.json"
    assert len(payload["stocks"]) == 30
    assert any(row["ticker"] == "BBCA" and row["domain"] == "bca.co.id" for row in payload["stocks"])


def test_api_market_movers_route(monkeypatch):
    def fake_load_market_movers(*, limit):
        assert limit == 10
        return {
            "source": "prices.parquet",
            "available_tickers": 2,
            "gainers": [{"ticker": "BBCA", "change_pct": 0.01}],
            "losers": [{"ticker": "BMRI", "change_pct": -0.02}],
        }

    monkeypatch.setattr(web_api, "load_market_movers", fake_load_market_movers)

    status, payload = api_response("/api/market/movers", {"limit": ["10"]})

    assert status == HTTPStatus.OK
    assert payload["status"] == "ok"
    assert payload["available_tickers"] == 2
    assert payload["gainers"][0]["ticker"] == "BBCA"


def test_api_market_profile_route(monkeypatch):
    def fake_load_company_profile(ticker):
        assert ticker == "BBCA"
        return {
            "ticker": "BBCA",
            "symbol": "BBCA.JK",
            "name": "PT Bank Central Asia Tbk",
            "logo_url": "https://example.test/bbca.png",
        }

    monkeypatch.setattr(web_api, "load_company_profile", fake_load_company_profile)

    status, payload = api_response("/api/market/profile", {"ticker": ["BBCA"]})

    assert status == HTTPStatus.OK
    assert payload["status"] == "ok"
    assert payload["profile"]["ticker"] == "BBCA"
    assert payload["profile"]["logo_url"].startswith("https://")


def test_api_unknown_route_returns_not_found():
    status, payload = api_response("/api/missing", {})

    assert status == HTTPStatus.NOT_FOUND
    assert payload["status"] == "error"


def test_api_candles_route_supports_intraday_period(monkeypatch):
    calls = {}

    def fake_load_local_price_ohlcv(symbol, *, period, interval):
        raise AssertionError("intraday candles should not read local daily artifacts")

    def fake_load_yfinance_ohlcv(symbol, *, period, interval):
        calls["symbol"] = symbol
        calls["period"] = period
        calls["interval"] = interval
        return []

    monkeypatch.setattr(web_api, "load_local_price_ohlcv", fake_load_local_price_ohlcv)
    monkeypatch.setattr(web_api, "load_yfinance_ohlcv", fake_load_yfinance_ohlcv)

    status, payload = api_response(
        "/api/market/candles",
        {"symbol": ["^JKSE"], "period": ["1d"], "interval": ["5m"]},
    )

    assert status == HTTPStatus.OK
    assert payload["period"] == "1d"
    assert payload["interval"] == "5m"
    assert calls == {"symbol": "^JKSE", "period": "1d", "interval": "5m"}


def test_api_candles_route_falls_back_when_local_daily_fails(monkeypatch):
    calls = {}

    def fake_load_local_price_ohlcv(symbol, *, period, interval):
        assert symbol == "^JKSE"
        assert period == "1d"
        assert interval == "1d"
        raise RuntimeError("bad local parquet")

    def fake_load_yfinance_ohlcv(symbol, *, period, interval):
        calls["symbol"] = symbol
        calls["period"] = period
        calls["interval"] = interval
        return [{"date": "2026-05-25", "close": 7300.0, "source": "Yahoo Finance / yfinance"}]

    monkeypatch.setattr(web_api, "load_local_price_ohlcv", fake_load_local_price_ohlcv)
    monkeypatch.setattr(web_api, "load_yfinance_ohlcv", fake_load_yfinance_ohlcv)

    status, payload = api_response(
        "/api/market/candles",
        {"symbol": ["^JKSE"], "period": ["1d"], "interval": ["1d"]},
    )

    assert status == HTTPStatus.OK
    assert payload["period"] == "1d"
    assert payload["interval"] == "1d"
    assert payload["candles"]
    assert calls == {"symbol": "^JKSE", "period": "1d", "interval": "1d"}


def test_api_candles_route_rejects_bad_interval():
    status, payload = api_response(
        "/api/market/candles",
        {"symbol": ["^JKSE"], "period": ["1d"], "interval": ["bad"]},
    )

    assert status == HTTPStatus.BAD_REQUEST
    assert payload["status"] == "error"


def test_api_projection_route_builds_projection(monkeypatch):
    def fake_load_local_price_ohlcv(symbol, *, period, interval):
        assert symbol == "BBCA.JK"
        assert period == "max"
        assert interval == "1d"
        return [
            {"date": "2026-01-01", "close": 100.0},
            {"date": "2026-01-02", "close": 101.0},
            {"date": "2026-01-05", "close": 102.0},
        ]

    monkeypatch.setattr(web_api, "load_local_price_ohlcv", fake_load_local_price_ohlcv)
    monkeypatch.setattr(
        web_api,
        "generate_latest_global_prediction",
        lambda ticker: {"status": "ok", "ticker": ticker, "predicted_direction": 1, "confidence": 0.4},
    )

    status, payload = api_response(
        "/api/projection",
        {
            "ticker": ["BBCA"],
            "amount": ["1000000"],
            "entry_date": ["2026-01-01"],
            "exit_date": ["2026-01-05"],
        },
    )

    assert status == HTTPStatus.OK
    assert payload["status"] == "ok"
    assert payload["ticker"] == "BBCA"
    assert payload["projection"]["initial_amount"] == 1_000_000
    assert payload["projection"]["exit_value"] == 1_020_000


def test_api_projection_route_validates_amount():
    status, payload = api_response(
        "/api/projection",
        {
            "ticker": ["BBCA"],
            "amount": ["0"],
            "entry_date": ["2026-01-01"],
            "exit_date": ["2026-01-05"],
        },
    )

    assert status == HTTPStatus.BAD_REQUEST
    assert payload["status"] == "error"


def test_artifact_status_reports_real_paths():
    rows = artifact_status()

    assert any(row["path"] == "data/final_dataset.parquet" for row in rows)
    assert all("exists" in row for row in rows)
