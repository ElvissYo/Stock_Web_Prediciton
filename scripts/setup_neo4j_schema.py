"""Create Neo4j constraints and indexes for Phase 0."""

from __future__ import annotations

import logging
import sys

from kag.config import Settings
from kag.graph.client import Neo4jClient
from kag.graph.schema import apply_schema
from kag.logging import configure_logging


logger = logging.getLogger(__name__)


def main() -> int:
    settings = Settings.from_env()
    configure_logging(settings.log_level)

    logger.info("Applying Neo4j schema with settings=%s", settings.redacted())

    try:
        with Neo4jClient(settings) as client:
            total = apply_schema(client)
    except Exception:
        logger.exception("Neo4j schema setup failed")
        return 1

    logger.info("Neo4j schema setup succeeded; statements_executed=%s", total)
    return 0


if __name__ == "__main__":
    sys.exit(main())

