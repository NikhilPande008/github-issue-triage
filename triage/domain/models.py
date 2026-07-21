from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class IssueExtraction(BaseModel):
    """Validated, source-bound executable behavior specification from one issue."""

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
    runner_id: str = "pytest"
    structured_results_path: Path | None = None
    execution_failure_reason: str | None = None
    reproducibility_manifest_path: Path | None = None
    focused_test_selection_path: Path | None = None
    reliability_status: str = "NOT_CONFIRMED"

    @property
    def test_output_path(self) -> Path:
        """Runner-neutral alias; legacy pytest field remains API-compatible."""
        return self.pytest_output_path

    @property
    def test_exit_code(self) -> int:
        return self.pytest_exit_code
