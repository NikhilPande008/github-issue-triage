import json

from triage.classification.models import ClassificationEvidence
from triage.core.prompt_evidence import MAX_TERMINAL_EVIDENCE_CHARS, TRUNCATION_NOTICE
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


def test_classification_prompt_bounds_pytest_output_to_its_tail(tmp_path) -> None:
    pytest_output = tmp_path / "pytest_output.txt"
    final_summary = "FAILED tests/test_api.py::test_api\n1 failed, 3 passed in 0.1s"
    pytest_output.write_text("discard-this\n" + ("x" * MAX_TERMINAL_EVIDENCE_CHARS) + final_summary, encoding="utf-8")
    evidence = ClassificationEvidence(False, "No assertion failure detected.", 1, pytest_output, None)

    payload = json.loads(render_evidence_prompt(evidence))

    assert payload["pytest_output"].startswith(TRUNCATION_NOTICE)
    assert "discard-this" not in payload["pytest_output"]
    assert payload["pytest_output"].endswith(final_summary)
