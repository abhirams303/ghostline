import json
from functools import lru_cache
from typing import Annotated, Any

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="OPSEC_MIRROR_",
        extra="ignore",
    )

    app_name: str = "OPSEC Mirror API"
    env: str = "development"
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )
    cache_ttl_seconds: int = 900
    use_demo_cache: bool = False
    strava_enabled: bool = False
    adsb_enabled: bool = False
    satellite_enabled: bool = True
    exa_enabled: bool = False
    openai_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPSEC_MIRROR_OPENAI_API_KEY", "OPENAI_API_KEY"),
    )
    openai_model: str = "gpt-5.4-mini"
    exa_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPSEC_MIRROR_EXA_API_KEY", "EXA_API_KEY"),
    )
    mapbox_token: str | None = None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> list[str]:
        if isinstance(value, list):
            return value

        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                return json.loads(stripped)
            return [item.strip() for item in stripped.split(",") if item.strip()]

        return ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
