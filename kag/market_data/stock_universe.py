"""Stock universe fetchers for IDX metadata."""

from __future__ import annotations

from dataclasses import dataclass
import csv
from html.parser import HTMLParser
from pathlib import Path
import re
from typing import Iterable
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from kag.ingestion.stocks import normalize_ticker


STOCKANALYSIS_IDX_URL = "https://stockanalysis.com/list/indonesia-stock-exchange/"
DEFAULT_SECTOR = "UNKNOWN"
USER_AGENT = (
    "Mozilla/5.0 (compatible; KAGStockUniverseFetcher/0.1; "
    "+https://github.com/ElvissYo/Stock_Web_Prediciton)"
)
TICKER_PATTERN = re.compile(r"^[A-Z0-9]{1,12}$")


@dataclass(frozen=True)
class StockUniverseRecord:
    """Canonical stock metadata exported to the graph ingestion CSV format."""

    ticker: str
    name: str
    universe_rank: int | None = None
    sector: str = DEFAULT_SECTOR
    exchange: str = "IDX"
    yfinance_symbol: str | None = None

    def to_csv_row(self) -> dict[str, str]:
        ticker = normalize_ticker(self.ticker)
        yfinance_symbol = self.yfinance_symbol or f"{ticker}.JK"
        return {
            "ticker": ticker,
            "name": self.name.strip(),
            "sector": self.sector.strip() or DEFAULT_SECTOR,
            "exchange": self.exchange.strip() or "IDX",
            "yfinance_symbol": yfinance_symbol.upper(),
            "universe_rank": "" if self.universe_rank is None else str(self.universe_rank),
        }


class StockAnalysisIDXParser(HTMLParser):
    """Parse the StockAnalysis IDX stock table without pulling in browser tooling."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.records: list[StockUniverseRecord] = []
        self.next_href: str | None = None
        self._in_main_table = False
        self._table_depth = 0
        self._in_row = False
        self._in_cell = False
        self._current_cells: list[str] = []
        self._current_cell_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key.lower(): value or "" for key, value in attrs}

        if tag == "link" and _contains_token(attrs_dict.get("rel", ""), "next"):
            self.next_href = attrs_dict.get("href") or self.next_href

        if tag == "table":
            if attrs_dict.get("id") == "main-table":
                self._in_main_table = True
                self._table_depth = 1
            elif self._in_main_table:
                self._table_depth += 1
            return

        if not self._in_main_table:
            return

        if tag == "tr":
            self._in_row = True
            self._current_cells = []
        elif tag == "td" and self._in_row:
            self._in_cell = True
            self._current_cell_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "table" and self._in_main_table:
            self._table_depth -= 1
            if self._table_depth <= 0:
                self._in_main_table = False
            return

        if not self._in_main_table:
            return

        if tag == "td" and self._in_cell:
            self._current_cells.append(_clean_text("".join(self._current_cell_parts)))
            self._current_cell_parts = []
            self._in_cell = False
        elif tag == "tr" and self._in_row:
            record = _record_from_cells(self._current_cells)
            if record is not None:
                self.records.append(record)
            self._current_cells = []
            self._in_row = False

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._current_cell_parts.append(data)


def fetch_stockanalysis_idx_universe(
    *,
    url: str = STOCKANALYSIS_IDX_URL,
    max_pages: int = 20,
    timeout: float = 30,
) -> list[StockUniverseRecord]:
    """Fetch IDX stock metadata from StockAnalysis and preserve source ordering."""

    if max_pages < 1:
        raise ValueError("max_pages must be at least 1")

    next_url: str | None = url
    seen_tickers: set[str] = set()
    records: list[StockUniverseRecord] = []
    pages_read = 0

    while next_url and pages_read < max_pages:
        html = fetch_html(next_url, timeout=timeout)
        page_records, discovered_next_url = parse_stockanalysis_idx_html(html, base_url=next_url)
        for record in page_records:
            ticker = normalize_ticker(record.ticker)
            if ticker in seen_tickers:
                continue
            seen_tickers.add(ticker)
            records.append(record)

        pages_read += 1
        next_url = discovered_next_url

    if not records:
        raise ValueError("No IDX stock records were found in the StockAnalysis response")

    return records


def fetch_html(url: str, *, timeout: float = 30) -> str:
    """Fetch an HTML page with a stable User-Agent for non-browser ingestion."""

    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def parse_stockanalysis_idx_html(
    html: str,
    *,
    base_url: str = STOCKANALYSIS_IDX_URL,
) -> tuple[list[StockUniverseRecord], str | None]:
    """Parse one StockAnalysis IDX list page into stock metadata records."""

    parser = StockAnalysisIDXParser()
    parser.feed(html)
    parser.close()
    next_url = urljoin(base_url, parser.next_href) if parser.next_href else None
    return parser.records, next_url


def write_stock_universe_csv(records: Iterable[StockUniverseRecord], csv_path: str | Path) -> int:
    """Write stock universe records to the CSV format accepted by graph ingestion."""

    path = Path(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [record.to_csv_row() for record in records]

    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "ticker",
                "name",
                "sector",
                "exchange",
                "yfinance_symbol",
                "universe_rank",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    return len(rows)


def _record_from_cells(cells: list[str]) -> StockUniverseRecord | None:
    if len(cells) < 3:
        return None

    universe_rank = _int_or_none(cells[0])
    ticker = normalize_ticker(cells[1])
    name = cells[2].strip()
    if not ticker or not name or not TICKER_PATTERN.fullmatch(ticker):
        return None

    return StockUniverseRecord(
        ticker=ticker,
        name=name,
        universe_rank=universe_rank,
        sector=DEFAULT_SECTOR,
        exchange="IDX",
        yfinance_symbol=f"{ticker}.JK",
    )


def _clean_text(value: str) -> str:
    return " ".join(value.split()).strip()


def _contains_token(value: str, token: str) -> bool:
    return token.lower() in {part.strip().lower() for part in value.split()}


def _int_or_none(value: str) -> int | None:
    stripped = value.strip()
    if not stripped:
        return None

    return int(stripped)
