import json
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import httpx

from devin_flow.devin.client import TERMINAL_SESSION_STATUSES

ISSUE_NUMBER = re.compile(r"#(\d+)\b")


def report(
    *,
    work_dir: Path,
    flow_url: str = "http://localhost:8000",
    timeout: float = 45 * 60,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
    http: httpx.Client | None = None,
) -> int:
    run = json.loads((work_dir / ".simulate-run.json").read_text())
    deadline = now() + timeout
    client = http or httpx.Client(base_url=flow_url)
    try:
        while True:
            response = client.get("/api/invocations")
            response.raise_for_status()
            invocations = response.json()
            by_issue = {
                number: item
                for item in invocations
                if (number := _issue_number(item)) is not None
                and (
                    item["status"] in TERMINAL_SESSION_STATUSES
                    or item.get("pull_requests")
                    or (item.get("structured_output") or {}).get("outcome")
                )
            }
            if all(item["number"] in by_issue for item in run["issues"]):
                break
            if now() >= deadline:
                print("report timed out")
                return 1
            sleep(min(30, max(0, deadline - now())))
        mismatches = 0
        print("issue  expected           actual             session")
        for item in run["issues"]:
            invocation = by_issue[item["number"]]
            actual = (
                "fixed"
                if invocation.get("pull_requests")
                else (invocation.get("structured_output") or {}).get("outcome")
            )
            session_url = invocation.get("url") or ""
            print(
                f"#{item['number']:<5} {item['expected_outcome']:<17} "
                f"{str(actual):<18} {session_url}"
            )
            mismatches += actual != item["expected_outcome"]
        return 1 if mismatches else 0
    finally:
        if http is None:
            client.close()


def _issue_number(invocation: dict[str, Any]) -> int | None:
    structured = invocation.get("structured_output")
    if isinstance(structured, dict) and isinstance(structured.get("issue_number"), int):
        return cast(int, structured["issue_number"])
    match = ISSUE_NUMBER.search(invocation.get("title") or "")
    return int(match.group(1)) if match else None
