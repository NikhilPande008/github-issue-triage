from triage.domain.models import IssueExtraction
from triage.core.prompt_evidence import MAX_TERMINAL_EVIDENCE_CHARS, TRUNCATION_NOTICE
from triage.investigation.prompts import render_codex_prompt


def test_codex_prompt_includes_revision_and_extraction() -> None:
    extraction = IssueExtraction(
        summary="A request fails", steps_to_reproduce=[], expected_behavior=None, actual_behavior=None,
        environment={}, affected_area=None, repro_code=None, missing_info=[], confidence=0.5,
    )
    prompt = render_codex_prompt(extraction, 2, "The prior test passed.", "previous terminal output")

    assert "Codex investigation prompt v1" in prompt
    assert "The prior test passed." in prompt
    assert "previous terminal output" in prompt
    assert '"summary": "A request fails"' in prompt


def test_codex_prompt_bounds_prior_terminal_evidence_to_its_tail() -> None:
    extraction = IssueExtraction(
        summary="A request fails", steps_to_reproduce=[], expected_behavior=None, actual_behavior=None,
        environment={}, affected_area=None, repro_code=None, missing_info=[], confidence=0.5,
    )
    final_summary = "FAILED tests/test_api.py::test_api\n1 failed, 3 passed in 0.1s"
    previous_evidence = "discard-this\n" + ("x" * MAX_TERMINAL_EVIDENCE_CHARS) + final_summary

    prompt = render_codex_prompt(extraction, 2, "Retry.", previous_evidence)

    assert TRUNCATION_NOTICE in prompt
    assert "discard-this" not in prompt
    assert final_summary in prompt
