"""Neo4j schema definitions for the initial knowledge graph."""

from __future__ import annotations

from kag.graph.client import Neo4jClient


SCHEMA_STATEMENTS: tuple[str, ...] = (
    "CREATE CONSTRAINT stock_ticker_unique IF NOT EXISTS "
    "FOR (s:Stock) REQUIRE s.ticker IS UNIQUE",
    "CREATE CONSTRAINT sector_name_unique IF NOT EXISTS "
    "FOR (s:Sector) REQUIRE s.name IS UNIQUE",
    "CREATE CONSTRAINT news_article_url_unique IF NOT EXISTS "
    "FOR (n:NewsArticle) REQUIRE n.url IS UNIQUE",
    "CREATE CONSTRAINT macro_indicator_code_unique IF NOT EXISTS "
    "FOR (m:MacroIndicator) REQUIRE m.code IS UNIQUE",
    "CREATE CONSTRAINT price_point_key_unique IF NOT EXISTS "
    "FOR (p:PricePoint) REQUIRE (p.ticker, p.date, p.source, p.interval) IS UNIQUE",
    "CREATE INDEX price_ticker_date IF NOT EXISTS "
    "FOR (p:PricePoint) ON (p.ticker, p.date)",
    "CREATE INDEX news_published_at IF NOT EXISTS "
    "FOR (n:NewsArticle) ON (n.published_at)",
)


def apply_schema(client: Neo4jClient) -> int:
    """Apply graph constraints/indexes and return the number of statements executed."""

    for statement in SCHEMA_STATEMENTS:
        client.execute_write(statement)

    return len(SCHEMA_STATEMENTS)
