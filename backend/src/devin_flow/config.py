from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
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
    seed_playbook_id: str | None = None
    seed_repository_full_name: str = "xlm/superset"

    @field_validator("seed_playbook_id", mode="before")
    @classmethod
    def normalize_seed_playbook_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


@lru_cache
def get_settings() -> Settings:
    return Settings()
