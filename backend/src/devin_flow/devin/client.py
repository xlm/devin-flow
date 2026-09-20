from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from devin_flow.config import Settings, get_settings

# v3 session status enum: new, claimed, running, exit, error, suspended,
# resuming. Suspended sessions can resume, so only exit and error are final.
TERMINAL_SESSION_STATUSES = frozenset({"exit", "error"})


class SessionPullRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pr_url: str
    pr_state: str | None = None


class DevinSession(BaseModel):
    model_config = ConfigDict(extra="ignore")

    session_id: str
    status: str
    title: str | None = None
    url: str | None = None
    automation_id: str | None = None
    pull_requests: list[SessionPullRequest] = []
    structured_output: dict[str, Any] | None = None
    created_at: int | None = None
    updated_at: int | None = None


class SessionCreate(BaseModel):
    prompt: str = Field(min_length=1, max_length=20_000)


class Playbook(BaseModel):
    model_config = ConfigDict(extra="ignore")

    playbook_id: str
    title: str
    body: str
    macro: str | None = None
    structured_output_schema: dict[str, Any] | None = None


class Repository(BaseModel):
    model_config = ConfigDict(extra="ignore")

    repo_path: str
    repo_name: str


class PlaybookCreate(BaseModel):
    title: str = Field(min_length=1)
    body: str = Field(min_length=1)
    macro: str | None = None
    structured_output_schema: dict[str, Any] | None = None


class AutomationCondition(BaseModel):
    field: str
    operator: Literal["eq"] = "eq"
    value: str


class AutomationConditionGroup(BaseModel):
    all: list[AutomationCondition]


class AutomationConditions(BaseModel):
    any: list[AutomationConditionGroup]


class AutomationTrigger(BaseModel):
    event_type: str
    conditions: AutomationConditions


class AutomationAction(BaseModel):
    type: Literal["start_session"] = "start_session"
    prompt: str


class AutomationRunAs(BaseModel):
    type: Literal["organization"] = "organization"


class AutomationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=500)
    enabled: bool
    triggers: list[AutomationTrigger]
    actions: list[AutomationAction]
    run_as: AutomationRunAs = AutomationRunAs()
    metadata: dict[str, str]


