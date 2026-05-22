"""Thin Neo4j client wrapper used by scripts and future graph pipelines."""

from __future__ import annotations

from contextlib import AbstractContextManager
from types import TracebackType
from typing import Any

from kag.config import Settings


class Neo4jClient(AbstractContextManager["Neo4jClient"]):
    """Owns Neo4j driver lifecycle and small operational queries."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._driver = None

    def __enter__(self) -> "Neo4jClient":
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def connect(self) -> None:
        if self._driver is not None:
            return

        try:
            from neo4j import GraphDatabase
        except ImportError as exc:
            raise RuntimeError(
                "Neo4j driver is not installed. Run: python -m pip install -e ."
            ) from exc

        self._driver = GraphDatabase.driver(
            self.settings.neo4j_uri,
            auth=(self.settings.neo4j_username, self.settings.neo4j_password),
        )

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    def verify_connectivity(self) -> None:
        self.connect()
        self._driver.verify_connectivity()

    def execute_write(self, query: str, parameters: dict[str, Any] | None = None) -> list[dict]:
        self.connect()

        with self._driver.session(database=self.settings.neo4j_database) as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]

    def execute_read(self, query: str, parameters: dict[str, Any] | None = None) -> list[dict]:
        self.connect()

        with self._driver.session(database=self.settings.neo4j_database) as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]

