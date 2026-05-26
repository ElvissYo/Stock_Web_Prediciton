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
from kag.news.dedup import deduplicate_news_items
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
        choices=["rss", "gdelt", "newsapi", "all"],
        default=os.getenv("NEWS_API_PROVIDER", "rss"),
        help="News source provider. Use all to combine RSS, GDELT, and NewsAPI when configured.",
    )
    parser.add_argument(
        "--providers",
        default=os.getenv("NEWS_API_PROVIDERS"),
        help="Comma-separated providers to combine, for example: rss,gdelt,newsapi.",
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
    parser.add_argument(
        "--append-existing",
        action="store_true",
        default=os.getenv("NEWS_APPEND_EXISTING", "").lower() in {"1", "true", "yes"},
        help="Merge newly collected rows with the existing output file before deduplication.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_logging()

    try:
        stocks = load_stock_metadata(args.universe, tickers=args.ticker)
        providers = _resolve_providers(args.provider, args.providers, api_key=args.api_key)
        provider_limit = None if len(providers) > 1 else args.limit
        articles = []
        for provider in providers:
            try:
                provider_articles = _collect_provider_articles(provider, stocks, args, limit=provider_limit)
            except Exception:
                if len(providers) == 1:
                    raise
                logger.exception("Skipping failed news provider; provider=%s", provider)
                continue

            articles.extend(provider_articles)
            articles = deduplicate_news_items(articles)
            logger.info(
                "Collected provider news; provider=%s rows=%s unique_rows=%s",
                provider,
                len(provider_articles),
                len(articles),
            )

        if args.limit is not None:
            articles = articles[: args.limit]
        if args.append_existing and args.output.exists():
            existing_articles = _read_existing_news_articles(args.output)
            articles = deduplicate_news_items([*existing_articles, *articles])
            if args.limit is not None:
                articles = articles[: args.limit]
        rows = write_news_parquet(articles, args.output)
    except Exception:
        logger.exception("News collection failed")
        return 1

    logger.info("News collection succeeded; output=%s rows=%s", args.output, rows)
    return 0


def _resolve_providers(provider: str, providers: str | None, *, api_key: str | None) -> list[str]:
    valid_providers = {"rss", "gdelt", "newsapi"}
    if providers:
        selected = [item.strip().lower() for item in providers.split(",") if item.strip()]
    elif provider == "all":
        selected = ["rss", "gdelt", "newsapi"]
    else:
        selected = [provider.strip().lower()]

    unknown = sorted(set(selected) - valid_providers)
    if unknown:
        raise ValueError(f"Unknown news provider(s): {', '.join(unknown)}")

    resolved = []
    for item in selected:
        if item == "newsapi" and not api_key:
            if provider == "newsapi" or providers:
                raise ValueError("NEWSAPI_API_KEY is required when provider=newsapi")
            logger.warning("Skipping NewsAPI because NEWSAPI_API_KEY is not configured")
            continue
        if item not in resolved:
            resolved.append(item)

    if not resolved:
        raise ValueError("No usable news providers were configured")
    return resolved


def _collect_provider_articles(
    provider: str,
    stocks: list[object],
    args: argparse.Namespace,
    *,
    limit: int | None,
) -> list[object]:
    if provider == "rss":
        sources = parse_rss_sources(args.rss_sources)
        return collect_rss_news(sources, stocks, limit=limit)

    return collect_news_from_api(
        stocks,
        config=NewsAPIConfig(
            provider=provider,
            api_key=args.api_key,
            language=args.language,
            max_articles_per_ticker=args.max_per_ticker,
            request_delay_seconds=args.request_delay,
            start_date=args.start_date,
            end_date=args.end_date,
        ),
        limit=limit,
    )


def _read_existing_news_articles(path: Path) -> list[object]:
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError(
            "pandas is not installed. Run: .venv\\Scripts\\python.exe -m pip install -e \".[data]\""
        ) from exc

    from kag.news.rss import NewsArticle

    frame = pd.read_parquet(path)
    articles = []
    for row in frame.to_dict("records"):
        articles.append(
            NewsArticle(
                ticker=str(row.get("ticker") or ""),
                date=row.get("date") or "",
                title=str(row.get("title") or ""),
                summary=str(row.get("summary") or ""),
                url=str(row.get("url") or ""),
                source=str(row.get("source") or ""),
                sentiment_score=_optional_float(row.get("sentiment_score")),
                image_url=_optional_text(row.get("image_url")),
                provider=_optional_text(row.get("provider")),
            )
        )
    return articles


def _optional_float(value: object) -> float | None:
    try:
        if value is None or value != value:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_text(value: object) -> str | None:
    try:
        if value is None or value != value:
            return None
    except TypeError:
        pass
    text = str(value).strip()
    return text or None


if __name__ == "__main__":
    sys.exit(main())
