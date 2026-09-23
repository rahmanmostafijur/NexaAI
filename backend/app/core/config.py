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


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "NexaAI Agent"
    app_version: str = "1.0.0"
    environment: Literal["development", "production", "test"] = "development"
    log_level: str = "INFO"

    # Database
    database_url: str = "postgresql+asyncpg://nexa:nexa_dev_password@localhost:5434/nexa"
    sql_readonly_user: str = "nexa_readonly"
    sql_readonly_password: SecretStr = SecretStr("nexa_readonly_dev_password")
    business_schema: str = "commerce"

    # Auth
    jwt_secret: SecretStr = SecretStr(INSECURE_JWT_DEFAULT)
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = Field(default=720, ge=5, le=60 * 24 * 7)
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
        if self.environment == "production":
            secret = self.jwt_secret.get_secret_value()
            if secret == INSECURE_JWT_DEFAULT or len(secret) < 32:
                raise ValueError("JWT_SECRET must be set to a random value of 32+ characters")
            if self.admin_password.get_secret_value() == "ChangeMe123!":
                raise ValueError("ADMIN_PASSWORD must be changed in production")
        return self

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
