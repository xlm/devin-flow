from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from devin_flow.config import Settings, get_settings


class DevinSession(BaseModel):
    model_config = ConfigDict(extra="ignore")

    session_id: str
    status: Literal[
        "new", "claimed", "running", "exit", "error", "suspended", "resuming"
    ]
    title: str | None = None
    url: str | None = None


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
        status_code = exc.response.status_code
        raise DevinUpstreamError(
            status_code, f"devin api returned HTTP {status_code}"
        ) from exc
    except httpx.TransportError as exc:
        raise DevinUpstreamError(None, "devin api unreachable") from exc
    except (ValueError, KeyError, TypeError) as exc:
        raise DevinUpstreamError(None, "malformed devin response") from exc


class DevinClient:
    def __init__(self, http: httpx.Client, org_id: str) -> None:
        self.http = http
        self.org_id = org_id

    def list_sessions(self, limit: int = 100) -> list[DevinSession]:
        with _upstream_errors():
            response = self.http.get(
                f"/organizations/{self.org_id}/sessions",
                params={"first": limit},
            )
            response.raise_for_status()
            return [
                DevinSession.model_validate(session)
                for session in response.json()["items"]
            ]

    def create_session(self, payload: SessionCreate) -> DevinSession:
        with _upstream_errors():
            response = self.http.post(
                f"/organizations/{self.org_id}/sessions",
                json=payload.model_dump(),
            )
            response.raise_for_status()
            return DevinSession.model_validate(response.json())


def create_client(settings: Settings) -> DevinClient:
    if not settings.devin_api_token:
        raise DevinNotConfiguredError("DEVIN_API_TOKEN is not set")
    if not settings.devin_org_id:
        raise DevinNotConfiguredError("DEVIN_ORG_ID is not set")
    url = httpx.URL(settings.devin_api_base_url)
    if url.scheme != "https" and not (
        url.scheme == "http" and url.host in {"localhost", "127.0.0.1", "::1"}
    ):
        raise DevinNotConfiguredError("DEVIN_API_BASE_URL must use https")
    http = httpx.Client(
        base_url=settings.devin_api_base_url,
        headers={"Authorization": f"Bearer {settings.devin_api_token}"},
        timeout=30,
    )
    return DevinClient(http, settings.devin_org_id)


@lru_cache
def get_devin_client() -> DevinClient:
    return create_client(get_settings())
