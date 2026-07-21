"""Safe, bounded renderers for the small set of permitted public comments."""

import re

from triage.domain.enums import Classification
from triage.persistence.models import Investigation

MARKER_PREFIX = "<!-- github-issue-triage:"
MAX_COMMENT_LENGTH = 6000


def _clean(value: str | None, limit: int = 1200) -> str:
    value = (value or "").replace("\x00", "").replace("```", "'''")
    value = re.sub(r"(?i)(authorization|token|secret|password)\s*[:=]\s*\S+", r"\1: [redacted]", value)
    value = " ".join(value.split())
    return value[:limit]


def render_comment(
    investigation: Investigation, delivery_id: str, extraction: dict | None = None, evidence_excerpt: str | None = None
) -> str | None:
    marker = f"{MARKER_PREFIX}{delivery_id} -->"
    if investigation.classification == Classification.BEHAVIOR_GAP_CONFIRMED:
        reason = _clean(investigation.validation_reason, 1000)
        excerpt = _clean(evidence_excerpt, 900)
        evidence = f"\n\n```diff\n{excerpt}\n```" if excerpt else "\n\nEvidence is available in the maintainer triage record."
        body = (
            "### Triage result: Behavior gap confirmed\n\n"
            "A focused test for the reported behavior failed on the current code. "
            "This confirms a behavior gap; it does not determine whether this is a bug or regression.\n\n"
            f"Deterministic validation: {reason}"
            f"{evidence}\n\n"
            f"{marker}"
        )
    elif investigation.classification == Classification.NEEDS_INFO:
        missing = extraction.get("missing_info", []) if extraction else []
        items = [f"- {_clean(str(item), 300)}" for item in missing[:10] if _clean(str(item), 300)]
        body = "### Information requested\n\nPlease provide the following details so maintainers can investigate:\n"
        body += "\n".join(items) if items else "- A minimal reproduction and relevant environment details."
        body += f"\n\n{marker}"
    else:
        return None
    return body[:MAX_COMMENT_LENGTH]
