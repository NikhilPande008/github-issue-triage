import json
from pathlib import Path

from triage.classification.models import ClassificationEvidence

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "classification.md"


def load_system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def render_evidence_prompt(evidence: ClassificationEvidence) -> str:
    """Render only execution evidence; no issue or investigation context is accepted."""
    pytest_output = evidence.pytest_output_path.read_text(encoding="utf-8")
    git_diff = (
        evidence.git_diff_path.read_text(encoding="utf-8")
        if evidence.git_diff_path is not None and evidence.git_diff_path.exists()
        else None
    )
    payload = {
        "asserts_failure": evidence.asserts_failure,
        "validation_reason": evidence.validation_reason,
        "pytest_exit_code": evidence.pytest_exit_code,
        "pytest_output": pytest_output,
        "git_diff": git_diff,
        "duplicate_evidence_available": False,
    }
    return json.dumps(payload, indent=2)
