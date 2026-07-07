"""Application settings — 12-factor, env-driven, safe defaults for local dev.

Every deployment knob lives here and is documented in .env.example.
AI keys, SMTP, and webhooks are optional: absence degrades features,
never crashes boot.
"""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="JOBPILOT_", env_file=".env", env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "local"                                     # local | docker | prod
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = ["http://localhost:5173"]

    database_url: str = "postgresql+psycopg://jobpilot:jobpilot@localhost:5432/jobpilot"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "dev-only-change-me"                 # override in prod
    jwt_access_ttl_seconds: int = 900                      # 15 min
    refresh_ttl_days: int = 14
    master_key: str = "dev-only-master-key-32-bytes!!"     # AES-GCM key material

    default_timezone: str = "America/Chicago"

    # OAuth (optional — endpoints return 501 until configured)
    google_client_id: str = ""
    google_client_secret: str = ""
    github_client_id: str = ""
    github_client_secret: str = ""
    oauth_redirect_base: str = "http://localhost:8000/api/v1"

    # AI provider chain (admin panel can override via DB later)
    ai_provider_chain: list[str] = ["OLLAMA", "OPENROUTER", "GEMINI", "ANTHROPIC", "OPENAI"]
    ollama_base_url: str = "http://localhost:11434"
    openrouter_api_key: str = ""
    gemini_api_key: str = ""
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    ai_daily_token_budget: int = 500_000
    embedding_dim: int = 768

    # SMTP (optional)
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "jobpilot@localhost"

    log_json: bool = Field(default=False, description="JSON logs (prod) vs console (dev)")


@lru_cache
def get_settings() -> Settings:
    return Settings()
