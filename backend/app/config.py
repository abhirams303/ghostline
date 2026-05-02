from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="OPSEC_MIRROR_",
        extra="ignore",
    )

    app_name: str = "OPSEC Mirror API"
    env: str = "development"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    cache_ttl_seconds: int = 900
    use_demo_cache: bool = False
    strava_enabled: bool = False
    adsb_enabled: bool = False
    satellite_enabled: bool = True
    exa_enabled: bool = False
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    exa_api_key: str | None = None
    mapbox_token: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
