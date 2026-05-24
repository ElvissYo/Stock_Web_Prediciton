"""NLP feature engineering for ticker-level RSS news."""

from __future__ import annotations

import logging
import math
from pathlib import Path
import re
from typing import Any, Iterable


logger = logging.getLogger(__name__)

DEFAULT_SENTIMENT_MODEL = "mdhugol/indonesia-bert-sentiment-classification"
DEFAULT_EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_EMBEDDING_DIMENSIONS = 50
HASHING_EMBEDDING_SIZE = 384
POSITIVE_TERMS = {
    "akumulasi",
    "bullish",
    "cuan",
    "laba",
    "melaju",
    "menguat",
    "naik",
    "optimis",
    "positif",
    "rebound",
    "rekor",
    "tumbuh",
    "untung",
}
NEGATIVE_TERMS = {
    "anjlok",
    "bearish",
    "koreksi",
    "melemah",
    "merosot",
    "negatif",
    "rugi",
    "tekanan",
    "terkoreksi",
    "turun",
}
TOKEN_PATTERN = re.compile(r"[a-zA-Z]+")


def build_nlp_feature_frame(
    news_frame: Any,
    *,
    embedding_dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS,
    sentiment_backend: str = "auto",
    sentiment_model: str = DEFAULT_SENTIMENT_MODEL,
    embedding_backend: str = "auto",
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    pca_path: str | Path | None = "models/pca.pkl",
) -> Any:
    """Build daily ticker-level NLP features from raw news rows."""

    pd = _require_pandas()
    _validate_news_frame(news_frame)

    if news_frame.empty:
        return _empty_nlp_frame(embedding_dimensions)

    frame = news_frame.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
    frame = frame.dropna(subset=["ticker", "date"])
    frame["text"] = [
        preprocess_text(f"{title} {summary}")
        for title, summary in zip(frame["title"].fillna(""), frame["summary"].fillna(""), strict=False)
    ]
    frame = frame[frame["text"].str.len() > 0].copy()
    if frame.empty:
        return _empty_nlp_frame(embedding_dimensions)

    frame["sentiment_score"] = sentiment_scores(
        frame["text"].tolist(),
        backend=sentiment_backend,
        model_name=sentiment_model,
    )
    embeddings = text_embeddings(
        frame["text"].tolist(),
        backend=embedding_backend,
        model_name=embedding_model,
    )
    reduced_embeddings = reduce_embeddings(
        embeddings,
        output_dimensions=embedding_dimensions,
        pca_path=pca_path,
    )

    for index in range(embedding_dimensions):
        frame[f"embedding_dim_{index}"] = reduced_embeddings[:, index]

    embedding_columns = [f"embedding_dim_{index}" for index in range(embedding_dimensions)]
    aggregations = {
        "sentiment_mean": ("sentiment_score", "mean"),
        "sentiment_std": ("sentiment_score", "std"),
        "news_count": ("sentiment_score", "size"),
    }
    for column in embedding_columns:
        aggregations[column] = (column, "mean")

    features = frame.groupby(["ticker", "date"], as_index=False).agg(**aggregations)
    features["sentiment_std"] = features["sentiment_std"].fillna(0.0)
    features = features.sort_values(["ticker", "date"]).reset_index(drop=True)
    features["sentiment_momentum"] = (
        features.groupby("ticker")["sentiment_mean"].diff().fillna(0.0)
    )

    ordered_columns = [
        "ticker",
        "date",
        "sentiment_mean",
        "sentiment_std",
        "news_count",
        "sentiment_momentum",
        *embedding_columns,
    ]
    return features[ordered_columns]


def build_nlp_features_from_parquet(
    input_path: str | Path,
    output_path: str | Path,
    *,
    embedding_dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS,
    sentiment_backend: str = "auto",
    sentiment_model: str = DEFAULT_SENTIMENT_MODEL,
    embedding_backend: str = "auto",
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    pca_path: str | Path | None = "models/pca.pkl",
) -> int:
    """Read raw news Parquet, build NLP features, and write Parquet."""

    pd = _require_pandas()
    news = pd.read_parquet(input_path)
    features = build_nlp_feature_frame(
        news,
        embedding_dimensions=embedding_dimensions,
        sentiment_backend=sentiment_backend,
        sentiment_model=sentiment_model,
        embedding_backend=embedding_backend,
        embedding_model=embedding_model,
        pca_path=pca_path,
    )

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        features.to_parquet(path, index=False)
    except ImportError as exc:
        raise RuntimeError(
            "Parquet support is not installed. Run: .venv\\Scripts\\python.exe -m pip install -e \".[data]\""
        ) from exc
    return len(features)


def preprocess_text(text: str) -> str:
    """Normalize article text before sentiment and embedding extraction."""

    cleaned = re.sub(r"<[^>]+>", " ", text)
    cleaned = re.sub(r"https?://\S+", " ", cleaned)
    cleaned = " ".join(cleaned.split())
    return cleaned.strip()


def sentiment_scores(
    texts: Iterable[str],
    *,
    backend: str = "auto",
    model_name: str = DEFAULT_SENTIMENT_MODEL,
) -> list[float]:
    """Score article sentiment in the range [-1, 1]."""

    text_list = list(texts)
    if backend not in {"auto", "transformers", "lexicon"}:
        raise ValueError("sentiment backend must be one of: auto, transformers, lexicon")

    if backend in {"auto", "transformers"}:
        try:
            return _transformer_sentiment_scores(text_list, model_name=model_name)
        except Exception as exc:
            if backend == "transformers":
                raise
            logger.warning(
                "Falling back to lexicon sentiment; model=%s reason=%s",
                model_name,
                exc,
            )

    return [_lexicon_sentiment_score(text) for text in text_list]


