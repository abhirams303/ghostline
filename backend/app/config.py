import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_PATH = BACKEND_DIR / "data" / "runtime" / "opsec_mirror.sqlite3"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
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
    adsbexchange_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "OPSEC_MIRROR_ADSBEXCHANGE_API_KEY",
            "ADSBEXCHANGE_API_KEY",
        ),
    )
    adsb_base_url: str = "https://adsbexchange.com"
    adsb_timeout_seconds: float = 10.0
    adsb_max_aircraft: int = 25
    adsb_low_altitude_threshold_ft: int = 5000
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
    database_path: Path = DEFAULT_DATABASE_PATH

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

    @field_validator("database_path", mode="before")
    @classmethod
    def resolve_database_path(cls, value: Any) -> Path:
        if value in (None, ""):
            return DEFAULT_DATABASE_PATH

        path = Path(value)
        if path.is_absolute():
            return path
        return BACKEND_DIR / path


@lru_cache
def get_settings() -> Settings:
    return Settings()
