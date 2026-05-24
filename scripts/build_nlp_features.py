"""Build ticker-date NLP features from raw RSS news."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys

from kag.features.nlp_features import (
    DEFAULT_EMBEDDING_DIMENSIONS,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_SENTIMENT_MODEL,
    build_nlp_features_from_parquet,
)
from kag.logging import configure_logging


DEFAULT_INPUT_PATH = Path("data/news_raw.parquet")
DEFAULT_OUTPUT_PATH = Path("data/nlp_features.parquet")
DEFAULT_PCA_PATH = Path("models/pca.pkl")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--pca-output", type=Path, default=DEFAULT_PCA_PATH)
    parser.add_argument("--embedding-dimensions", type=int, default=DEFAULT_EMBEDDING_DIMENSIONS)
    parser.add_argument("--sentiment-backend", choices=["auto", "transformers", "lexicon"], default="auto")
    parser.add_argument("--sentiment-model", default=DEFAULT_SENTIMENT_MODEL)
    parser.add_argument(
        "--embedding-backend",
        choices=["auto", "sentence_transformer", "hashing"],
        default="auto",
    )
    parser.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_logging()

    try:
        rows = build_nlp_features_from_parquet(
            args.input,
            args.output,
            embedding_dimensions=args.embedding_dimensions,
            sentiment_backend=args.sentiment_backend,
            sentiment_model=args.sentiment_model,
            embedding_backend=args.embedding_backend,
            embedding_model=args.embedding_model,
            pca_path=args.pca_output,
        )
    except Exception:
        logger.exception("NLP feature build failed")
        return 1

    logger.info("NLP feature build succeeded; output=%s rows=%s", args.output, rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
