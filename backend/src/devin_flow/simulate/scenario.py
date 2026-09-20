import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

Phase = Literal["original", "filler", "duplicate"]
ExpectedOutcome = Literal["fixed", "duplicate", "not_a_bug", "not_reproducible"]
DEFAULT_PATCH_DIR = Path(__file__).resolve().parent / "patches"


class Poison(BaseModel):
    id: str = Field(min_length=1)
    patch: str = Field(min_length=1, pattern=r"^[^/\\]+\.patch$")
    failing_test: str = Field(min_length=1)


class Issue(BaseModel):
    id: str = Field(min_length=1)
    phase: Phase
    expected_outcome: ExpectedOutcome
    duplicate_of: str | None = None
    title: str = Field(min_length=1)
    body: str = Field(min_length=1)


class Scenario(BaseModel):
    repository: str = Field(min_length=1)
    default_branch: str = Field(min_length=1)
    baseline: str = Field(pattern=r"^[0-9a-f]{40}$")
    window_seconds: int = Field(gt=0)
    poisons: list[Poison]
    issues: list[Issue]
    patch_dir: Path = DEFAULT_PATCH_DIR

    def patch_path(self, poison: Poison) -> Path:
        return self.patch_dir / poison.patch

    @model_validator(mode="after")
    def validate_consistency(self) -> "Scenario":
        poison_ids = [poison.id for poison in self.poisons]
        issue_ids = [issue.id for issue in self.issues]
        if len(set(poison_ids)) != len(poison_ids):
            raise ValueError("poison ids must be unique")
        if len(set(issue_ids)) != len(issue_ids):
            raise ValueError("issue ids must be unique")
        phase_order = {"original": 0, "filler": 1, "duplicate": 2}
        phases = [phase_order[issue.phase] for issue in self.issues]
        if any(left > right for left, right in zip(phases, phases[1:], strict=False)):
            raise ValueError("issues must be ordered original, filler, duplicate")
        original_ids = {issue.id for issue in self.issues if issue.phase == "original"}
        for issue in self.issues:
            if issue.phase == "duplicate":
                if issue.duplicate_of is None:
                    raise ValueError("duplicate issues require duplicate_of")
                if issue.duplicate_of not in original_ids:
                    raise ValueError("duplicate_of must reference an original issue")
            elif issue.duplicate_of is not None:
                raise ValueError("duplicate_of is only valid for duplicate issues")
        poison_by_id = set(poison_ids)
        fixed_original_ids = {
            issue.id
            for issue in self.issues
            if issue.phase == "original" and issue.expected_outcome == "fixed"
        }
        for issue in self.issues:
            if (
                issue.phase == "original"
                and issue.expected_outcome == "fixed"
                and issue.id not in poison_by_id
            ):
                raise ValueError("fixed originals require a poison with the same id")
        if poison_by_id - fixed_original_ids:
            raise ValueError("poisons require fixed original issues")
        return self


def load_scenario(path: Path) -> Scenario:
    with path.open("rb") as file:
        scenario = Scenario.model_validate(tomllib.load(file))
    scenario.patch_dir = path.resolve().parent / "patches"
    return scenario
