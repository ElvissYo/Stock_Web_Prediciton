from kag.market_data.top_universe import StockMetadata
from kag.news.api import (
    _articles_from_gdelt_payload,
    _articles_from_newsapi_payload,
    build_news_query,
    clean_company_name,
)


def test_build_news_query_uses_ticker_and_clean_company_name():
    stock = StockMetadata(
        ticker="BBCA",
        yfinance_symbol="BBCA.JK",
        name="PT Bank Central Asia Tbk",
    )

    assert clean_company_name(stock.name) == "Bank Central Asia"
    assert build_news_query(stock, provider="gdelt") == '(BBCA OR "Bank Central Asia")'


def test_articles_from_gdelt_payload_maps_rows():
    stock = StockMetadata(ticker="BBCA", yfinance_symbol="BBCA.JK", name="PT Bank Central Asia Tbk")
    payload = {
        "articles": [
            {
                "title": "BBCA menguat",
                "url": "https://example.com/bbca",
                "seendate": "20260523120000",
                "domain": "example.com",
                "socialimage": "https://example.com/bbca.jpg",
            }
        ]
    }

    rows = _articles_from_gdelt_payload(payload, stock)

    assert rows[0].ticker == "BBCA"
    assert rows[0].date == "2026-05-23"
    assert rows[0].source == "GDELT - example.com"
    assert rows[0].image_url == "https://example.com/bbca.jpg"


def test_articles_from_newsapi_payload_maps_rows():
    stock = StockMetadata(ticker="BBRI", yfinance_symbol="BBRI.JK", name="PT Bank Rakyat Indonesia")
    payload = {
        "status": "ok",
        "articles": [
            {
                "title": "BBRI cetak laba",
                "description": "Bank besar mencatat kinerja positif",
                "url": "https://example.com/bbri",
                "publishedAt": "2026-05-23T12:00:00Z",
                "source": {"name": "Example News"},
                "urlToImage": "https://example.com/bbri.jpg",
            }
        ],
    }

    rows = _articles_from_newsapi_payload(payload, stock)

    assert rows[0].ticker == "BBRI"
    assert rows[0].date == "2026-05-23"
    assert rows[0].source == "NewsAPI - Example News"
    assert rows[0].image_url == "https://example.com/bbri.jpg"
