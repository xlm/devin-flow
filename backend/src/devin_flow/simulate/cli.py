import argparse
import json
from pathlib import Path

from sqlmodel import Session

from devin_flow import db
from devin_flow.config import get_settings
from devin_flow.devin.client import create_client
from devin_flow.simulate import report, reset, run
from devin_flow.simulate.scenario import load_scenario

PACKAGE_SCENARIO = Path(__file__).with_name("scenario.toml")
DEFAULT_WORK_DIR = Path("~/.cache/devin-flow/superset").expanduser()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="simulate-issues")
    parser.add_argument("--scenario", type=Path, default=PACKAGE_SCENARIO)
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_WORK_DIR)
    commands = parser.add_subparsers(dest="command", required=True)
    reset_parser = commands.add_parser("reset")
    _add_shared_options(reset_parser)
    reset_parser.add_argument("--no-wipe-invocations", action="store_true")
    run_parser = commands.add_parser("run")
    _add_shared_options(run_parser)
    run_parser.add_argument("--report", action="store_true")
    _add_report_options(run_parser)
    report_parser = commands.add_parser("report")
    _add_shared_options(report_parser)
    _add_report_options(report_parser)
    return parser


def _add_shared_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--scenario", type=Path, default=argparse.SUPPRESS)
    parser.add_argument("--work-dir", type=Path, default=argparse.SUPPRESS)


def _add_report_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--timeout", type=float, default=45 * 60)
    parser.add_argument("--flow-url", default="http://localhost:8000")


def main() -> None:
    args = build_parser().parse_args()
    settings = get_settings()
    scenario = load_scenario(
        args.scenario, default_repository=settings.seed_repository_full_name
    )
    if args.command == "reset":
        with Session(db.get_engine()) as session:
            reset.reset(
                scenario,
                work_dir=args.work_dir,
                session=session,
                devin_client=create_client(settings),
                wipe_invocations=not args.no_wipe_invocations,
            )
    elif args.command == "run":
        state = json.loads((args.work_dir / ".simulate-state.json").read_text())
        run.run(scenario, state=state, work_dir=args.work_dir)
        if args.report:
            raise SystemExit(
                report.report(
                    work_dir=args.work_dir,
                    timeout=args.timeout,
                    flow_url=args.flow_url,
                )
            )
    else:
        raise SystemExit(
            report.report(
                work_dir=args.work_dir,
                timeout=args.timeout,
                flow_url=args.flow_url,
            )
        )
