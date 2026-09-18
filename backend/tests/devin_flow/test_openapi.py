import json

import pytest

from devin_flow.openapi import dump_openapi, main


def test_dump_openapi_includes_health_endpoint() -> None:
    spec = json.loads(dump_openapi())
    assert spec["paths"]["/api/health"]["get"]
    assert spec["components"]["schemas"]["HealthResponse"]


def test_dump_openapi_includes_items_endpoints() -> None:
    spec = json.loads(dump_openapi())
    assert set(spec["paths"]["/api/items"]) == {"get", "post"}
    assert spec["components"]["schemas"]["ItemCreate"]
    assert spec["components"]["schemas"]["ItemRead"]


def test_dump_openapi_is_deterministic() -> None:
    assert dump_openapi() == dump_openapi()


def test_main_prints_dump(capsys: pytest.CaptureFixture[str]) -> None:
    main()
    captured = capsys.readouterr()
    assert captured.out == dump_openapi()
