import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from devin_flow.simulate import report


def test_report_maps_structured_and_title_outcomes(tmp_path: Path) -> None:
    (tmp_path / ".simulate-run.json").write_text(
        json.dumps(
            {
                "issues": [
                    {"number": 1, "expected_outcome": "fixed"},
                    {"number": 2, "expected_outcome": "duplicate"},
                ]
            }
        )
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json=[
                {
                    "status": "running",
                    "title": "Triage issue #2",
                    "structured_output": {"issue_number": 2, "outcome": "duplicate"},
                    "pull_requests": [],
                    "url": "session-2",
                },
                {
                    "status": "error",
                    "title": "Fix issue #1",
                    "structured_output": None,
                    "pull_requests": [{"pr_url": "pr-1"}],
                    "url": "session-1",
                },
            ],
        )
    )
    with httpx.Client(transport=transport, base_url="http://flow") as client:
        assert report.report(work_dir=tmp_path, http=client) == 0


def test_report_terminal_without_outcome_is_a_mismatch(tmp_path: Path) -> None:
    (tmp_path / ".simulate-run.json").write_text(
        json.dumps({"issues": [{"number": 1, "expected_outcome": "fixed"}]})
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json=[
                {
                    "status": "exit",
                    "title": "Triage issue #1",
                    "structured_output": None,
                    "pull_requests": [],
                }
            ],
        )
    )
    with httpx.Client(transport=transport, base_url="http://flow") as client:
        assert report.report(work_dir=tmp_path, http=client) == 1


def test_report_waits_for_running_invocation_without_outcome(tmp_path: Path) -> None:
    (tmp_path / ".simulate-run.json").write_text(
        json.dumps({"issues": [{"number": 1, "expected_outcome": "fixed"}]})
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json=[
                {
                    "status": "running",
                    "title": "Triage issue #1",
                    "structured_output": None,
                    "pull_requests": [],
                }
            ],
        )
    )
    with httpx.Client(transport=transport, base_url="http://flow") as client:
        assert report.report(work_dir=tmp_path, timeout=0, http=client) == 1


def test_report_times_out(tmp_path: Path, capsys: Any) -> None:
    (tmp_path / ".simulate-run.json").write_text(
        json.dumps({"issues": [{"number": 1}]})
    )
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=[]))
    with httpx.Client(transport=transport, base_url="http://flow") as client:
        assert report.report(work_dir=tmp_path, timeout=0, http=client) == 1
    assert "timed out" in capsys.readouterr().out


def test_report_waits_and_closes_owned_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".simulate-run.json").write_text(
        json.dumps({"issues": [{"number": 1, "expected_outcome": "fixed"}]})
    )
    clock = [0.0]

    class FakeClient:
        def get(self, path: str) -> httpx.Response:
            return httpx.Response(
                200,
                json=[],
                request=httpx.Request("GET", "http://flow/api/invocations"),
            )

        def close(self) -> None:
            closed.append(True)

    closed: list[bool] = []
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: FakeClient())

    def sleep(seconds: float) -> None:
        clock[0] += seconds

    assert (
        report.report(
            work_dir=tmp_path,
            timeout=1,
            sleep=sleep,
            now=lambda: clock[0],
        )
        == 1
    )
    assert closed == [True]
    assert report._issue_number({"title": "no issue"}) is None
