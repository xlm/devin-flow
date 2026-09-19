from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from devin_flow.api.health import STALE_INTERVALS, polling_status
from devin_flow.config import get_settings
from devin_flow.models import PollerState

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def set_interval(monkeypatch: pytest.MonkeyPatch, seconds: str) -> None:
    monkeypatch.setenv("POLL_INTERVAL_SECONDS", seconds)
    get_settings.cache_clear()


def test_health_never_polled_with_polling_disabled(unit_client: TestClient) -> None:
    response = unit_client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "polling": {
            "enabled": False,
            "interval_seconds": 0,
            "last_success_at": None,
            "stale": False,
        },
    }


def test_health_never_polled_with_polling_enabled(
    unit_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    set_interval(monkeypatch, "60")
    polling = unit_client.get("/api/health").json()["polling"]
    assert polling == {
        "enabled": True,
        "interval_seconds": 60,
        "last_success_at": None,
        "stale": True,
    }


def test_health_reports_recent_poll_as_live(
    unit_client: TestClient, unit_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    set_interval(monkeypatch, "60")
    last = datetime.now(UTC) - timedelta(seconds=30)
    unit_session.add(PollerState(last_success_at=last))
    unit_session.commit()
    polling = unit_client.get("/api/health").json()["polling"]
    assert polling["enabled"] is True
    assert polling["stale"] is False
    # sqlite returns naive timestamps, so compare without tzinfo
    reported = datetime.fromisoformat(polling["last_success_at"])
    assert reported.replace(tzinfo=None) == last.replace(tzinfo=None)


def test_health_reports_old_poll_as_stale(
    unit_client: TestClient, unit_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    set_interval(monkeypatch, "60")
    last = datetime.now(UTC) - timedelta(seconds=STALE_INTERVALS * 60 + 1)
    unit_session.add(PollerState(last_success_at=last))
    unit_session.commit()
    polling = unit_client.get("/api/health").json()["polling"]
    assert polling["enabled"] is True
    assert polling["stale"] is True


def test_health_ignores_staleness_when_polling_disabled(
    unit_client: TestClient, unit_session: Session
) -> None:
    unit_session.add(PollerState(last_success_at=NOW - timedelta(days=1)))
    unit_session.commit()
    polling = unit_client.get("/api/health").json()["polling"]
    assert polling["enabled"] is False
    assert polling["stale"] is False
    assert polling["last_success_at"] is not None


@pytest.mark.parametrize(
    ("age", "stale"),
    [
        (timedelta(seconds=0), False),
        (timedelta(seconds=STALE_INTERVALS * 60), False),
        (timedelta(seconds=STALE_INTERVALS * 60 + 1), True),
    ],
)
def test_polling_status_stale_boundary(age: timedelta, stale: bool) -> None:
    status = polling_status(NOW - age, 60, NOW)
    assert status.stale is stale


def test_polling_status_treats_naive_timestamps_as_utc() -> None:
    naive = (NOW - timedelta(seconds=10)).replace(tzinfo=None)
    assert polling_status(naive, 60, NOW).stale is False
