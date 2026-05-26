"""RSS news ingestion and ticker extraction for IDX stocks."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
import logging
from pathlib import Path
import re
from urllib.parse import urljoin
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
from typing import Iterable

from kag.market_data.top_universe import StockMetadata, ticker_aliases
from kag.news.dedup import deduplicate_news_items, infer_provider_from_source


logger = logging.getLogger(__name__)

DEFAULT_RSS_SOURCES = (
    ("CNBC Indonesia Market", "https://www.cnbcindonesia.com/market/rss"),
    ("Bisnis Finansial", "https://finansial.bisnis.com/rss"),
    ("Kontan Investasi", "https://investasi.kontan.co.id/rss"),
)
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class RSSSource:
    """RSS source definition."""

    name: str
    url: str


@dataclass(frozen=True)
class NewsArticle:
    """Ticker-level article row persisted to news_raw.parquet."""

    ticker: str
    date: str
    title: str
    summary: str
    url: str
    source: str
    sentiment_score: float | None = None
    image_url: str | None = None
    provider: str | None = None

    def to_record(self) -> dict[str, str | float | None]:
        return asdict(self)


def parse_rss_sources(raw_sources: str | None = None) -> list[RSSSource]:
    """Parse RSS source configuration.

    Format for custom sources: ``Source Name|https://example/rss,Other|https://...``.
    """

    if not raw_sources:
        return [RSSSource(name, url) for name, url in DEFAULT_RSS_SOURCES]

    sources = []
    for item in raw_sources.split(","):
        value = item.strip()
        if not value:
            continue
        if "|" not in value:
            raise ValueError(
                "RSS source entries must use 'Source Name|https://example/rss' format"
            )
        name, url = value.split("|", 1)
        sources.append(RSSSource(name=name.strip(), url=url.strip()))

    if not sources:
        raise ValueError("No valid RSS sources were configured")
    return sources


def collect_rss_news(
    sources: Iterable[RSSSource],
    stocks: Iterable[StockMetadata],
    *,
    limit: int | None = 500,
) -> list[NewsArticle]:
    """Fetch RSS feeds and return ticker-matched article rows."""

    aliases = ticker_aliases(stocks)
    articles: list[NewsArticle] = []

    for source in sources:
        for entry in _source_entries(source):
            title = _clean_text(_entry_value(entry, "title"))
            summary = _clean_text(
                _entry_value(entry, "summary")
                or _entry_value(entry, "description")
                or _entry_value(entry, "subtitle")
            )
            url = _entry_value(entry, "link")
            date = _entry_date(entry)
            matched_tickers = extract_tickers(f"{title} {summary}", aliases)
            image_url = extract_article_image_url(entry, article_url=url)

            for ticker in matched_tickers:
                articles.append(
                    NewsArticle(
                        ticker=ticker,
                        date=date,
                        title=title,
                        summary=summary,
                        url=url,
                        source=source.name,
                        image_url=image_url,
                        provider="rss",
                    )
                )

    deduplicated = deduplicate_news_items(articles)
    if limit is not None:
        return deduplicated[:limit]
    return deduplicated


def extract_tickers(text: str, aliases: dict[str, set[str]]) -> list[str]:
    """Extract configured tickers from article title/summary text."""

    normalized = text.upper()
    matched = []
    for ticker, ticker_aliases_ in aliases.items():
        for alias in ticker_aliases_:
            pattern = rf"(?<![A-Z0-9]){re.escape(alias.upper())}(?![A-Z0-9])"
            if re.search(pattern, normalized):
                matched.append(ticker)
                break
    return sorted(set(matched))


def write_news_parquet(articles: Iterable[NewsArticle], output_path: str | Path) -> int:
    """Write raw ticker-level news rows to Parquet."""

    pd = _require_pandas()
    rows = [article.to_record() for article in deduplicate_news_items(articles)]
    if not rows:
        raise ValueError("No ticker-matched news articles were collected")

    frame = pd.DataFrame(rows)
    if "provider" not in frame.columns:
        frame["provider"] = None
    frame["provider"] = [
        _clean_provider(provider) or infer_provider_from_source(source)
        for provider, source in zip(frame["provider"], frame["source"], strict=False)
    ]
    if "sentiment_score" not in frame.columns:
        frame["sentiment_score"] = None
    missing_sentiment = frame["sentiment_score"].isna()
    if missing_sentiment.any():
        frame.loc[missing_sentiment, "sentiment_score"] = _article_sentiment_scores(
            frame.loc[missing_sentiment]
        )
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
    frame = frame.dropna(subset=["date", "ticker", "title"])
    frame = frame[
        [
            "ticker",
            "date",
            "title",
            "summary",
            "url",
            "source",
            "provider",
            "sentiment_score",
            "image_url",
        ]
    ]
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        frame.to_parquet(path, index=False)
    except ImportError as exc:
        raise RuntimeError(
            "Parquet support is not installed. Run: .venv\\Scripts\\python.exe -m pip install -e \".[data]\""
        ) from exc
    return len(frame)


def _clean_provider(value: object) -> str:
    if value is None:
        return ""
    try:
        if value != value:
            return ""
    except TypeError:
        pass
    return " ".join(str(value).lower().split()).strip()


def _entry_date(entry: object) -> str:
    parsed = _entry_value(entry, "published_parsed") or _entry_value(entry, "updated_parsed")
    if parsed:
        return datetime(*parsed[:6], tzinfo=timezone.utc).date().isoformat()

    for field_name in ("published", "updated", "created"):
        value = _entry_value(entry, field_name)
        if len(value) >= 10:
            try:
                return parsedate_to_datetime(value).date().isoformat()
            except (TypeError, ValueError, IndexError):
                return value[:10]

    return datetime.now(tz=timezone.utc).date().isoformat()


def _clean_text(value: str) -> str:
    without_tags = HTML_TAG_PATTERN.sub(" ", value)
    return " ".join(without_tags.split()).strip()


def extract_article_image_url(entry: object | None = None, *, article_url: str = "") -> str | None:
    """Extract a real article image from RSS/API metadata or article og:image."""

    image_url = _entry_image_url(entry) if entry is not None else None
    if image_url:
        return image_url
    if not article_url:
        return None
    return fetch_og_image(article_url)


def fetch_og_image(article_url: str, *, timeout: float = 8) -> str | None:
    """Fetch article page metadata and return og:image/twitter image if available."""

    try:
        request = Request(article_url, headers={"User-Agent": "IHSG-KAG-NewsImageFetcher/0.1"})
        with urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            html = response.read(400_000).decode(charset, errors="replace")
    except Exception:
        logger.debug("Could not fetch og:image; url=%s", article_url, exc_info=True)
        return None

    parser = OpenGraphImageParser(base_url=article_url)
    parser.feed(html)
    parser.close()
    return parser.image_url


class OpenGraphImageParser(HTMLParser):
    """Small metadata parser for article thumbnails."""

    def __init__(self, *, base_url: str = "") -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.image_url: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.image_url or tag.lower() != "meta":
            return

        attributes = {key.lower(): value or "" for key, value in attrs}
        key = attributes.get("property") or attributes.get("name")
        if key not in {"og:image", "og:image:secure_url", "twitter:image"}:
            return

        content = attributes.get("content", "").strip()
        image_url = urljoin(self.base_url, content)
        if _is_http_url(image_url):
            self.image_url = image_url


def _source_entries(source: RSSSource) -> list[object]:
    feedparser = _optional_feedparser()
    if feedparser is not None:
        try:
            feed = feedparser.parse(
                source.url,
                request_headers={"User-Agent": "IHSG-KAG-NewsCollector/0.1"},
            )
        except Exception:
            logger.exception("RSS fetch failed; source=%s url=%s", source.name, source.url)
            return []

        if getattr(feed, "bozo", False):
            logger.warning(
                "RSS parser reported an issue; source=%s url=%s",
                source.name,
                source.url,
            )
        return list(getattr(feed, "entries", []))

    try:
        return _stdlib_rss_entries(source.url)
    except Exception:
        logger.exception("RSS fetch failed; source=%s url=%s", source.name, source.url)
        return []


def _stdlib_rss_entries(url: str) -> list[dict[str, str]]:
    request = Request(url, headers={"User-Agent": "IHSG-KAG-NewsCollector/0.1"})
    with urlopen(request, timeout=30) as response:
        payload = response.read()

    root = ET.fromstring(payload)
    entries = []
    for item in root.findall(".//item"):
        entries.append(
            {
                "title": _child_text(item, "title"),
                "summary": _child_text(item, "description"),
                "link": _child_text(item, "link"),
                "published": _child_text(item, "pubDate"),
                "image_url": _rss_item_image(item),
            }
        )

    atom_namespace = "{http://www.w3.org/2005/Atom}"
    for item in root.findall(f".//{atom_namespace}entry"):
        link = ""
        link_element = item.find(f"{atom_namespace}link")
        if link_element is not None:
            link = link_element.attrib.get("href", "")
        entries.append(
            {
                "title": _child_text(item, f"{atom_namespace}title"),
                "summary": _child_text(item, f"{atom_namespace}summary"),
                "link": link,
                "published": _child_text(item, f"{atom_namespace}published"),
                "updated": _child_text(item, f"{atom_namespace}updated"),
                "image_url": _atom_item_image(item),
            }
        )
    return entries


def _child_text(element: ET.Element, tag: str) -> str:
    child = element.find(tag)
    if child is None or child.text is None:
        return ""
    return child.text


def _entry_value(entry: object, field_name: str) -> str:
    if isinstance(entry, dict):
        value = entry.get(field_name, "")
    else:
        value = getattr(entry, field_name, "")
    if value is None:
        return ""
    return value


def _entry_image_url(entry: object) -> str | None:
    for field_name in ("image_url", "image", "urlToImage", "socialimage"):
        value = _mapping_or_attr_value(entry, field_name)
        if _is_http_url(value):
            return str(value).strip()

    for field_name in ("media_content", "media_thumbnail"):
        media_rows = _mapping_or_attr_value(entry, field_name) or []
        for media in media_rows:
            url = _mapping_or_attr_value(media, "url")
            if _is_http_url(url):
                return str(url).strip()

    enclosures = _mapping_or_attr_value(entry, "enclosures") or []
    for enclosure in enclosures:
        url = _mapping_or_attr_value(enclosure, "href") or _mapping_or_attr_value(enclosure, "url")
        mime_type = str(_mapping_or_attr_value(enclosure, "type") or "")
        if _is_http_url(url) and (not mime_type or mime_type.startswith("image/")):
            return str(url).strip()

    links = _mapping_or_attr_value(entry, "links") or []
    for link in links:
        rel = _mapping_or_attr_value(link, "rel")
        href = _mapping_or_attr_value(link, "href")
        mime_type = str(_mapping_or_attr_value(link, "type") or "")
        if rel == "enclosure" and _is_http_url(href) and (not mime_type or mime_type.startswith("image/")):
            return str(href).strip()

    return None


def _mapping_or_attr_value(item: object, field_name: str) -> object:
    if isinstance(item, dict):
        return item.get(field_name)
    return getattr(item, field_name, None)


def _article_sentiment_scores(frame: object) -> list[float]:
    from kag.features.nlp_features import preprocess_text, sentiment_scores

    texts = [
        preprocess_text(f"{title} {summary}")
        for title, summary in zip(frame["title"].fillna(""), frame["summary"].fillna(""), strict=False)
    ]
    return sentiment_scores(texts, backend="lexicon")


def _rss_item_image(item: ET.Element) -> str:
    for enclosure in item.findall("enclosure"):
        url = enclosure.attrib.get("url", "")
        mime_type = enclosure.attrib.get("type", "")
        if _is_http_url(url) and (not mime_type or mime_type.startswith("image/")):
            return url

    for child in item.iter():
        tag = child.tag.lower()
        if tag.endswith("content") or tag.endswith("thumbnail"):
            url = child.attrib.get("url", "")
            if _is_http_url(url):
                return url
    return ""


def _atom_item_image(item: ET.Element) -> str:
    for child in item.iter():
        tag = child.tag.lower()
        if tag.endswith("link") and child.attrib.get("rel") in {"enclosure", "image"}:
            url = child.attrib.get("href", "")
            if _is_http_url(url):
                return url
    return ""


def _is_http_url(value: object) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    return text.startswith("http://") or text.startswith("https://")


def _optional_feedparser():
    try:
        import feedparser
    except ImportError:
        return None
    return feedparser


def _require_pandas():
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError(
            "pandas is not installed. Run: .venv\\Scripts\\python.exe -m pip install -e \".[data]\""
        ) from exc
    return pd
