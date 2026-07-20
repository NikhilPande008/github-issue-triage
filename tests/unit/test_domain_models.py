from pathlib import Path

import pytest
from pydantic import ValidationError

from triage.domain.enums import Classification, InvestigationStatus
from triage.domain.models import InvestigationEvidence, IssueExtraction


def test_enum_values_are_exact() -> None:
    assert set(InvestigationStatus) == {
        InvestigationStatus.PENDING,
        InvestigationStatus.RUNNING,
        InvestigationStatus.COMPLETED,
        InvestigationStatus.FAILED,
    }
    assert set(Classification) == {
        Classification.REPRODUCED,
        Classification.NEEDS_INFO,
        Classification.WONT_REPRO,
        Classification.NOT_A_BUG,
        Classification.DUPLICATE,
    }
    with pytest.raises(ValueError):
        Classification("UNKNOWN")


def test_issue_extraction_contract() -> None:
    extraction = IssueExtraction(
        summary="request fails",
        steps_to_reproduce=["send request"],
        expected_behavior="succeeds",
        actual_behavior="fails",
        environment={"python": "3.12"},
        affected_area=None,
        repro_code=None,
        missing_info=[],
        confidence=0.8,
    )
    assert extraction.affected_area is None
    with pytest.raises(ValidationError):
        IssueExtraction(**{**extraction.model_dump(), "confidence": 1.1})


def test_evidence_contract() -> None:
    evidence = InvestigationEvidence(
        asserts_failure=True,
        git_diff_path=None,
        pytest_output_path=Path("artifacts/pytest_output.txt"),
        pytest_exit_code=1,
    )
    assert evidence.pytest_output_path == Path("artifacts/pytest_output.txt")
