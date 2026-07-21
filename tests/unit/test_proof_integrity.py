from pathlib import Path

import pytest

from triage.domain.models import IssueExtraction
from triage.validation.models import ValidationEvidence
from triage.validation.proof_integrity import analyze
from triage.validation.validator import EvidenceValidator


def extraction() -> IssueExtraction:
    return IssueExtraction(summary="Call client.fetch_record", steps_to_reproduce=[], expected_behavior="fetch_record raises ValueError", actual_behavior="fetch_record returns invalid value", environment={}, affected_area="Client.fetch_record", repro_code=None, missing_info=[], confidence=0.8)


@pytest.mark.parametrize("body", ["+    assert False", "+    raise AssertionError('bad')", "+    pytest.fail('bad')"])
def test_rejects_obvious_manufactured_failure(tmp_path, body) -> None:
    diff = tmp_path / "git.diff"; diff.write_text("diff --git a/tests/test_client.py b/tests/test_client.py\n+++ b/tests/test_client.py\n+def test_fetch_record():\n" + body + "\n", encoding="utf-8")
    report = analyze(diff, "pytest", extraction())
    assert report["result"] == "REJECTED_PROOF_PATTERN"


def test_rejects_production_and_fixture_changes_but_allows_normal_raises(tmp_path) -> None:
    bad = tmp_path / "bad.diff"; bad.write_text("diff --git a/src/client.py b/src/client.py\n+++ b/src/client.py\n+pass\ndiff --git a/tests/fixtures/value.json b/tests/fixtures/value.json\n+++ b/tests/fixtures/value.json\n+{}\n", encoding="utf-8")
    assert analyze(bad, "pytest", extraction())["result"] == "REJECTED_PROOF_PATTERN"
    good = tmp_path / "good.diff"; good.write_text("diff --git a/tests/test_client.py b/tests/test_client.py\n+++ b/tests/test_client.py\n+def test_fetch_record():\n+    with pytest.raises(ValueError):\n+        Client().fetch_record()\n", encoding="utf-8")
    assert analyze(good, "pytest", extraction())["result"] == "ACCEPTABLE"


def test_missing_anchor_is_review_flag_and_rejection_blocks_validator(tmp_path) -> None:
    diff = tmp_path / "diff"; diff.write_text("diff --git a/tests/test_other.py b/tests/test_other.py\n+++ b/tests/test_other.py\n+def test_other():\n+    value = helper()\n", encoding="utf-8")
    report = analyze(diff, "pytest", extraction())
    assert report["result"] == "REVIEW_FLAGGED"
    rejected = {"result": "REJECTED_PROOF_PATTERN", "findings": [{"severity": "REJECT", "explanation": "added assert False"}]}
    result = EvidenceValidator().validate(ValidationEvidence(git_diff_path=diff, pytest_output_path=Path("/missing"), pytest_exit_code=1, proof_integrity_report=rejected))
    assert not result.asserts_failure and "Rejected proof pattern" in result.reason
