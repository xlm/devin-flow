from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_STATIC_DIR = Path(__file__).resolve().parents[3] / "frontend" / "dist"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://devin:devin@localhost:5432/devin_flow"
    static_dir: Path = DEFAULT_STATIC_DIR
    devin_api_token: str = Field(min_length=1)
    devin_api_base_url: str = "https://api.devin.ai/v3"
    devin_org_id: str = Field(min_length=1)
    poll_interval_seconds: float = Field(default=15, ge=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
