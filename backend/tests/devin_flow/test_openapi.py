import json

import pytest

from devin_flow.openapi import dump_openapi, main


def test_dump_openapi_includes_health_endpoint() -> None:
    spec = json.loads(dump_openapi())
    assert spec["paths"]["/api/health"]["get"]
    assert spec["components"]["schemas"]["HealthResponse"]


def test_dump_openapi_has_no_items_endpoints() -> None:
    spec = json.loads(dump_openapi())
    assert "/api/items" not in spec["paths"]
    assert not {"ItemCreate", "ItemRead"} & set(spec["components"]["schemas"])


def test_dump_openapi_is_deterministic() -> None:
    assert dump_openapi() == dump_openapi()


def test_main_prints_dump(capsys: pytest.CaptureFixture[str]) -> None:
    main()
    captured = capsys.readouterr()
    assert captured.out == dump_openapi()