def text_embeddings(
    texts: Iterable[str],
    *,
    backend: str = "auto",
    model_name: str = DEFAULT_EMBEDDING_MODEL,
) -> Any:
    """Generate article embeddings, with a deterministic hashing fallback."""

    text_list = list(texts)
    if backend not in {"auto", "sentence_transformer", "hashing"}:
        raise ValueError("embedding backend must be one of: auto, sentence_transformer, hashing")

    if backend in {"auto", "sentence_transformer"}:
        try:
            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer(model_name)
            return model.encode(text_list, show_progress_bar=False)
        except Exception as exc:
            if backend == "sentence_transformer":
                raise
            logger.warning(
                "Falling back to hashing embeddings; model=%s reason=%s",
                model_name,
                exc,
            )

    return _hashing_embeddings(text_list)


def reduce_embeddings(
    embeddings: Any,
    *,
    output_dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS,
    pca_path: str | Path | None = "models/pca.pkl",
) -> Any:
    """Reduce embeddings with PCA and pad to a stable output width."""

    np = _require_numpy()
    if output_dimensions < 1:
        raise ValueError("output_dimensions must be at least 1")

    matrix = np.asarray(embeddings, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] == 0:
        return np.zeros((0, output_dimensions), dtype=float)

    if matrix.shape[0] < 2:
        return _padded_embeddings_without_pca(
            matrix,
            output_dimensions=output_dimensions,
            pca_path=pca_path,
            reason="pca_requires_at_least_two_samples",
        )

    n_components = min(output_dimensions, matrix.shape[0], matrix.shape[1])
    if n_components < 1:
        return np.zeros((matrix.shape[0], output_dimensions), dtype=float)

    from sklearn.decomposition import PCA

    pca = PCA(n_components=n_components, random_state=42)
    reduced = pca.fit_transform(matrix)
    padded = np.zeros((matrix.shape[0], output_dimensions), dtype=float)
    padded[:, :n_components] = reduced

    if pca_path is not None:
        joblib = _require_joblib()
        path = Path(pca_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "pca": pca,
                "actual_components": n_components,
                "output_dimensions": output_dimensions,
            },
            path,
        )

    return padded


def _padded_embeddings_without_pca(
    matrix: Any,
    *,
    output_dimensions: int,
    pca_path: str | Path | None,
    reason: str,
) -> Any:
    np = _require_numpy()
    padded = np.zeros((matrix.shape[0], output_dimensions), dtype=float)
    copied_dimensions = min(output_dimensions, matrix.shape[1])
    padded[:, :copied_dimensions] = matrix[:, :copied_dimensions]

    if pca_path is not None:
        joblib = _require_joblib()
        path = Path(pca_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "pca": None,
                "actual_components": 0,
                "output_dimensions": output_dimensions,
                "reason": reason,
            },
            path,
        )
    return padded


def _transformer_sentiment_scores(texts: list[str], *, model_name: str) -> list[float]:
    from transformers import pipeline

    classifier = pipeline("sentiment-analysis", model=model_name, truncation=True)
    raw_results = classifier(texts, batch_size=16)
    return [_sentiment_value(result) for result in raw_results]


def _sentiment_value(result: dict[str, Any]) -> float:
    label = str(result.get("label", "")).lower()
    score = float(result.get("score", 0.0))

    if "neg" in label or label.endswith("_0") or label == "label_0":
        return -score
    if "pos" in label or label.endswith("_2") or label == "label_2":
        return score
    if "neu" in label or label.endswith("_1") or label == "label_1":
        return 0.0
    return 0.0


def _lexicon_sentiment_score(text: str) -> float:
    tokens = [token.lower() for token in TOKEN_PATTERN.findall(text)]
    if not tokens:
        return 0.0

    positive = sum(1 for token in tokens if token in POSITIVE_TERMS)
    negative = sum(1 for token in tokens if token in NEGATIVE_TERMS)
    if positive == 0 and negative == 0:
        return 0.0

    score = (positive - negative) / math.sqrt(len(tokens))
    return max(-1.0, min(1.0, score))


def _hashing_embeddings(texts: list[str]) -> Any:
    from sklearn.feature_extraction.text import HashingVectorizer

    vectorizer = HashingVectorizer(
        n_features=HASHING_EMBEDDING_SIZE,
        alternate_sign=False,
        norm="l2",
    )
    return vectorizer.transform(texts).toarray()


def _empty_nlp_frame(embedding_dimensions: int) -> Any:
    pd = _require_pandas()
    columns = [
        "ticker",
        "date",
        "sentiment_mean",
        "sentiment_std",
        "news_count",
        "sentiment_momentum",
        *[f"embedding_dim_{index}" for index in range(embedding_dimensions)],
    ]
    return pd.DataFrame(columns=columns)


def _validate_news_frame(frame: Any) -> None:
    required_columns = {"ticker", "date", "title", "summary", "url", "source"}
    missing = required_columns - set(frame.columns)
    if missing:
        raise ValueError(f"news data is missing required columns: {', '.join(sorted(missing))}")


def _require_pandas() -> Any:
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError(
            "pandas is not installed. Run: .venv\\Scripts\\python.exe -m pip install -e \".[data]\""
        ) from exc
    return pd


def _require_numpy() -> Any:
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(
            "numpy is not installed. Run: .venv\\Scripts\\python.exe -m pip install -e \".[data]\""
        ) from exc
    return np


def _require_joblib() -> Any:
    try:
        import joblib
    except ImportError as exc:
        raise RuntimeError(
            "joblib is not installed. Run: .venv\\Scripts\\python.exe -m pip install -e \".[ml]\""
        ) from exc
    return joblib
