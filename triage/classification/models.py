from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ClassificationEvidence:
    """The complete input boundary for evidence-based classification."""

    asserts_failure: bool
    validation_reason: str
    pytest_exit_code: int
    pytest_output_path: Path
    git_diff_path: Path | None
