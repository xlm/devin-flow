from pathlib import Path

import pytest

from devin_flow.simulate.scenario import Scenario, load_scenario

from .conftest import SCENARIO_PATH


def test_packaged_scenario_has_expected_issue_phases() -> None:
    scenario = load_scenario(SCENARIO_PATH)
    assert len(scenario.poisons) == 3
    assert scenario.patch_dir == SCENARIO_PATH.resolve().parent / "patches"
    assert [issue.phase for issue in scenario.issues] == [
        "original",
        "original",
        "original",
        "filler",
        "filler",
        "filler",
        "duplicate",
        "duplicate",
    ]


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("baseline", "baseline"),
        ("poisons", "poison ids"),
        ("issues", "issue ids"),
    ],
)
def test_scenario_rejects_invalid_ids(
    field: str, message: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = load_scenario(SCENARIO_PATH).model_dump()
    if field == "baseline":
        scenario[field] = "not-a-sha"
    elif field == "poisons":
        scenario[field][1]["id"] = scenario[field][0]["id"]
    else:
        scenario[field][1]["id"] = scenario[field][0]["id"]
    with pytest.raises(ValueError, match=message):
        Scenario.model_validate(scenario)


def test_scenario_rejects_phase_and_duplicate_rules() -> None:
    scenario = load_scenario(SCENARIO_PATH).model_dump()
    scenario["issues"][0]["phase"] = "filler"
    with pytest.raises(ValueError, match="ordered"):
        Scenario.model_validate(scenario)

    scenario = load_scenario(SCENARIO_PATH).model_dump()
    scenario["issues"][-1]["duplicate_of"] = "missing"
    with pytest.raises(ValueError, match="reference"):
        Scenario.model_validate(scenario)

    scenario = load_scenario(SCENARIO_PATH).model_dump()
    scenario["issues"][-1]["duplicate_of"] = None
    with pytest.raises(ValueError, match="require"):
        Scenario.model_validate(scenario)

    scenario = load_scenario(SCENARIO_PATH).model_dump()
    scenario["issues"][0]["duplicate_of"] = "date-parser-offset"
    with pytest.raises(ValueError, match="only valid"):
        Scenario.model_validate(scenario)

    scenario = load_scenario(SCENARIO_PATH).model_dump()
    scenario["issues"][0]["id"] = "missing-poison"
    scenario["issues"] = scenario["issues"][:6]
    with pytest.raises(ValueError, match="fixed originals"):
        Scenario.model_validate(scenario)

    scenario = load_scenario(SCENARIO_PATH).model_dump()
    scenario["poisons"][0]["patch"] = "../escape.patch"
    with pytest.raises(ValueError):
        Scenario.model_validate(scenario)

    scenario = load_scenario(SCENARIO_PATH).model_dump()
    scenario["poisons"].append(
        {
            "id": "unused",
            "patch": "unused.patch",
            "failing_test": "tests/unit_tests/test_unused.py::test_unused",
        }
    )
    with pytest.raises(ValueError, match="fixed original"):
        Scenario.model_validate(scenario)


def test_scenario_resolves_patches_beside_file(tmp_path: Path) -> None:
    scenario_path = tmp_path / "scenario.toml"
    patch_dir = tmp_path / "patches"
    patch_dir.mkdir()
    scenario_path.write_text(SCENARIO_PATH.read_text())
    patch_path = patch_dir / "date-parser-offset.patch"
    patch_path.write_text("")

    scenario = load_scenario(scenario_path)

    assert scenario.patch_dir == patch_dir
    assert scenario.patch_path(scenario.poisons[0]) == patch_path
