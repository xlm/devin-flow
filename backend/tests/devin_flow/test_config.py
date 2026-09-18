from pathlib import Path

import pytest

from devin_flow.config import DEFAULT_STATIC_DIR, Settings, get_settings


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("STATIC_DIR", raising=False)
    monkeypatch.delenv("DEVIN_API_TOKEN", raising=False)
    monkeypatch.delenv("DEVIN_API_BASE_URL", raising=False)
    monkeypatch.delenv("DEVIN_ORG_ID", raising=False)
    monkeypatch.chdir(tmp_path)  # no stray .env
    get_settings.cache_clear()


def test_defaults() -> None:
    settings = Settings()
    assert settings.database_url == (
        "postgresql+psycopg://devin:devin@localhost:5432/devin_flow"
    )
    assert settings.static_dir == DEFAULT_STATIC_DIR
    assert settings.devin_api_token is None
    assert settings.devin_api_base_url == "https://api.devin.ai/v3"
    assert settings.devin_org_id is None
    assert DEFAULT_STATIC_DIR.parts[-2:] == ("frontend", "dist")


def test_env_overrides(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db:5432/x")
    monkeypatch.setenv("STATIC_DIR", str(tmp_path))
    monkeypatch.setenv("DEVIN_API_TOKEN", "test-token")
    monkeypatch.setenv("DEVIN_API_BASE_URL", "https://devin.example/v3")
    monkeypatch.setenv("DEVIN_ORG_ID", "org-test")
    settings = Settings()
    assert settings.database_url == "postgresql+psycopg://u:p@db:5432/x"
    assert settings.static_dir == tmp_path
    assert settings.devin_api_token == "test-token"
    assert settings.devin_api_base_url == "https://devin.example/v3"
    assert settings.devin_org_id == "org-test"


def test_dotenv_file_is_read_and_unrelated_keys_ignored(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        "DATABASE_URL=postgresql+psycopg://a:b@h/d\nVITE_API_URL=/api\n"
    )
    assert Settings().database_url == "postgresql+psycopg://a:b@h/d"


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()
    get_settings.cache_clear()
    assert get_settings() is not None
