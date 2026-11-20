"""Application configuration from environment variables and .env."""
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_mode: Literal["all", "telegram", "api"] = "all"
    bot_token: str | None = None
    api_key: str | None = None
    api_host: str = "0.0.0.0"
    api_port: int = Field(default=8000, ge=1, le=65535)
    database_url: str = "sqlite+aiosqlite:////data/weather.db"
    redis_url: str | None = None
    cache_ttl_seconds: int = Field(default=900, ge=30, le=86400)
    request_timeout_seconds: float = Field(default=12.0, gt=0, le=120)
    forecast_days: int = Field(default=7, ge=1, le=16)
    met_user_agent: str = "WetherBot/0.1 (+https://github.com/wether-bot/wether-bot)"
    openweather_api_key: str | None = None
    weatherapi_key: str | None = None
    enable_gfs: bool = True
    enable_icon: bool = True
    enable_ecmwf: bool = True
    enable_met_no: bool = True
    enable_open_meteo: bool = True

    @field_validator("bot_token", "api_key", "redis_url", "openweather_api_key", "weatherapi_key", mode="before")
    @classmethod
    def empty_to_none(cls, value: str | None) -> str | None:
        return value or None


@lru_cache
def get_settings() -> Settings:
    return Settings()
