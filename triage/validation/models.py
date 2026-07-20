from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ValidationEvidence:
    git_diff_path: Path
    pytest_output_path: Path
    pytest_exit_code: int


@dataclass(frozen=True)
class ValidationResult:
    asserts_failure: bool
    reason: str
    failing_test_paths: list[Path]
    assertion_count: int
