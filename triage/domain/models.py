from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class IssueExtraction(BaseModel):
    """Validated, source-bound reproduction information from one issue."""

    model_config = ConfigDict(extra="forbid")

    summary: str | None
    steps_to_reproduce: list[str]
    expected_behavior: str | None
    actual_behavior: str | None
    environment: dict[str, str]
    affected_area: str | None
    repro_code: str | None
    missing_info: list[str]
    confidence: float = Field(ge=0, le=1)


class InvestigationEvidence(BaseModel):
    asserts_failure: bool
    git_diff_path: Path | None
    pytest_output_path: Path
    pytest_exit_code: int
