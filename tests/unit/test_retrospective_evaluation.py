import pytest

from triage.retrospective_evaluation import DatasetError, validate


def case(**overrides):
    data = {"case_id": "case-1", "repository": "owner/repo", "issue_number": 1, "issue_url": "https://github.com/owner/repo/issues/1", "title": "Bounded title", "included_at": "2026-07-21", "historical_state": "closed", "investigation_id": "run-1", "terminal_status": "COMPLETED", "classification": "BEHAVIOR_GAP_CONFIRMED", "assertsFailure": True, "validation_reason": "Focused failure", "tracked_openai_cost": None, "tracked_openai_latency": None, "codex_wall_time": None, "external_support": "SUPPORTS_INTERPRETATION", "evaluator_note": "Merged fix is public evidence.", "sources": [{"url": "https://github.com/owner/repo/pull/2", "source_type": "MERGED_PR", "title": "Fix", "captured_at": "2026-07-21"}], "inclusion_rationale": "Source-backed", "limitations": "Small selected sample."}
    data.update(overrides); return data


def test_valid_mixed_dataset_preserves_all_external_assessment_categories():
    cases = [case(), case(case_id="case-2", issue_number=2, external_support="CONTRADICTS_INTERPRETATION"), case(case_id="case-3", issue_number=3, external_support="AMBIGUOUS"), case(case_id="case-4", issue_number=4, external_support="INSUFFICIENT_EXTERNAL_EVIDENCE")]
    result = validate({"schema_version": "retrospective-v1", "captured_at": "2026-07-21", "excluded_case_count": 2, "cases": cases}, {"run-1"})
    assert len(result["cases"]) == 4


def test_dataset_rejects_missing_sources_duplicate_cases_and_unknown_local_evidence():
    with pytest.raises(DatasetError, match="requires a public source"):
        validate({"schema_version": "retrospective-v1", "cases": [case(sources=[])]}, {"run-1"})
    with pytest.raises(DatasetError, match="unique"):
        validate({"schema_version": "retrospective-v1", "cases": [case(), case(case_id="case-2")]}, {"run-1"})
    with pytest.raises(DatasetError, match="unavailable local investigation"):
        validate({"schema_version": "retrospective-v1", "cases": [case(investigation_id="missing")]}, {"run-1"})
