from datetime import datetime, timezone

from triage.domain.enums import Classification, InvestigationStatus
from triage.persistence.models import Artifact, Investigation
from triage.validation.explainer import explain


def _artifact(investigation, kind, path):
    return Artifact(investigation_id=investigation.id, kind=kind, path=str(path), created_at=datetime.now(timezone.utc))


def test_modern_confirmed_explainer_requires_all_persisted_gates(tmp_path) -> None:
    investigation = Investigation(id="modern", repository="owner/repo", issue_number=1, test_runner="pytest", status=InvestigationStatus.COMPLETED, classification=Classification.BEHAVIOR_GAP_CONFIRMED, asserts_failure=True)
    diff = tmp_path / "git.diff"; diff.write_text("diff --git a/tests/test_target.py b/tests/test_target.py\n+++ b/tests/test_target.py\n+def test_target():\n+    assert False\n", encoding="utf-8")
    junit = tmp_path / "junit.xml"; junit.write_text('<testsuite tests="1" failures="1" errors="0" skipped="0"><testcase classname="tests.test_target" name="test_target"><failure>assertion</failure></testcase></testsuite>', encoding="utf-8")
    manifests = []
    for number in (1, 2):
        path = tmp_path / f"manifest-{number}.json"; path.write_text('{"confirmation_runs": 2, "execution_failure_reason": null}', encoding="utf-8"); manifests.append(_artifact(investigation, "reproducibility_manifest", path))
    proof = tmp_path / "proof.json"; proof.write_text('{"result": "ACCEPTABLE", "findings": []}', encoding="utf-8")
    selection = tmp_path / "selection.json"; selection.write_text('{"precision": "EXACT", "targets": ["tests/test_target.py::test_target"]}', encoding="utf-8")
    result = explain(investigation, [_artifact(investigation, "git_diff", diff), _artifact(investigation, "focused_test_selection", selection), _artifact(investigation, "structured_test_results_junit", junit), _artifact(investigation, "structured_test_results_junit", junit), _artifact(investigation, "proof_integrity_report", proof), *manifests])
    assert result["conclusion"] == "BEHAVIOR_GAP_CONFIRMED"
    assert [item["status"] for item in result["checks"]] == ["PASS"] * 7


def test_rejected_and_legacy_explanations_do_not_invent_modern_evidence(tmp_path) -> None:
    investigation = Investigation(id="legacy", repository="owner/repo", issue_number=2, test_runner="pytest", status=InvestigationStatus.COMPLETED, classification=Classification.BEHAVIOR_GAP_CONFIRMED, asserts_failure=True)
    result = explain(investigation, [])
    assert result["conclusion"] == "BEHAVIOR_GAP_NOT_ESTABLISHED"
    assert result["checks"][0]["status"] == "UNAVAILABLE"
    assert result["checks"][1]["status"] == "UNAVAILABLE"
    assert result["checks"][-2]["status"] == "NOT_APPLICABLE"
    assert result["checks"][-1]["status"] == "UNAVAILABLE"
    diff = tmp_path / "diff"; diff.write_text("diff --git a/src/app.py b/src/app.py\n+++ b/src/app.py\n+print('x')\n", encoding="utf-8")
    rejected = explain(Investigation(id="rejected", repository="owner/repo", issue_number=3, test_runner="pytest", status=InvestigationStatus.COMPLETED_NO_GAP, classification=Classification.NEEDS_INFO, asserts_failure=False), [_artifact(investigation, "git_diff", diff)])
    assert rejected["checks"][0]["status"] == "FAIL"
