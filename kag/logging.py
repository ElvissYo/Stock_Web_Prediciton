"""Logging utilities for scripts and pipelines."""

from __future__ import annotations

import logging


def configure_logging(level: str = "INFO") -> None:
    """Configure a consistent console logger for CLI scripts."""

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    logging.getLogger("neo4j.notifications").setLevel(logging.WARNING)
