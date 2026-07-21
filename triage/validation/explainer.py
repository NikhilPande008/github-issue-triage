"""Read-only reconstruction of deterministic validation gates from persisted evidence."""
from __future__ import annotations

import json
from pathlib import Path

from triage.persistence.models import Artifact, Investigation
from triage.runners import select_runner
from triage.validation.diff import analyze_diff
from triage.validation.junit import matches_selected_node, parse_junit_xml


def _check(identifier: str, label: str, status: str, explanation: str, artifact: Artifact | None = None) -> dict[str, object]:
    return {"id": identifier, "label": label, "status": status, "explanation": explanation[:1_200], "artifact_kind": artifact.kind if artifact else None}


def _latest(artifacts: list[Artifact], kind: str) -> Artifact | None:
    choices = [item for item in artifacts if item.kind == kind]
    return choices[-1] if choices else None


def _manifest(artifact: Artifact | None) -> dict[str, object] | None:
    if artifact is None:
        return None
    try:
        value = json.loads(Path(artifact.path).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _proof_report(artifact: Artifact | None) -> dict[str, object] | None:
    return _manifest(artifact)


def explain(investigation: Investigation, artifacts: list[Artifact]) -> dict[str, object]:
    """Return gate statuses without rerunning a test or interpreting terminal text."""
    diff_artifact = _latest(artifacts, "git_diff")
    junit_artifacts = [item for item in artifacts if item.kind == "structured_test_results_junit"]
    junit_artifact = junit_artifacts[-1] if junit_artifacts else None
    manifests = [item for item in artifacts if item.kind == "reproducibility_manifest"]
    proof_artifact = _latest(artifacts, "proof_integrity_report")
    selection_artifact = _latest(artifacts, "focused_test_selection")
    manifest = _manifest(manifests[-1] if manifests else None)
    selection = _manifest(selection_artifact)
    selected_targets = selection.get("targets") if isinstance(selection, dict) and isinstance(selection.get("targets"), list) else None
    if selection is None:
        focused_selection = _check("exact_focused_test_selection", "Exact focused-test selection", "UNAVAILABLE", "No persisted focused-test selection is available; historical evidence is not inferred.")
    elif selection.get("precision") == "EXACT":
        focused_selection = _check("exact_focused_test_selection", "Exact focused-test selection", "PASS", "Exact selected target(s): " + ", ".join(str(item) for item in selection.get("targets", [])), selection_artifact)
    else:
        focused_selection = _check("exact_focused_test_selection", "Exact focused-test selection", "FAIL", f"Selection precision is {selection.get('precision', 'UNAVAILABLE')}: {selection.get('reason', 'no exact target was recorded.')}", selection_artifact)
    changed_paths: set[Path] = set()
    runner = None
    if diff_artifact is None:
        changed = _check("changed_executable_test", "Changed executable test", "UNAVAILABLE", "No persisted git diff is available to identify a changed focused test.")
    else:
        try:
            runner = select_runner(investigation.test_runner)
            changed_paths = set(analyze_diff(Path(diff_artifact.path).read_text(encoding="utf-8"), runner.is_test_path).changed_test_paths)
            changed = _check("changed_executable_test", "Changed executable test", "PASS" if changed_paths else "FAIL", f"Changed executable {runner.id} test path(s): {', '.join(str(path) for path in sorted(changed_paths))}." if changed_paths else f"No new or modified executable {runner.id} test was detected.", diff_artifact)
        except OSError:
            changed = _check("changed_executable_test", "Changed executable test", "UNAVAILABLE", "The persisted git diff cannot be read.", diff_artifact)
        except ValueError:
            changed = _check("changed_executable_test", "Changed executable test", "UNAVAILABLE", "The stored runner is not available for deterministic diff analysis.", diff_artifact)

    report = None
    if junit_artifact is None:
        junit = _check("structured_junit_result", "Valid structured JUnit result", "UNAVAILABLE", "Historical evidence has no persisted structured JUnit artifact; it was not JUnit-validated.")
        failure = _check("explicit_failure", "Explicit assertion failure", "UNAVAILABLE", "No structured JUnit result is available to establish an explicit focused failure.")
        clean = _check("clean_execution", "No setup, error, or timeout", "UNAVAILABLE", "Execution cleanliness cannot be determined safely without structured test evidence.")
    else:
        report = parse_junit_xml(Path(junit_artifact.path), investigation.test_runner or "pytest", selected_targets)
        if report.rejection_reason:
            junit = _check("structured_junit_result", "Valid structured JUnit result", "FAIL", report.rejection_reason, junit_artifact)
            failure = _check("explicit_failure", "Explicit assertion failure", "UNAVAILABLE", "The JUnit result was rejected before focused-failure matching.", junit_artifact)
            clean = _check("clean_execution", "No setup, error, or timeout", "FAIL", report.rejection_reason, junit_artifact)
        elif report.total == 0:
            junit = _check("structured_junit_result", "Valid structured JUnit result", "FAIL", "Structured test results report zero executed tests.", junit_artifact)
            failure = _check("explicit_failure", "Explicit assertion failure", "FAIL", "Structured test results report zero executed tests.", junit_artifact)
            clean = _check("clean_execution", "No setup, error, or timeout", "UNAVAILABLE", "No executed structured testcase is available to assess execution cleanliness.", junit_artifact)
        elif report.errors:
            junit = _check("structured_junit_result", "Valid structured JUnit result", "FAIL", "Structured test results contain infrastructure/error test cases.", junit_artifact)
            failure = _check("explicit_failure", "Explicit assertion failure", "FAIL", "JUnit errors cannot serve as explicit assertion-failure evidence.", junit_artifact)
            clean = _check("clean_execution", "No setup, error, or timeout", "FAIL", "Structured test results contain infrastructure/error test cases.", junit_artifact)
        else:
            junit = _check("structured_junit_result", "Valid structured JUnit result", "PASS", f"Valid JUnit recorded {report.total} testcase(s) with {report.failed} failure(s).", junit_artifact)
            failed_paths = {case.path for case in report.cases if case.outcome == "failure" and case.path is not None}
            scoped = failed_paths & changed_paths
            scope_matches = selected_targets is None or all(matches_selected_node(case.path, case.name, selected_targets) for case in report.cases if case.outcome == "failure")
            if not report.failed:
                failure = _check("explicit_failure", "Explicit assertion failure", "FAIL", "Structured test results contain no test failures.", junit_artifact)
            elif not failed_paths:
                failure = _check("explicit_failure", "Explicit assertion failure", "FAIL", "Structured failures did not identify a test file.", junit_artifact)
            elif not changed_paths:
                failure = _check("explicit_failure", "Explicit assertion failure", "FAIL", "No changed executable test is available for focused-failure matching.", junit_artifact)
            elif not scoped:
                failure = _check("explicit_failure", "Explicit assertion failure", "FAIL", "Assertion failures originated only from pre-existing tests.", junit_artifact)
            elif not scope_matches:
                failure = _check("explicit_failure", "Explicit assertion failure", "FAIL", "Structured failures did not match the persisted exact selected test target.", junit_artifact)
            else:
                failure = _check("explicit_failure", "Explicit assertion failure", "PASS", "A structured failure belongs to a changed focused test: " + ", ".join(str(path) for path in sorted(scoped)), junit_artifact)
            reason = str(manifest.get("execution_failure_reason") or "") if manifest else ""
            clean = _check("clean_execution", "No setup, error, or timeout", "FAIL" if reason else "PASS", reason or "No structured JUnit errors or persisted execution-failure reason were recorded.", junit_artifact)

    if not manifests:
        confirmation = _check("confirmation_match", "Confirmation rerun matches", "NOT_APPLICABLE" if junit_artifact is None else "UNAVAILABLE", "Historical evidence predates persisted confirmation support." if junit_artifact is None else "No persisted confirmation manifest is available; confirmation cannot be assumed.")
    elif "FLAKY_OR_INCONCLUSIVE" in (investigation.validation_reason or ""):
        confirmation = _check("confirmation_match", "Confirmation rerun matches", "FAIL", "Persisted deterministic validation marked confirmation evidence flaky or inconclusive.", manifests[-1])
    else:
        required = max(int((_manifest(item) or {}).get("confirmation_runs", 1) or 1) for item in manifests)
        confirmation_reports = [parse_junit_xml(Path(item.path), investigation.test_runner or "pytest", selected_targets) for item in junit_artifacts]
        stable_reports = [report for report in confirmation_reports if not report.rejection_reason and report.total and not report.errors and report.failed]
        if investigation.asserts_failure and len(manifests) >= required and len(stable_reports) >= required:
            confirmation = _check("confirmation_match", "Confirmation rerun matches", "PASS", f"{len(stable_reports)} persisted structured confirmation result(s) meet the recorded requirement of {required}.", manifests[-1])
        elif investigation.asserts_failure and len(manifests) >= required and len(junit_artifacts) >= required:
            confirmation = _check("confirmation_match", "Confirmation rerun matches", "FAIL", "At least one persisted confirmation JUnit result is malformed, error-containing, empty, or lacks an explicit failure.", manifests[-1])
        else:
            confirmation = _check("confirmation_match", "Confirmation rerun matches", "UNAVAILABLE", f"Persisted confirmation evidence is incomplete: {len(manifests)} manifest(s) and {len(junit_artifacts)} structured result(s) are available; the recorded requirement is {required}.", manifests[-1])
    proof = _proof_report(proof_artifact)
    if proof is None:
        integrity = _check("proof_pattern_integrity", "Proof-pattern integrity", "UNAVAILABLE", "No persisted proof-integrity report is available; historical evidence was not analyzed.")
    elif proof.get("result") == "REJECTED_PROOF_PATTERN":
        finding = next((item for item in proof.get("findings", []) if item.get("severity") == "REJECT"), {})
        integrity = _check("proof_pattern_integrity", "Proof-pattern integrity", "FAIL", "Rejected proof pattern: " + str(finding.get("explanation", "generated proof was rejected.")), proof_artifact)
    elif proof.get("result") == "REVIEW_FLAGGED":
        finding = next((item for item in proof.get("findings", []) if item.get("severity") == "REVIEW_FLAG"), {})
        integrity = _check("proof_pattern_integrity", "Proof-pattern integrity", "UNAVAILABLE", "Review flag: " + str(finding.get("explanation", "human semantic review is required.")), proof_artifact)
    else:
        integrity = _check("proof_pattern_integrity", "Proof-pattern integrity", "PASS", "No manufactured or unrelated proof pattern was detected.", proof_artifact)
    core_checks = [changed, focused_selection, junit, failure, clean, confirmation]
    checks = [*core_checks, integrity]
    # Proof integrity was introduced after historical confirmations. It is a
    # required live gate, but its absence must not rewrite persisted verdicts.
    established = investigation.asserts_failure and all(item["status"] == "PASS" for item in core_checks)
    return {"version": "deterministic-validator-v1", "conclusion": "BEHAVIOR_GAP_CONFIRMED" if established else "BEHAVIOR_GAP_NOT_ESTABLISHED", "checks": checks}
