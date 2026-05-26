import pytest

from kag.features.nlp_features import (
    _lexicon_sentiment_score,
    build_nlp_feature_frame,
    preprocess_text,
)
from kag.market_data.top_universe import StockMetadata, ticker_aliases
from kag.news.rss import (
    NewsArticle,
    OpenGraphImageParser,
    extract_article_image_url,
    extract_tickers,
    write_news_parquet,
)


def test_extract_tickers_matches_configured_aliases():
    aliases = ticker_aliases(
        [
            StockMetadata(ticker="BBCA", yfinance_symbol="BBCA.JK"),
            StockMetadata(ticker="TLKM", yfinance_symbol="TLKM.JK"),
        ]
    )

    assert extract_tickers("Saham BBCA dan TLKM.JK kompak menguat", aliases) == ["BBCA", "TLKM"]


def test_preprocess_text_and_lexicon_sentiment():
    text = preprocess_text("<p>BBCA menguat dan laba tumbuh https://example.com</p>")

    assert "https" not in text
    assert _lexicon_sentiment_score(text) > 0


def test_open_graph_image_parser_extracts_real_metadata_url():
    parser = OpenGraphImageParser()
    parser.feed('<html><head><meta property="og:image" content="https://example.com/news.jpg"></head></html>')
    parser.close()

    assert parser.image_url == "https://example.com/news.jpg"


def test_open_graph_image_parser_resolves_relative_metadata_url():
    parser = OpenGraphImageParser(base_url="https://example.com/news/article")
    parser.feed('<html><head><meta property="og:image" content="/assets/news.jpg"></head></html>')
    parser.close()

    assert parser.image_url == "https://example.com/assets/news.jpg"


def test_extract_article_image_url_reads_feed_media_fields():
    entry = {
        "media_content": [{"url": "https://example.com/media.jpg"}],
        "enclosures": [{"href": "https://example.com/enclosure.jpg", "type": "image/jpeg"}],
    }

    assert extract_article_image_url(entry) == "https://example.com/media.jpg"


def test_write_news_parquet_includes_sentiment_and_image_columns(tmp_path):
    pd = pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")
    output = tmp_path / "news.parquet"

    rows = [
        NewsArticle(
            ticker="BBCA",
            date="2026-05-23",
            title="BBCA laba tumbuh",
            summary="Saham menguat dan kinerja positif",
            url="https://example.com/bbca",
            source="Example",
            image_url="https://example.com/bbca.jpg",
        )
    ]

    assert write_news_parquet(rows, output) == 1
    frame = pd.read_parquet(output)

    assert "sentiment_score" in frame.columns
    assert "provider" in frame.columns
    assert "image_url" in frame.columns
    assert frame.loc[0, "sentiment_score"] > 0
    assert frame.loc[0, "provider"] == "rss"
    assert frame.loc[0, "image_url"] == "https://example.com/bbca.jpg"


def test_write_news_parquet_deduplicates_provider_overlap(tmp_path):
    pd = pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")
    output = tmp_path / "news.parquet"

    rows = [
        NewsArticle(
            ticker="BBCA",
            date="2026-05-23",
            title="BBCA laba tumbuh",
            summary="Saham menguat",
            url="https://example.com/bbca?utm_source=gdelt",
            source="GDELT - example.com",
            provider="gdelt",
        ),
        NewsArticle(
            ticker="BBCA",
            date="2026-05-23",
            title="BBCA laba tumbuh",
            summary="Saham menguat dari API lain",
            url="https://example.com/bbca",
            source="NewsAPI - Example",
            provider="newsapi",
        ),
    ]

    assert write_news_parquet(rows, output) == 1
    frame = pd.read_parquet(output)

    assert len(frame) == 1
    assert frame.loc[0, "ticker"] == "BBCA"


def test_build_nlp_feature_frame_adds_source_diversity_features():
    pd = pytest.importorskip("pandas")
    pytest.importorskip("sklearn")

    news = pd.DataFrame(
        [
            {
                "ticker": "BBCA",
                "date": "2026-05-23",
                "title": "BBCA laba tumbuh",
                "summary": "Saham menguat positif",
                "url": "https://example.com/bbca-1",
                "source": "GDELT - example.com",
                "provider": "gdelt",
            },
            {
                "ticker": "BBCA",
                "date": "2026-05-23",
                "title": "BBCA laba tumbuh",
                "summary": "Duplikat dari API lain",
                "url": "https://example.com/bbca-1?utm_medium=api",
                "source": "NewsAPI - Example",
                "provider": "newsapi",
            },
            {
                "ticker": "BBCA",
                "date": "2026-05-23",
                "title": "BBCA volume transaksi naik",
                "summary": "Investor asing akumulasi",
                "url": "https://example.com/bbca-2",
                "source": "CNBC Indonesia Market",
                "provider": "rss",
            },
        ]
    )

    features = build_nlp_feature_frame(
        news,
        embedding_dimensions=2,
        sentiment_backend="lexicon",
        embedding_backend="hashing",
        pca_path=None,
    )

    row = features.iloc[0]
    assert row["news_count"] == 2
    assert row["source_count"] == 2
    assert row["provider_count"] == 2
    assert row["positive_news_count"] >= 1
    assert 0 <= row["source_diversity"] <= 1
