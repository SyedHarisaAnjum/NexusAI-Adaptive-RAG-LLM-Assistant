import secrets
import warnings
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file.

    Secrets (GEMINI_API_KEY, JWT_SECRET) must only ever come from the
    environment - never commit them. See .env.example for every option.
    """

    environment: Literal["development", "production"] = "development"

    gemini_api_key: str
    gemini_model: str = "gemini-3.5-flash"
    app_name: str = "AI Q&A Assistant"

    # Authentication
    jwt_secret: str = ""  # required in production (32+ chars)
    jwt_expire_minutes: int = 60 * 24
    allow_registration: bool = True
    # Optional demo account created at startup so visitors can try the app.
    demo_user_email: str | None = None
    demo_user_password: str | None = None

    # Comma-separated list of frontend origins allowed to call the API.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Document upload settings
    data_dir: Path = Path("data")
    max_upload_mb: int = 10
    max_pdf_pages: int = 500
    max_documents_per_user: int = 20

    # Rate limits (per user for chat/upload, per IP for login/register)
    rate_limit_chat_per_minute: int = 10
    rate_limit_upload_per_hour: int = 10
    rate_limit_auth_per_minute: int = 10

    # Timeouts
    gemini_timeout_seconds: int = 60  # per Gemini HTTP call
    request_timeout_seconds: int = 120  # whole chat turn (classify + retrieve + answer)

    # Logging
    log_level: str = "INFO"
    log_json: bool = True

    # Backups (BACKUP_INTERVAL_HOURS=0 disables the built-in scheduler)
    backup_dir: Path = Path("backups")
    backup_keep: int = 7
    backup_interval_hours: int = 24

    # RAG settings. Documents and queries MUST use the same embedding model
    # and dimension; changing either requires re-indexing all documents.
    embedding_model: str = "gemini-embedding-001"
    embedding_dim: int = 768
    chunk_size: int = 1000
    chunk_overlap: int = 200
    rag_top_k: int = 5
    # Minimum cosine similarity (0-1) for a chunk to count as relevant.
    # Raise it for stricter answers, lower it if good passages are being missed.
    rag_min_score: float = 0.6

    # Conversation history: how many previous messages are sent to Gemini.
    history_max_messages: int = 10

    # Agentic routing (Auto mode). The LLM classifier costs one extra Gemini
    # call per ambiguous question; set ROUTER_USE_LLM=false to use rules only.
    # ROUTER_MODEL lets routing use a cheaper model (free-tier quota is per model).
    router_use_llm: bool = True
    router_model: str | None = None

    # extra="ignore": unrelated entries in .env (e.g. frontend VITE_* vars) must not crash startup.
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @model_validator(mode="after")
    def _check_secrets(self) -> "Settings":
        if len(self.jwt_secret) < 32:
            if self.environment == "production":
                raise ValueError("JWT_SECRET must be set to at least 32 characters in production.")
            # Development only: a random secret means logins reset on every restart.
            warnings.warn("JWT_SECRET not set - using a temporary random secret (dev only).")
            self.jwt_secret = secrets.token_urlsafe(48)
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def chroma_dir(self) -> Path:
        return self.data_dir / "chroma"

    @property
    def sessions_dir(self) -> Path:
        return self.data_dir / "sessions"

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def extracted_dir(self) -> Path:
        return self.data_dir / "extracted"

    @property
    def metadata_file(self) -> Path:
        return self.data_dir / "documents.json"

    @property
    def users_file(self) -> Path:
        return self.data_dir / "users.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()
