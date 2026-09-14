"""Application configuration loaded from environment variables.

Values come from a `.env` file in the backend directory (see the
`.env.example` template) or from the process environment.

Data paths default to absolute paths under the backend directory so the
server works regardless of where it is launched from.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> backend/
BACKEND_DIR = Path(__file__).resolve().parents[2]
_DEFAULT_DB_PATH = BACKEND_DIR / "data" / "meddoc.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
    )

    # Application metadata
    app_name: str = "MedDoc AI"
    app_version: str = "0.1.0"
    log_level: str = "INFO"

    # OpenAI
    openai_api_key: str = ""
    openai_chat_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"

    # Storage paths (default to absolute paths inside the backend dir)
    upload_dir: Path = BACKEND_DIR / "data" / "uploads"
    chroma_dir: Path = BACKEND_DIR / "data" / "chroma"
    database_url: str = f"sqlite:///{_DEFAULT_DB_PATH.as_posix()}"

    # RAG pipeline tuning (evaluation targets, not absolutes)
    chunk_size: int = 800
    chunk_overlap: int = 120
    top_k: int = 4
    similarity_threshold: float = 0.30

    # Upload limits
    max_upload_size_mb: int = 10

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (fast + stable across requests)."""
    return Settings()