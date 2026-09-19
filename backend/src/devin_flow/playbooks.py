import json
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from devin_flow.devin.client import (
    DevinClient,
    DevinUpstreamError,
    PlaybookCreate,
    get_devin_client,
)

PLAYBOOKS_DIR = Path(__file__).resolve().parents[3] / "playbooks"

_HEADING = re.compile(r"^#+\s+(.+?)\s*$")


class PlaybookFile(BaseModel):
    path: Path
    title: str
    body: str
    structured_output_schema: dict[str, Any] | None


def load_playbook(path: Path) -> PlaybookFile:
    body = path.read_text()
    matches = (match for line in body.splitlines() if (match := _HEADING.match(line)))
    title = next((match.group(1) for match in matches), None)
    if title is None:
        raise ValueError(f"{path.name}: no markdown heading for the playbook title")
    schema_path = path.with_suffix(".schema.json")
    schema = json.loads(schema_path.read_text()) if schema_path.exists() else None
    return PlaybookFile(
        path=path, title=title, body=body, structured_output_schema=schema
    )


def sync_playbooks(
    client: DevinClient, directory: Path = PLAYBOOKS_DIR
) -> Iterator[tuple[Path, str]]:
    if not directory.is_dir():
        raise ValueError(f"{directory}: playbooks directory not found")
    files = [
        load_playbook(path)
        for path in sorted(directory.glob("*.md"))
        if path.name.lower() != "readme.md"
    ]
    by_title: dict[str, list[Path]] = {}
    for playbook_file in files:
        by_title.setdefault(playbook_file.title, []).append(playbook_file.path)
    for title, paths in sorted(by_title.items()):
        if len(paths) > 1:
            names = ", ".join(sorted(path.name for path in paths))
            raise ValueError(f"duplicate playbook title {title!r}: {names}")
    existing = {playbook.title: playbook for playbook in client.list_playbooks()}
    for playbook_file in files:
        current = existing.get(playbook_file.title)
        payload = PlaybookCreate(
            title=playbook_file.title,
            body=playbook_file.body,
            macro=current.macro if current is not None else None,
            structured_output_schema=playbook_file.structured_output_schema,
        )
        if current is not None:
            client.update_playbook(current.playbook_id, payload)
            yield playbook_file.path, "updated"
        else:
            client.create_playbook(payload)
            yield playbook_file.path, "created"


def main() -> None:
    try:
        for path, action in sync_playbooks(get_devin_client(), PLAYBOOKS_DIR):
            print(f"{action} {path.name}")
    except (DevinUpstreamError, ValueError, OSError) as exc:
        print(f"sync-playbooks failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
