"""News API ingestion providers for ticker-level Indonesian stock news."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
import time
from typing import Any, Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from kag.market_data.top_universe import StockMetadata
from kag.news.dedup import deduplicate_news_items
from kag.news.rss import NewsArticle, extract_article_image_url


logger = logging.getLogger(__name__)

GDELT_DOC_API_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
NEWSAPI_EVERYTHING_URL = "https://newsapi.org/v2/everything"
DEFAULT_USER_AGENT = "IHSG-KAG-NewsAPICollector/0.1"
COMPANY_SUFFIX_PATTERN = re.compile(
    r"\b(PT|Tbk|Perseroan|Persero|Terbuka)\b|\([^)]*\)",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class NewsAPIConfig:
    """Configuration for external news API collection."""

    provider: str = "gdelt"
    api_key: str | None = None
    language: str = "id"
    max_articles_per_ticker: int = 25
    request_delay_seconds: float = 0.2
    start_date: str | None = None
    end_date: str | None = None


def collect_news_from_api(
    stocks: Iterable[StockMetadata],
    *,
    config: NewsAPIConfig,
    limit: int | None = 500,
) -> list[NewsArticle]:
    """Collect ticker-tagged articles from a configured news API provider."""

    provider = config.provider.lower().strip()
    if provider not in {"gdelt", "newsapi"}:
        raise ValueError("news API provider must be one of: gdelt, newsapi")
    if provider == "newsapi" and not config.api_key:
        raise ValueError("NEWSAPI_API_KEY is required when provider=newsapi")

    articles: list[NewsArticle] = []
    for stock in stocks:
        try:
            provider_rows = _fetch_provider_rows(stock, config=config)
        except Exception:
            logger.exception("News API fetch failed; provider=%s ticker=%s", provider, stock.ticker)
            continue

        for article in provider_rows:
            articles.append(article)
        if limit is not None and len(deduplicate_news_items(articles)) >= limit:
            return deduplicate_news_items(articles)[:limit]

        if config.request_delay_seconds > 0:
            time.sleep(config.request_delay_seconds)

    deduplicated = deduplicate_news_items(articles)
    if limit is not None:
        return deduplicated[:limit]
    return deduplicated


def build_news_query(stock: StockMetadata, *, provider: str) -> str:
    """Build a conservative query for ticker plus company name."""

    ticker = stock.ticker.upper()
    company = clean_company_name(stock.name)
    if not company or company.upper() == ticker:
        return ticker

    if provider == "gdelt":
        return f'({ticker} OR "{company}")'
    return f'{ticker} OR "{company}"'


def clean_company_name(name: str) -> str:
    """Remove legal suffixes from company names for broader article matching."""

    without_suffix = COMPANY_SUFFIX_PATTERN.sub(" ", name)
    return " ".join(without_suffix.replace(".", " ").replace(",", " ").split()).strip()


def _fetch_provider_rows(stock: StockMetadata, *, config: NewsAPIConfig) -> list[NewsArticle]:
    provider = config.provider.lower().strip()
    if provider == "gdelt":
        payload = _fetch_json(_gdelt_url(stock, config=config))
        return _articles_from_gdelt_payload(payload, stock)

    payload = _fetch_json(_newsapi_url(stock, config=config))
    return _articles_from_newsapi_payload(payload, stock)


def _gdelt_url(stock: StockMetadata, *, config: NewsAPIConfig) -> str:
    query = build_news_query(stock, provider="gdelt")
    gdelt_language = _gdelt_language(config.language)
    if gdelt_language:
        query = f"{query} sourcelang:{gdelt_language}"

    parameters = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "sort": "datedesc",
        "maxrecords": max(1, min(config.max_articles_per_ticker, 250)),
    }
    if config.start_date:
        parameters["startdatetime"] = _gdelt_datetime(config.start_date)
    if config.end_date:
        parameters["enddatetime"] = _gdelt_datetime(config.end_date)
    return f"{GDELT_DOC_API_URL}?{urlencode(parameters)}"


def _newsapi_url(stock: StockMetadata, *, config: NewsAPIConfig) -> str:
    parameters = {
        "q": build_news_query(stock, provider="newsapi"),
        "language": config.language,
        "sortBy": "publishedAt",
        "pageSize": max(1, min(config.max_articles_per_ticker, 100)),
        "apiKey": config.api_key or "",
    }
    if config.start_date:
        parameters["from"] = config.start_date
    if config.end_date:
        parameters["to"] = config.end_date
    return f"{NEWSAPI_EVERYTHING_URL}?{urlencode(parameters)}"


def _articles_from_gdelt_payload(payload: dict[str, Any], stock: StockMetadata) -> list[NewsArticle]:
    rows = []
    for item in payload.get("articles", []) or []:
        title = _clean_text(item.get("title"))
        url = _clean_text(item.get("url"))
        if not title or not url:
            continue

        source_name = _clean_text(item.get("sourceCommonName") or item.get("domain")) or "GDELT"
        rows.append(
            NewsArticle(
                ticker=stock.ticker,
                date=_date_text(item.get("seendate") or item.get("datetime")),
                title=title,
                summary=_clean_text(item.get("snippet") or ""),
                url=url,
                source=f"GDELT - {source_name}",
                image_url=extract_article_image_url(
                    {"image_url": item.get("socialimage") or item.get("image")},
                    article_url=url,
                ),
                provider="gdelt",
            )
        )
    return rows


def _articles_from_newsapi_payload(payload: dict[str, Any], stock: StockMetadata) -> list[NewsArticle]:
    if payload.get("status") == "error":
        raise RuntimeError(payload.get("message") or "NewsAPI request failed")

    rows = []
    for item in payload.get("articles", []) or []:
        title = _clean_text(item.get("title"))
        url = _clean_text(item.get("url"))
        if not title or not url:
            continue

        source = item.get("source") or {}
        rows.append(
            NewsArticle(
                ticker=stock.ticker,
                date=_date_text(item.get("publishedAt")),
                title=title,
                summary=_clean_text(item.get("description") or item.get("content") or ""),
                url=url,
                source=f"NewsAPI - {_clean_text(source.get('name')) or 'Unknown'}",
                image_url=extract_article_image_url(
                    {"image_url": item.get("urlToImage")},
                    article_url=url,
                ),
                provider="newsapi",
            )
        )
    return rows


def _fetch_json(url: str) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
    with urlopen(request, timeout=30) as response:
        text = response.read().decode("utf-8", errors="replace")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            preview = " ".join(text[:200].split())
            raise ValueError(f"Provider returned non-JSON response: {preview}") from exc


def _gdelt_datetime(date_text: str) -> str:
    return date_text.replace("-", "")[:8] + "000000"


def _gdelt_language(language: str | None) -> str | None:
    if not language:
        return None

    normalized = language.strip().lower()
    if normalized in {"", "all", "*"}:
        return None

    language_map = {
        "id": "Indonesian",
        "indonesian": "Indonesian",
        "en": "English",
        "english": "English",
    }
    return language_map.get(normalized, language)


def _date_text(value: Any) -> str:
    if value is None:
        return datetime.now(tz=timezone.utc).date().isoformat()

    text = str(value).strip()
    if not text:
        return datetime.now(tz=timezone.utc).date().isoformat()

    if len(text) >= 8 and text[:8].isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return text[:10]


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split()).strip()


def write_api_news_debug_json(payload: dict[str, Any], output_path: str | Path) -> None:
    """Optional helper for storing provider responses while debugging API coverage."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
