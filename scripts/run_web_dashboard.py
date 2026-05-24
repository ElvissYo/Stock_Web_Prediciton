"""Run the custom non-Streamlit IHSG dashboard."""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.environ.get("DASHBOARD_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", os.environ.get("DASHBOARD_PORT", "8000"))),
    )
    parser.add_argument("--static-dir", type=Path, default=Path("web"))
    return parser.parse_args()


def main() -> int:
    from kag.logging import configure_logging
    from kag.web.api import create_server

    args = parse_args()
    configure_logging()

    if not args.static_dir.exists():
        logger.error("Static web directory does not exist: %s", args.static_dir)
        return 1

    server = create_server(host=args.host, port=args.port, static_dir=args.static_dir)
    logger.info("Custom dashboard running at http://%s:%s", args.host, args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down dashboard server")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
