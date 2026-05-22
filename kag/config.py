"""Application configuration loaded from environment variables."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


DEFAULT_NEO4J_DATABASE = "neo4j"


@dataclass(frozen=True)
class Settings:
    """Runtime settings needed by Phase 0 infrastructure."""

    app_env: str
    log_level: str
    neo4j_uri: str
    neo4j_username: str
    neo4j_password: str
    neo4j_database: str = DEFAULT_NEO4J_DATABASE

    @classmethod
    def from_env(cls, env_file: str | Path | None = ".env") -> "Settings":
        """Load settings from an optional dotenv file and process environment."""

        load_environment(env_file)

        return cls(
            app_env=os.getenv("APP_ENV", "local"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            neo4j_uri=_required_env("NEO4J_URI"),
            neo4j_username=_required_env("NEO4J_USERNAME"),
            neo4j_password=_required_env("NEO4J_PASSWORD"),
            neo4j_database=os.getenv("NEO4J_DATABASE", DEFAULT_NEO4J_DATABASE),
        )

    def redacted(self) -> dict[str, str]:
        """Return settings safe for logs."""

        return {
            "app_env": self.app_env,
            "log_level": self.log_level,
            "neo4j_uri": self.neo4j_uri,
            "neo4j_username": self.neo4j_username,
            "neo4j_password": "***",
            "neo4j_database": self.neo4j_database,
        }


def load_environment(env_file: str | Path | None = ".env") -> None:
    """Load environment variables from dotenv when available.

    A small fallback parser keeps local tests usable before dependencies are installed.
    """

    if env_file is None:
        return

    env_path = Path(env_file)
    if not env_path.exists():
        return

    try:
        from dotenv import load_dotenv
    except ImportError:
        _load_dotenv_fallback(env_path)
        return

    load_dotenv(env_path)


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if value:
        return value

    raise ValueError(f"Missing required environment variable: {name}")


def _load_dotenv_fallback(env_path: Path) -> None:
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

