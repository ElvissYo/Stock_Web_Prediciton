"""Collect ticker-matched RSS news for the NLP feature pipeline."""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
import sys

from kag.logging import configure_logging
from kag.market_data.top_universe import DEFAULT_TOP10_UNIVERSE_PATH, load_stock_metadata
from kag.news.api import NewsAPIConfig, collect_news_from_api
from kag.news.rss import collect_rss_news, parse_rss_sources, write_news_parquet


DEFAULT_OUTPUT_PATH = Path("data/news_raw.parquet")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", type=Path, default=DEFAULT_TOP10_UNIVERSE_PATH)
    parser.add_argument("--ticker", action="append", help="Limit to selected ticker(s).")
    parser.add_argument("--limit", type=int, default=500, help="Maximum ticker-article rows to save.")
    parser.add_argument(
        "--provider",
        choices=["rss", "gdelt", "newsapi"],
        default=os.getenv("NEWS_API_PROVIDER", "rss"),
        help="News source provider. Use gdelt for no-key API, newsapi for NewsAPI.org.",
    )
    parser.add_argument(
        "--rss-sources",
        default=os.getenv("NEWS_RSS_FEEDS"),
        help="Comma-separated 'Name|URL' entries. Defaults to built-in Indonesian market feeds.",
    )
    parser.add_argument("--api-key", default=os.getenv("NEWSAPI_API_KEY"))
    parser.add_argument("--language", default=os.getenv("NEWS_API_LANGUAGE", "id"))
    parser.add_argument("--start-date", help="Optional provider start date in YYYY-MM-DD format.")
    parser.add_argument("--end-date", help="Optional provider end date in YYYY-MM-DD format.")
    parser.add_argument("--max-per-ticker", type=int, default=25)
    parser.add_argument("--request-delay", type=float, default=1.5)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_logging()

    try:
        stocks = load_stock_metadata(args.universe, tickers=args.ticker)
        if args.provider == "rss":
            sources = parse_rss_sources(args.rss_sources)
            articles = collect_rss_news(sources, stocks, limit=args.limit)
        else:
            articles = collect_news_from_api(
                stocks,
                config=NewsAPIConfig(
                    provider=args.provider,
                    api_key=args.api_key,
                    language=args.language,
                    max_articles_per_ticker=args.max_per_ticker,
                    request_delay_seconds=args.request_delay,
                    start_date=args.start_date,
                    end_date=args.end_date,
                ),
                limit=args.limit,
            )
        rows = write_news_parquet(articles, args.output)
    except Exception:
        logger.exception("News collection failed")
        return 1

    logger.info("News collection succeeded; output=%s rows=%s", args.output, rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
