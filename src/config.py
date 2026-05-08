"""Configuration management for AI Twitter Scanner."""

from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TwitterSettings(BaseSettings):
    """Twitter/X specific settings."""

    username: str = Field(default="", description="Twitter username (without @)")
    password: str = Field(default="", description="Twitter password")
    email: str = Field(default="", description="Twitter email")
    auth_cookie: Optional[str] = Field(default=None, description="JSON serialized auth cookies")
    min_like_count: int = Field(default=100, description="Minimum like count to consider")
    max_tweet_age_hours: int = Field(default=24 * 7, description="Max age of tweets to fetch")


class ProxySettings(BaseSettings):
    """Proxy configuration."""

    enabled: bool = Field(default=False, description="Enable proxy rotation")
    api_key: str = Field(default="", description="Proxy API key")
    proxy_url: str = Field(default="", description="Proxy endpoint")
    rotation_interval: int = Field(default=300, description="Seconds between IP rotations")


class DatabaseSettings(BaseSettings):
    """Database configuration."""

    postgres_host: str = Field(default="localhost", description="PostgreSQL host")
    postgres_port: int = Field(default=5432, description="PostgreSQL port")
    postgres_db: str = Field(default="twitter_scanner", description="Database name")
    postgres_user: str = Field(default="postgres", description="Database user")
    postgres_password: str = Field(default="", description="Database password")
    chroma_persist_dir: Path = Field(
        default=Path("./data/chroma_db"), description="ChromaDB persistence directory"
    )


class AISettings(BaseSettings):
    """AI/LLM configuration."""

    provider: str = Field(default="openai", description="AI provider: openai, ollama, groq")
    model: str = Field(default="gpt-4o-mini", description="LLM model name")
    api_key: str = Field(default="", description="API key for the AI provider")
    base_url: Optional[str] = Field(default=None, description="Custom base URL (for Ollama)")
    temperature: float = Field(default=0.7, description="LLM temperature")
    max_tokens: int = Field(default=1000, description="Max tokens in response")


class AlertSettings(BaseSettings):
    """Alert configuration."""

    telegram_bot_token: str = Field(default="", description="Telegram bot token")
    telegram_chat_id: str = Field(default="", description="Telegram chat ID")
    discord_webhook_url: str = Field(default="", description="Discord webhook URL")
    alert_threshold: float = Field(default=0.8, description="Sentiment threshold for alerts")


class ScannerSettings(BaseSettings):
    """Scanner behavior configuration."""

    headless: bool = Field(default=True, description="Run browser headless")
    min_delay: float = Field(default=2.0, description="Minimum delay between actions (seconds)")
    max_delay: float = Field(default=5.0, description="Maximum delay between actions (seconds)")
    max_retries: int = Field(default=3, description="Max retries for failed operations")
    timeout: int = Field(default=30000, description="Page timeout in milliseconds")
    stealth_enabled: bool = Field(default=True, description="Enable stealth mode")


class Settings(BaseSettings):
    """Main settings container."""

    model_config = SettingsConfigDict(
        env_prefix="TWITTER_SCANNER_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    twitter: TwitterSettings = Field(default_factory=TwitterSettings)
    proxy: ProxySettings = Field(default_factory=ProxySettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    ai: AISettings = Field(default_factory=AISettings)
    alert: AlertSettings = Field(default_factory=AlertSettings)
    scanner: ScannerSettings = Field(default_factory=ScannerSettings)

    tracked_handles: list[str] = Field(
        default_factory=lambda: [
            "elonmusk",
            "PreetBharatara",
            "zerohedge",
            "jimcramer",
            "Carl_Ichan",
            "davidfaber",
            "Mad_Finance",
            "BaldyCap",
            "acobles",
            "SchuldheissDe",
        ],
        description="List of handles to track",
    )


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get or create the global settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """Reload settings from environment."""
    global _settings
    _settings = Settings()
    return _settings