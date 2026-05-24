"""Compare baseline and NLP global model metrics."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys

from kag.logging import configure_logging
from kag.modeling.global_model import (
    build_model_comparison,
    load_result_json,
    write_json,
    write_model_comparison_markdown,
)


DEFAULT_BASELINE_METRICS_PATH = Path("reports/baseline_metrics.json")
DEFAULT_NLP_METRICS_PATH = Path("reports/nlp_metrics.json")
DEFAULT_OUTPUT_PATH = Path("reports/metrics.json")
DEFAULT_MARKDOWN_PATH = Path("reports/model_comparison.md")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-metrics", type=Path, default=DEFAULT_BASELINE_METRICS_PATH)
    parser.add_argument("--nlp-metrics", type=Path, default=DEFAULT_NLP_METRICS_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN_PATH)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_logging()

    try:
        baseline_result = load_result_json(args.baseline_metrics)
        nlp_result = load_result_json(args.nlp_metrics)
        comparison = build_model_comparison(baseline_result, nlp_result)
        write_json(comparison, args.output)
        write_model_comparison_markdown(comparison, args.markdown_output)
    except Exception:
        logger.exception("Model evaluation failed")
        return 1

    logger.info("Model evaluation succeeded; output=%s markdown=%s", args.output, args.markdown_output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
