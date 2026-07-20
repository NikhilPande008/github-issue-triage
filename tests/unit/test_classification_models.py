from dataclasses import fields
from inspect import signature
from pathlib import Path

from triage.classification.models import ClassificationEvidence
from triage.classification.service import ClassificationService
from triage.domain.enums import Classification


def test_classification_evidence_has_only_the_execution_evidence_contract() -> None:
    assert [field.name for field in fields(ClassificationEvidence)] == [
        "asserts_failure",
        "validation_reason",
        "pytest_exit_code",
        "pytest_output_path",
        "git_diff_path",
    ]
    assert ClassificationEvidence.__annotations__["pytest_output_path"] is Path


def test_classify_signature_accepts_only_classification_evidence() -> None:
    parameters = list(signature(ClassificationService.classify).parameters)
    assert parameters == ["self", "evidence"]
    assert signature(ClassificationService.classify).return_annotation is Classification
