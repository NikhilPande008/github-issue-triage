from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ValidationEvidence:
    git_diff_path: Path
    pytest_output_path: Path
    pytest_exit_code: int
    runner_id: str = "pytest"
    structured_results_path: Path | None = None
    execution_failure_reason: str | None = None
    reliability_status: str = "NOT_CONFIRMED"
    proof_integrity_report: dict | None = None
    focused_test_selection: dict | None = None
    focused_test_selection_required: bool = False

    @property
    def test_output_path(self) -> Path:
        return self.pytest_output_path

    @property
    def test_exit_code(self) -> int:
        return self.pytest_exit_code


@dataclass(frozen=True)
class ValidationResult:
    asserts_failure: bool
    reason: str
    failing_test_paths: list[Path]
    assertion_count: int
