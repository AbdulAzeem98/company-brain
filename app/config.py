
"""Configuration management for Company Brain using Pydantic Settings."""

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings and environment configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application metadata
    APP_NAME: str = "Company Brain — Nexora Technologies"
    APP_VERSION: str = "1.0.0"
    APP_ENV: str = "development"

    # Base workspace paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    DATA_DIR: Path = Path(__file__).resolve().parent.parent / "data"
    KNOWLEDGE_DIR: Path = (
        Path(__file__).resolve().parent.parent
        / "data"
        / "synthetic_company"
    )
    DATABASE_PATH: Path = (
        Path(__file__).resolve().parent.parent
        / "data"
        / "company_brain.db"
    )

    # API configuration
    API_HOST: str = "127.0.0.1"
    API_PORT: int = 8000

    # Browser CORS configuration
    # Set CORS_ORIGINS in .env for additional trusted browser origins.
    CORS_ORIGINS: list[str] = ["http://localhost:8501"]

    # LLM configuration
    # Options: "auto", "gemini", "retrieval_only"
    LLM_PROVIDER: str = "auto"
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.5-flash"

    # Retrieval parameters
    DEFAULT_ROLE: str = "employee"
    DEFAULT_SEARCH_LIMIT: int = 5
    MAX_RETRIEVAL_CHUNKS: int = 5
    CHUNK_SIZE_WORDS: int = 350
    CHUNK_OVERLAP_WORDS: int = 50

    # Security and development settings
    DEV_IDENTITY_MODE: bool = True

    # MCP uses a server-controlled role, never a caller-supplied role.
    # Keep this as employee unless a trusted deployment explicitly
    # configures a different role for its dedicated MCP server.
    MCP_DEFAULT_ROLE: str = "employee"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached application settings."""
    return Settings()
