import json
from pathlib import Path

from triage.core.prompt_evidence import tail_terminal_evidence
from triage.domain.models import IssueExtraction

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "codex_investigation.md"


def render_codex_prompt(
    extraction: IssueExtraction,
    attempt_number: int,
    revision_reason: str | None,
    previous_evidence: str,
) -> str:
    template = PROMPT_PATH.read_text(encoding="utf-8")
    return (
        template.replace("{{extraction_json}}", json.dumps(extraction.model_dump(mode="json"), indent=2))
        .replace("{{attempt_number}}", str(attempt_number))
        .replace("{{revision_reason}}", revision_reason or "None; this is the first attempt.")
        .replace(
            "{{previous_evidence}}",
            tail_terminal_evidence(previous_evidence) if previous_evidence else "None; this is the first attempt.",
        )
    )
