from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

import httpx
from pydantic import BaseModel, ConfigDict, Field

from devin_flow.config import Settings, get_settings


class DevinSession(BaseModel):
    model_config = ConfigDict(extra="ignore")

    session_id: str
    status: str
    title: str | None = None
    url: str | None = None


class SessionCreated(BaseModel):
    model_config = ConfigDict(extra="ignore")

    session_id: str
    url: str | None = None
    is_new_session: bool | None = None


class SessionCreate(BaseModel):
    prompt: str = Field(min_length=1, max_length=20_000)


class DevinNotConfiguredError(RuntimeError):
    pass


class DevinUpstreamError(RuntimeError):
    def __init__(self, status_code: int | None, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


@contextmanager
def _upstream_errors() -> Iterator[None]:
    try:
        yield
    except httpx.HTTPStatusError as exc:
        raise DevinUpstreamError(exc.response.status_code, exc.response.text) from exc
    except httpx.TransportError as exc:
        raise DevinUpstreamError(None, str(exc)) from exc
    except (ValueError, KeyError, TypeError) as exc:
        raise DevinUpstreamError(None, f"malformed devin response: {exc}") from exc


class DevinClient:
    def __init__(self, http: httpx.Client) -> None:
        self.http = http

    def list_sessions(self, limit: int = 20) -> list[DevinSession]:
        with _upstream_errors():
            response = self.http.get("/sessions", params={"limit": limit})
            response.raise_for_status()
            return [
                DevinSession.model_validate(session)
                for session in response.json()["sessions"]
            ]

    def create_session(self, payload: SessionCreate) -> SessionCreated:
        with _upstream_errors():
            response = self.http.post("/sessions", json=payload.model_dump())
            response.raise_for_status()
            return SessionCreated.model_validate(response.json())


def create_client(settings: Settings) -> DevinClient:
    if settings.devin_api_token is None:
        raise DevinNotConfiguredError("DEVIN_API_TOKEN is not set")
    http = httpx.Client(
        base_url=settings.devin_api_base_url,
        headers={"Authorization": f"Bearer {settings.devin_api_token}"},
        timeout=30,
    )
    return DevinClient(http)


@lru_cache
def get_devin_client() -> DevinClient:
    return create_client(get_settings())
