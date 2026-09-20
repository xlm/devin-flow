import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from devin_flow.config import Settings
from devin_flow.simulate import cli
from devin_flow.simulate.scenario import load_scenario

from .conftest import SCENARIO_PATH


def test_cli_parser_and_dispatch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["--work-dir", str(tmp_path), "report", "--timeout", "1"])
    assert args.command == "report"
    assert (
        parser.parse_args(["report", "--work-dir", str(tmp_path)]).work_dir == tmp_path
    )
    scenario = load_scenario(SCENARIO_PATH, default_repository="xlm/superset")
    monkeypatch.setattr(cli, "load_scenario", lambda path, **kw: scenario)
    monkeypatch.setattr(cli, "report", SimpleNamespace(report=lambda **kwargs: 0))
    monkeypatch.setattr(
        sys, "argv", ["simulate-issues", "--work-dir", str(tmp_path), "report"]
    )
    with pytest.raises(SystemExit) as raised:
        cli.main()
    assert raised.value.code == 0


def test_cli_dispatches_run_and_reset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    scenario = load_scenario(SCENARIO_PATH, default_repository="xlm/superset")
    monkeypatch.setattr(cli, "load_scenario", lambda path, **kw: scenario)
    (tmp_path / ".simulate-state.json").write_text(json.dumps({"reset_sha": "sha"}))
    run_calls: list[Any] = []
    monkeypatch.setattr(
        cast(Any, cli).run,
        "run",
        lambda scenario, **kwargs: run_calls.append((scenario, kwargs)),
    )
    monkeypatch.setattr(
        sys, "argv", ["simulate-issues", "run", "--work-dir", str(tmp_path)]
    )
    cli.main()
    assert run_calls

    report_calls: list[dict[str, Any]] = []

    def fake_report(**kwargs: Any) -> int:
        report_calls.append(kwargs)
        return 0

    monkeypatch.setattr(cli, "report", SimpleNamespace(report=fake_report))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "simulate-issues",
            "run",
            "--report",
            "--timeout",
            "5",
            "--work-dir",
            str(tmp_path),
        ],
    )
    with pytest.raises(SystemExit) as raised:
        cli.main()
    assert raised.value.code == 0
    assert report_calls == [
        {
            "work_dir": tmp_path,
            "timeout": 5.0,
            "flow_url": "http://localhost:8000",
        }
    ]

    class FakeSession:
        def __enter__(self) -> Any:
            return self

        def __exit__(self, *args: Any) -> None:
            return None

    monkeypatch.setattr(cli, "Session", lambda engine: FakeSession())
    monkeypatch.setattr(cast(Any, cli).db, "get_engine", lambda: object())
    monkeypatch.setattr(
        cli,
        "get_settings",
        lambda: Settings(devin_api_token="token", devin_org_id="org"),
    )
    monkeypatch.setattr(cli, "create_client", lambda settings: object())
    reset_calls: list[Any] = []
    monkeypatch.setattr(
        cast(Any, cli).reset,
        "reset",
        lambda scenario, **kwargs: reset_calls.append((scenario, kwargs)),
    )
    monkeypatch.setattr(
        sys, "argv", ["simulate-issues", "reset", "--work-dir", str(tmp_path)]
    )
    cli.main()
    assert reset_calls
