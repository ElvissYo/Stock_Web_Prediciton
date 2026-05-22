"""Validate Neo4j connectivity using local environment settings."""

from __future__ import annotations

import logging
import sys

from kag.config import Settings
from kag.graph.client import Neo4jClient
from kag.logging import configure_logging


logger = logging.getLogger(__name__)


def main() -> int:
    settings = Settings.from_env()
    configure_logging(settings.log_level)

    logger.info("Checking Neo4j connection with settings=%s", settings.redacted())

    try:
        with Neo4jClient(settings) as client:
            client.verify_connectivity()
    except Exception:
        logger.exception("Neo4j connection check failed")
        return 1

    logger.info("Neo4j connection check succeeded")
    return 0


if __name__ == "__main__":
    sys.exit(main())

