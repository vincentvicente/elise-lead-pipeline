"""Application configuration loaded from environment variables.

All API keys, database URLs, and runtime knobs are centralized here.
Use `get_settings()` everywhere — it caches one Settings instance per process.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized configuration. Reads from .env and environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------------
    database_url: str = Field(
        default="sqlite+aiosqlite:///./elise.db",
        description="Async SQLAlchemy connection URL.",
    )

    # ------------------------------------------------------------------------
    # Enrichment APIs
    # ------------------------------------------------------------------------
    census_api_key: str = ""
    news_api_key: str = ""
    walkscore_api_key: str = ""
    fred_api_key: str = ""

    # ------------------------------------------------------------------------
    # LLM
    # ------------------------------------------------------------------------
    anthropic_api_key: str = ""
    llm_primary_model: str = "claude-sonnet-4-6"
    llm_fallback_model: str = "claude-haiku-4-5"
    llm_max_tokens: int = 500
    llm_throttle_seconds: float = 1.3  # min interval between Claude calls (RPM control)

    # ------------------------------------------------------------------------
    # Alerting (Resend)
    # ------------------------------------------------------------------------
    resend_api_key: str = ""
    alert_email: str = ""
    alert_from_address: str = "EliseAI Pipeline <onboarding@resend.dev>"

    # ------------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------------
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    environment: Literal["development", "staging", "production"] = "development"
    frontend_url: str = "http://localhost:5173"

    # ------------------------------------------------------------------------
    # Scoring (defaults; override in scoring/rubric.py if needed)
    # ------------------------------------------------------------------------
    tier_threshold_hot: int = 75
    tier_threshold_warm: int = 55

    # ------------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------------
    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached singleton Settings instance.

    Cached so repeated calls don't re-read the .env file.
    Tests can override by calling `get_settings.cache_clear()`.
    """
    return Settings()
