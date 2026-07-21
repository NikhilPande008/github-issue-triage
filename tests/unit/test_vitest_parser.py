import pytest

from triage.validation.vitest_parser import parse_vitest_output
from triage.validation.models import ValidationEvidence
from triage.validation.validator import EvidenceValidator


def test_vitest_completed_assertion_failure_is_accepted() -> None:
    report = parse_vitest_output(" FAIL  tests/widget.spec.ts\nTests  1 failed | 2 passed", 1)
    assert report.completed is True
    assert str(report.assertion_failures[0]) == "tests/widget.spec.ts"


@pytest.mark.parametrize("output,code,reason", [
    ("Tests  2 passed", 0, "test failure summary"),
    ("Error: Failed to resolve import 'x'", 1, "module-resolution"),
    ("No test files found", 1, "discovery"),
    ("Test timed out", 124, "timed out"),
    ("not vitest output", 1, "test failure summary"),
])
def test_vitest_rejects_non_evidence_outputs(output, code, reason) -> None:
    report = parse_vitest_output(output, code)
    assert report.completed is False
    assert reason in (report.rejection_reason or "")


def test_vitest_validator_requires_a_changed_failing_test(tmp_path) -> None:
    diff = tmp_path / "change.diff"
    output = tmp_path / "vitest.txt"
    diff.write_text("diff --git a/tests/widget.spec.ts b/tests/widget.spec.ts\n+++ b/tests/widget.spec.ts\n+expect(value).toBe(2)\n")
    output.write_text(" FAIL  tests/widget.spec.ts\nTests  1 failed", encoding="utf-8")
    junit = tmp_path / "junit.xml"
    junit.write_text('<testsuite tests="1" failures="1" errors="0" skipped="0"><testcase file="tests/widget.spec.ts" name="widget"><failure/></testcase></testsuite>', encoding="utf-8")
    result = EvidenceValidator().validate(ValidationEvidence(diff, output, 1, runner_id="vitest", structured_results_path=junit))
    assert result.asserts_failure is True
