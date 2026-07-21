from triage.validation.diff import analyze_diff
from triage.validation.junit import matches_selected_node, parse_junit_xml
from triage.validation.models import ValidationEvidence, ValidationResult


class EvidenceValidator:
    """The sole gate allowed to confirm a tested behavior gap."""

    def __init__(self, runner=None):
        self.runner = runner

    def validate(self, evidence: ValidationEvidence) -> ValidationResult:
        if evidence.proof_integrity_report and evidence.proof_integrity_report.get("result") == "REJECTED_PROOF_PATTERN":
            finding = next((item for item in evidence.proof_integrity_report.get("findings", []) if item.get("severity") == "REJECT"), None)
            return ValidationResult(False, "Rejected proof pattern: " + str((finding or {}).get("explanation", "generated proof is invalid.")), [], 0)
        if self.runner is None:
            from triage.runners import select_runner
            runner = select_runner(evidence.runner_id)
        else:
            runner = self.runner
        diff = analyze_diff(evidence.git_diff_path.read_text(encoding="utf-8"), runner.is_test_path)
        if not diff.changed_test_paths:
            return ValidationResult(False, f"No new or modified executable {runner.id} test was detected.", [], 0)

        selection = evidence.focused_test_selection
        if evidence.focused_test_selection_required and (selection is None or selection.get("precision") != "EXACT"):
            return ValidationResult(False, "Exact focused-test selection is required for structured confirmation.", [], 0)
        if selection is not None and selection.get("precision") != "EXACT":
            return ValidationResult(False, "Exact focused-test selection is required for structured confirmation.", [], 0)

        if evidence.execution_failure_reason:
            return ValidationResult(False, evidence.execution_failure_reason, [], 0)
        if evidence.structured_results_path is None:
            return ValidationResult(False, "Structured test results are required for validation.", [], 0)
        targets = selection.get("targets") if isinstance(selection, dict) else None
        report = parse_junit_xml(evidence.structured_results_path, runner.id, targets if isinstance(targets, list) else None)
        if report.rejection_reason:
            return ValidationResult(False, report.rejection_reason, [], 0)
        if report.total == 0:
            return ValidationResult(False, "Structured test results report zero executed tests.", [], 0)
        if report.errors:
            return ValidationResult(False, "Structured test results contain infrastructure/error test cases.", [], 0)
        if report.failed == 0:
            return ValidationResult(False, "Structured test results contain no test failures.", [], 0)
        changed = set(diff.changed_test_paths)
        failed_paths = [case.path for case in report.cases if case.outcome == "failure" and case.path is not None]
        failing = [path for path in failed_paths if path in changed]
        if not failed_paths:
            return ValidationResult(False, "Structured failures did not identify a test file.", [], 0)
        if not failing:
            return ValidationResult(
                False,
                "Assertion failures originated only from pre-existing tests.",
                [],
                len(failed_paths),
            )
        if selection is not None:
            if not isinstance(targets, list) or not targets or not all(matches_selected_node(case.path, case.name, targets) for case in report.cases if case.outcome == "failure"):
                return ValidationResult(False, "Structured failures could not be matched safely to the exact selected test target.", [], len(failed_paths))
        return ValidationResult(
            True,
            "New failing assertion introduced in: " + ", ".join(str(path) for path in failing),
            failing,
            len(failing),
        )
