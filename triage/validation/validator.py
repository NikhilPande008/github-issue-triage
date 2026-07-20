from triage.validation.diff import analyze_diff
from triage.validation.models import ValidationEvidence, ValidationResult
from triage.validation.pytest_parser import parse_pytest_output


class EvidenceValidator:
    """The sole gate allowed to declare a reproduced investigation."""

    def validate(self, evidence: ValidationEvidence) -> ValidationResult:
        diff = analyze_diff(evidence.git_diff_path.read_text(encoding="utf-8"))
        if not diff.changed_test_paths:
            return ValidationResult(False, "No new or modified executable pytest test was detected.", [], 0)

        report = parse_pytest_output(
            evidence.pytest_output_path.read_text(encoding="utf-8"), evidence.pytest_exit_code
        )
        if report.rejection_reason:
            return ValidationResult(False, report.rejection_reason, [], 0)
        changed = set(diff.changed_test_paths)
        failing = [path for path in report.assertion_failures if path in changed]
        if not report.assertion_failures:
            return ValidationResult(False, "No assertion failure detected.", [], 0)
        if not failing:
            return ValidationResult(
                False,
                "Assertion failures originated only from pre-existing tests.",
                [],
                len(report.assertion_failures),
            )
        return ValidationResult(
            True,
            "New failing assertion introduced in: " + ", ".join(str(path) for path in failing),
            failing,
            len(failing),
        )
