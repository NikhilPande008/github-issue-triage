from triage.classification.models import ClassificationEvidence
from triage.classification.prompts import load_system_prompt, render_evidence_prompt


def test_classification_prompt_is_version_controlled_and_evidence_only(tmp_path) -> None:
    pytest_output = tmp_path / "pytest_output.txt"
    pytest_output.write_text("collected 1 item\ntests/test_api.py F\n", encoding="utf-8")
    evidence = ClassificationEvidence(False, "No assertion failure detected.", 1, pytest_output, None)

    prompt = render_evidence_prompt(evidence)

    assert "No assertion failure detected." in prompt
    assert "tests/test_api.py F" in prompt
    assert "duplicate_evidence_available" in prompt
    assert "asserts_failure" in load_system_prompt()
