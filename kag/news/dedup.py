"""Deduplication helpers for ticker-level news rows."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
import re
from typing import Any, Iterable, TypeVar
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


T = TypeVar("T")

TRACKING_QUERY_PARAMS = {
    "fbclid",
    "gclid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
    "utm_campaign",
    "utm_content",
    "utm_medium",
    "utm_source",
    "utm_term",
}
TITLE_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
TITLE_STOPWORDS = {
    "a",
    "an",
    "and",
    "atau",
    "dan",
    "dari",
    "di",
    "for",
    "ini",
    "itu",
    "ke",
    "of",
    "on",
    "pada",
    "saat",
    "the",
    "untuk",
    "yang",
}


def deduplicate_news_items(
    items: Iterable[T],
    *,
    title_similarity_threshold: float = 0.9,
) -> list[T]:
    """Keep one unique article insight per ticker.

    The same article can appear through RSS, GDELT, and NewsAPI with slightly
    different metadata. URL duplicates are removed across dates, while title
    duplicates are removed inside each ticker-date bucket.
    """

    unique_items: list[T] = []
    seen_urls: set[tuple[str, str]] = set()
    title_buckets: dict[tuple[str, str], list[tuple[set[str], str]]] = defaultdict(list)

    for item in items:
        ticker = normalize_ticker(_item_value(item, "ticker"))
        if not ticker:
            continue

        date_text = normalize_date_text(_item_value(item, "date"))
        url_key = canonical_article_url(_item_value(item, "url"))
        title = _clean_text(_item_value(item, "title"))
        title_tokens = article_title_tokens(title)
        title_fingerprint = " ".join(sorted(title_tokens))

        if url_key and (ticker, url_key) in seen_urls:
            continue

        bucket_key = (ticker, date_text)
        if _has_duplicate_title(
            title_tokens,
            title_fingerprint,
            title_buckets[bucket_key],
            threshold=title_similarity_threshold,
        ):
            continue

        unique_items.append(item)
        if url_key:
            seen_urls.add((ticker, url_key))
        if title_tokens:
            title_buckets[bucket_key].append((title_tokens, title_fingerprint))

    return unique_items


def canonical_article_url(value: Any) -> str:
    """Canonicalize article URLs so provider tracking params do not create duplicates."""

    text = _clean_text(value)
    if not text:
        return ""

    try:
        parsed = urlsplit(text)
    except ValueError:
        return text.lower().rstrip("/")

    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = re.sub(r"/+", "/", parsed.path).rstrip("/")
    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in TRACKING_QUERY_PARAMS and not key.lower().startswith("utm_")
    ]
    query = urlencode(sorted(query_pairs))
    return urlunsplit((scheme, netloc, path, query, ""))


def article_title_tokens(title: Any) -> set[str]:
    """Return stable title tokens used for duplicate insight detection."""

    text = _clean_text(title).lower()
    tokens = {
        token
        for token in TITLE_TOKEN_PATTERN.findall(text)
        if len(token) > 1 and token not in TITLE_STOPWORDS
    }
    return tokens


def infer_provider_from_source(source: Any) -> str:
    """Infer provider for old news files that do not have a provider column."""

    text = _clean_text(source).lower()
    if text.startswith("gdelt"):
        return "gdelt"
    if text.startswith("newsapi"):
        return "newsapi"
    if text.startswith("mediastack"):
        return "mediastack"
    return "rss"


def normalize_ticker(value: Any) -> str:
    return _clean_text(value).upper().removesuffix(".JK")


def normalize_date_text(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = _clean_text(value)
    if len(text) >= 10:
        return text[:10]
    return text


def _has_duplicate_title(
    title_tokens: set[str],
    title_fingerprint: str,
    existing_titles: list[tuple[set[str], str]],
    *,
    threshold: float,
) -> bool:
    if not title_tokens:
        return False

    for existing_tokens, existing_fingerprint in existing_titles:
        if title_fingerprint == existing_fingerprint:
            return True

        intersection = len(title_tokens & existing_tokens)
        union = len(title_tokens | existing_tokens)
        smaller = min(len(title_tokens), len(existing_tokens))
        if not union or smaller < 4:
            continue

        jaccard = intersection / union
        containment = intersection / smaller
        if jaccard >= threshold or (containment >= threshold and jaccard >= 0.75):
            return True

    return False


def _item_value(item: Any, field_name: str) -> Any:
    if isinstance(item, dict):
        return item.get(field_name)
    return getattr(item, field_name, None)


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if value != value:
            return ""
    except TypeError:
        pass
    return " ".join(str(value).split()).strip()
