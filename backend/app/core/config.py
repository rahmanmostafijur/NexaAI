"""Application configuration loaded from environment variables (and `.env`)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy.engine import make_url

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent

INSECURE_JWT_DEFAULT = "insecure-development-secret-change-me-please-0000"
INSECURE_READONLY_DEFAULTS = {"nexa_readonly_dev_password", "change-me-readonly-password"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "NexaAI Agent"
    # The organisation the assistant works for (used in every prompt).
    company_name: str = Field(default="Nexa Commerce Ltd", min_length=1, max_length=120)
    currency_code: str = Field(default="BDT", min_length=1, max_length=10)
    currency_symbol: str = Field(default="৳", min_length=1, max_length=5)
    app_version: str = "1.0.0"
    environment: Literal["development", "production", "test"] = "development"
    log_level: str = "INFO"

    # Database
    database_url: str = "postgresql+asyncpg://nexa:nexa_dev_password@localhost:5440/nexa"
    sql_readonly_user: str = "nexa_readonly"
    sql_readonly_password: SecretStr = SecretStr("nexa_readonly_dev_password")
    business_schema: str = "commerce"

    # Auth
    jwt_secret: SecretStr = SecretStr(INSECURE_JWT_DEFAULT)
    jwt_algorithm: str = "HS256"
    # Short-lived access token (kept in memory by the browser) + rotating refresh cookie.
    access_token_expire_minutes: int = Field(default=15, ge=1, le=240)
    refresh_token_expire_days: int = Field(default=14, ge=1, le=90)
    session_max_days: int = Field(default=30, ge=1, le=365)
    # A just-rotated refresh token presented again within this window (two tabs racing)
    # gets a retryable 409 instead of being treated as theft.
    refresh_reuse_grace_seconds: int = Field(default=10, ge=0, le=120)
    # None = automatic: Secure cookies in production, plain cookies elsewhere.
    cookie_secure: bool | None = None
    admin_email: str = "admin@nexa.local"
    admin_password: SecretStr = SecretStr("ChangeMe123!")
    allow_registration: bool = True
    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:5173",
        "http://localhost:3000",
    ]

    # LLM
    llm_provider: Literal["openai_compatible", "none"] = "openai_compatible"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    llm_timeout_seconds: float = Field(default=60.0, gt=0)
    llm_max_tokens: int = Field(default=1200, ge=64)
    llm_json_mode: bool = True
    # For reasoning models (e.g. gpt-oss): "low" | "medium" | "high"; empty = not sent.
    llm_reasoning_effort: Literal["", "low", "medium", "high"] = ""

    # Embeddings
    embedding_provider: Literal["fastembed", "openai_compatible"] = "fastembed"
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_dimension: int = Field(default=384, ge=8, le=4096)
    embedding_base_url: str = ""
    embedding_api_key: SecretStr = SecretStr("")
    fastembed_cache_dir: str | None = None

    # Text-to-SQL
    sql_statement_timeout_ms: int = Field(default=5000, ge=100, le=60000)
    sql_max_rows: int = Field(default=200, ge=1, le=5000)
    sql_max_correction_attempts: int = Field(default=2, ge=0, le=5)

    # RAG
    rag_top_k: int = Field(default=5, ge=1, le=20)
    rag_min_similarity: float = Field(default=0.30, ge=0.0, le=1.0)
    rag_chunk_size: int = Field(default=900, ge=200, le=4000)
    rag_chunk_overlap: int = Field(default=150, ge=0, le=1000)
    rag_reranker: Literal["none", "llm"] = "none"
    upload_dir: Path = BACKEND_DIR / "storage" / "uploads"
    max_upload_mb: int = Field(default=10, ge=1, le=100)

    # Agent
    router_clarify_threshold: float = Field(default=0.40, ge=0.0, le=1.0)
    context_max_messages: int = Field(default=8, ge=0, le=40)
    context_max_chars: int = Field(default=6000, ge=500)

    # Rate limits (requests per minute)
    rate_limit_chat_per_minute: int = Field(default=20, ge=1)
    rate_limit_auth_per_minute: int = Field(default=10, ge=1)
    rate_limit_upload_per_minute: int = Field(default=10, ge=1)

    # Redis (optional): job queue for document indexing and shared rate limits.
    redis_url: str = ""
    ingestion_backend: Literal["inprocess", "arq"] = "inprocess"
    ingestion_max_attempts: int = Field(default=3, ge=1, le=10)
    ingestion_retry_base_seconds: float = Field(default=5.0, ge=0.0, le=600.0)
    # A pending/processing document untouched for this long is considered orphaned.
    ingestion_stuck_timeout_seconds: int = Field(default=600, ge=30)
    ingestion_sweep_interval_seconds: int = Field(default=60, ge=5)
    rate_limit_backend: Literal["memory", "redis"] = "memory"

    # Prometheus endpoint at /metrics (not under /api, so the bundled nginx never exposes it).
    metrics_enabled: bool = True
    # Set to require `Authorization: Bearer <token>`. Empty: only direct local/private callers.
    metrics_token: SecretStr = SecretStr("")

    seed_on_startup: bool = False

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip().startswith("["):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def _validate_production(self) -> Settings:
        if self.rag_chunk_overlap >= self.rag_chunk_size:
            raise ValueError("RAG_CHUNK_OVERLAP must be smaller than RAG_CHUNK_SIZE")
        if not self.redis_url and self.ingestion_backend == "arq":
            raise ValueError("INGESTION_BACKEND=arq requires REDIS_URL")
        if not self.redis_url and self.rate_limit_backend == "redis":
            raise ValueError("RATE_LIMIT_BACKEND=redis requires REDIS_URL")
        if self.environment == "production":
            secret = self.jwt_secret.get_secret_value()
            if secret == INSECURE_JWT_DEFAULT or len(secret) < 32:
                raise ValueError("JWT_SECRET must be set to a random value of 32+ characters")
            if self.admin_password.get_secret_value() == "ChangeMe123!":
                raise ValueError("ADMIN_PASSWORD must be changed in production")
            readonly = self.sql_readonly_password.get_secret_value()
            if readonly in INSECURE_READONLY_DEFAULTS or len(readonly) < 16:
                raise ValueError(
                    "SQL_READONLY_PASSWORD must be set to a random value of 16+ characters"
                )
        return self

    @property
    def secure_cookies(self) -> bool:
        if self.cookie_secure is not None:
            return self.cookie_secure
        return self.environment == "production"

    @property
    def readonly_database_url(self) -> str:
        """Same host/database as the app, but authenticated as the read-only SQL role."""
        url = make_url(self.database_url).set(
            username=self.sql_readonly_user,
            password=self.sql_readonly_password.get_secret_value(),
        )
        return url.render_as_string(hide_password=False)

    @property
    def llm_configured(self) -> bool:
        if self.llm_provider == "none" or not self.llm_model:
            return False
        is_local = "localhost" in self.llm_base_url or "ollama" in self.llm_base_url
        return is_local or bool(self.llm_api_key.get_secret_value())

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
