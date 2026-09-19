"""Application configuration loaded from environment variables.

Values come from a `.env` file in the backend directory (see the
`.env.example` template) or from the process environment.

Groq is the only AI provider: it powers document summaries, RAG chat, and
structured extraction. Groq offers no embedding API, so retrieval uses
deterministic local lexical embeddings (no external calls, fully private).

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

    # Groq AI (the only AI provider)
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    groq_timeout_seconds: int = 30
    ai_provider: str = "groq"

    # Embeddings: local deterministic lexical vectors (Groq has no
    # embedding API, so no external embedding provider is used).
    embedding_dimensions: int = 1536

    # Storage paths (default to absolute paths inside the backend dir)
    upload_dir: Path = BACKEND_DIR / "data" / "uploads"
    chroma_dir: Path = BACKEND_DIR / "data" / "chroma"
    database_url: str = f"sqlite:///{_DEFAULT_DB_PATH.as_posix()}"

    # RAG pipeline tuning (evaluation targets, not absolutes)
    chunk_size: int = 800
    chunk_overlap: int = 120
    top_k: int = 4
    # Cosine-distance gate for the local lexical embeddings. Lexical
    # vectors are sparse and land at larger cosine distances than dense
    # vectors, so the relevance gate is loose. In chat, only the single
    # best passage is used for grounding.
    similarity_threshold: float = 0.90

    # Upload limits
    max_upload_size_mb: int = 10

    # Comma-separated list of origins allowed to call the API from a browser
    # (dev CORS). Add http://<your-lan-ip>:5173 when testing from a phone or
    # another device on the same network.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (fast + stable across requests)."""
    return Settings()