from triage.domain.models import IssueExtraction
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