class AutomationUpdate(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    triggers: list[AutomationTrigger] | None = None
    actions: list[AutomationAction] | None = None
    metadata: dict[str, str] | None = None


class Automation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    automation_id: str
    name: str
    enabled: bool
    metadata: dict[str, str] = {}


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

    def list_sessions(
        self,
        limit: int = 100,
        *,
        automation_ids: list[str] | None = None,
        created_after: int | None = None,
        paginate: bool = False,
    ) -> list[DevinSession]:
        # the v3 API reads list filters as repeated flat query keys
        # (automation_ids=a&automation_ids=b) and epoch seconds for created_after
        with _upstream_errors():
            sessions: list[DevinSession] = []
            params: dict[str, str | int | list[str]] = {"first": limit}
            if automation_ids is not None:
                params["automation_ids"] = automation_ids
            if created_after is not None:
                params["created_after"] = created_after
            while True:
                response = self.http.get(
                    f"/organizations/{self.org_id}/sessions",
                    params=params,
                )
                response.raise_for_status()
                page = response.json()
                sessions.extend(
                    DevinSession.model_validate(session) for session in page["items"]
                )
                if not (paginate and page.get("has_next_page")):
                    return sessions
                params["after"] = page["end_cursor"]

    def get_session(self, session_id: str) -> DevinSession:
        with _upstream_errors():
            response = self.http.get(
                f"/organizations/{self.org_id}/sessions/{session_id}"
            )
            response.raise_for_status()
            return DevinSession.model_validate(response.json())

    def terminate_session(self, session_id: str) -> DevinSession:
        with _upstream_errors():
            response = self.http.delete(
                f"/organizations/{self.org_id}/sessions/{session_id}"
            )
            response.raise_for_status()
            return DevinSession.model_validate(response.json())

    def create_session(self, payload: SessionCreate) -> DevinSession:
        with _upstream_errors():
            response = self.http.post(
                f"/organizations/{self.org_id}/sessions",
                json=payload.model_dump(),
            )
            response.raise_for_status()
            return DevinSession.model_validate(response.json())

    def archive_session(self, session_id: str) -> DevinSession:
        with _upstream_errors():
            response = self.http.post(
                f"/organizations/{self.org_id}/sessions/{session_id}/archive"
            )
            response.raise_for_status()
            return DevinSession.model_validate(response.json())

    def list_playbooks(self) -> list[Playbook]:
        with _upstream_errors():
            playbooks: list[Playbook] = []
            params: dict[str, str | int] = {"first": 100}
            while True:
                response = self.http.get(
                    f"/organizations/{self.org_id}/playbooks",
                    params=params,
                )
                response.raise_for_status()
                page = response.json()
                playbooks.extend(
                    Playbook.model_validate(playbook) for playbook in page["items"]
                )
                if not page.get("has_next_page"):
                    return playbooks
                params["after"] = page["end_cursor"]

    def _beta_url(self, path: str) -> httpx.URL:
        base = self.http.base_url
        prefix = base.path.rstrip("/").removesuffix("/v3")
        return base.copy_with(path=f"{prefix}/v3beta1{path}")

    def list_repositories(self) -> list[Repository]:
        with _upstream_errors():
            repositories: list[Repository] = []
            params: dict[str, str | int] = {
                "first": 100,
                "load_indexing_status": "false",
            }
            while True:
                response = self.http.get(
                    self._beta_url(f"/organizations/{self.org_id}/repositories"),
                    params=params,
                )
                response.raise_for_status()
                page = response.json()
                repositories.extend(
                    Repository.model_validate(repository)
                    for repository in page["items"]
                )
                if not page.get("has_next_page"):
                    return repositories
                params["after"] = page["end_cursor"]

    def create_playbook(self, payload: PlaybookCreate) -> Playbook:
        with _upstream_errors():
            response = self.http.post(
                f"/organizations/{self.org_id}/playbooks",
                json=payload.model_dump(),
            )
            response.raise_for_status()
            return Playbook.model_validate(response.json())

    def update_playbook(self, playbook_id: str, payload: PlaybookCreate) -> Playbook:
        with _upstream_errors():
            response = self.http.put(
                f"/organizations/{self.org_id}/playbooks/{playbook_id}",
                json=payload.model_dump(),
            )
            response.raise_for_status()
            return Playbook.model_validate(response.json())

    def list_automations(
        self, metadata: dict[str, str] | None = None
    ) -> list[Automation]:
        with _upstream_errors():
            automations: list[Automation] = []
            params: dict[str, str | int] = {"first": 100}
            for key, value in (metadata or {}).items():
                params[f"metadata.{key}"] = value
            while True:
                response = self.http.get(
                    f"/organizations/{self.org_id}/automations",
                    params=params,
                )
                response.raise_for_status()
                page = response.json()
                automations.extend(
                    Automation.model_validate(automation)
                    for automation in page["items"]
                )
                if not page.get("has_next_page"):
                    return automations
                params["after"] = page["end_cursor"]

    def create_automation(self, payload: AutomationCreate) -> Automation:
        with _upstream_errors():
            response = self.http.post(
                f"/organizations/{self.org_id}/automations",
                json=payload.model_dump(),
            )
            response.raise_for_status()
            return Automation.model_validate(response.json())

    def update_automation(
        self, automation_id: str, payload: AutomationUpdate
    ) -> Automation:
        with _upstream_errors():
            response = self.http.patch(
                f"/organizations/{self.org_id}/automations/{automation_id}",
                json=payload.model_dump(exclude_none=True),
            )
            response.raise_for_status()
            return Automation.model_validate(response.json())


def create_client(settings: Settings) -> DevinClient:
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
