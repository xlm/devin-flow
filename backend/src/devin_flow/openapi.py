import json
from pathlib import Path

from devin_flow.app import create_app


def dump_openapi() -> str:
    app = create_app(static_dir=Path("/nonexistent"))
    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


def main() -> None:
    print(dump_openapi(), end="")


if __name__ == "__main__":
    main()
