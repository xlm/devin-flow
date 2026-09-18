from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_STATIC_DIR = Path(__file__).resolve().parents[3] / "frontend" / "dist"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://devin:devin@localhost:5432/devin_flow"
    static_dir: Path = DEFAULT_STATIC_DIR


@lru_cache
def get_settings() -> Settings:
    return Settings()
