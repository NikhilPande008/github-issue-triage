"""Safe, deterministic presentation helpers for semantic-fidelity review."""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from triage.domain.enums import AssessmentJudgment, ConsensusState

MAX_EXCERPT_CHARS = 2_500
MAX_ASSERTION_LINES = 12
MAX_FAILURE_CHARS = 1_200
_SECRET = re.compile(r"(?i)(authorization|token|secret|password|api[_-]?key)\s*[:=]\s*[^\s,]+")
_ASSERTION = re.compile(r"\b(assert|raises|expect|matcher|match)\b", re.IGNORECASE)


def review_outcome(
    extraction_aligned: AssessmentJudgment,
    test_aligned: AssessmentJudgment,
    failure_supports_signal: AssessmentJudgment,
    public_comment_appropriate: AssessmentJudgment,
) -> str:
    """Derive a categorical review outcome; confidence is intentionally ignored."""
    answers = (extraction_aligned, test_aligned, failure_supports_signal, public_comment_appropriate)
    if any(answer == AssessmentJudgment.NO for answer in answers):
        return "MISALIGNED"
    if any(answer in {AssessmentJudgment.UNCERTAIN, AssessmentJudgment.NOT_ENOUGH_CONTEXT} for answer in answers):
        return "UNCLEAR"
    return "ALIGNED"


def consensus_label(state: str | None) -> str:
    return {
        ConsensusState.UNANIMOUSLY_ALIGNED.value: "Aligned",
        ConsensusState.REJECTED_ALIGNMENT.value: "Misaligned",
        ConsensusState.INSUFFICIENT_CONTEXT.value: "Unclear",
        ConsensusState.DISAGREED.value: "Reviewer disagreement",
        ConsensusState.PENDING_REVIEW.value: "Awaiting required review coverage",
        ConsensusState.UNAVAILABLE.value: "Review evidence unavailable",
    }.get(state or "", "Review evidence unavailable")


def _safe(value: object, limit: int = MAX_EXCERPT_CHARS) -> str | None:
    if not isinstance(value, str):
        return None
    return _SECRET.sub(r"\1: [redacted]", value.replace("\x00", ""))[:limit]


def bounded_claim(snapshot: dict[str, Any]) -> dict[str, object]:
    extraction = (snapshot.get("extraction") or {}).get("structured_output") or {}
    if not isinstance(extraction, dict):
        return {"available": False}
    missing = extraction.get("missing_info")
    return {
        "available": True,
        "summary": _safe(extraction.get("summary")),
        "expected_behavior": _safe(extraction.get("expected_behavior")),
        "actual_behavior": _safe(extraction.get("actual_behavior")),
        "missing_information": [_safe(item, 600) for item in missing[:12] if _safe(item, 600)] if isinstance(missing, list) else [],
    }


def diff_evidence(snapshot: dict[str, Any]) -> dict[str, object]:
    diff = snapshot.get("generated_test_diff") or {}
    excerpt = _safe(diff.get("content_excerpt")) if isinstance(diff, dict) else None
    if not excerpt:
        return {"available": False, "reason": "A bounded diff excerpt was not retained in the review packet."}
    paths = []
    for line in excerpt.splitlines():
        if line.startswith("+++ b/"):
            path = line[6:].strip()
            if path and path != "/dev/null" and path not in paths:
                paths.append(path)
    assertions = [line for line in excerpt.splitlines() if line.startswith("+") and not line.startswith("+++") and _ASSERTION.search(line)]
    return {
        "available": True,
        "changed_test_paths": paths[:12],
        "assertion_lines": assertions[:MAX_ASSERTION_LINES],
        "diff_excerpt": excerpt,
        "truncated": bool(diff.get("content_truncated")) if isinstance(diff, dict) else False,
    }


def junit_evidence(path: str | None) -> dict[str, object]:
    if not path:
        return {"available": False, "reason": "No structured JUnit artifact was retained."}
    try:
        root = ET.fromstring(Path(path).read_bytes())
    except (OSError, ET.ParseError):
        return {"available": False, "reason": "The structured JUnit artifact is unavailable."}
    failure = root.find(".//testcase[failure]")
    if failure is None:
        return {"available": False, "reason": "No failing testcase was found in the retained JUnit artifact."}
    node = failure.find("failure")
    return {
        "available": True,
        "testcase": _safe(f"{failure.get('classname', '')}::{failure.get('name', '')}", 600),
        "failure": _safe((node.text if node is not None else None) or (node.get("message") if node is not None else None), MAX_FAILURE_CHARS),
    }


def packet_semantic_evidence(snapshot: dict[str, Any]) -> dict[str, object]:
    junit = snapshot.get("structured_junit_result") or {}
    junit_path = junit.get("path") if isinstance(junit, dict) and junit.get("availability") == "AVAILABLE_AT_ISSUANCE" else None
    return {
        "claim": bounded_claim(snapshot),
        "generated_test": {
            "hypothesis": None,
            **diff_evidence(snapshot),
        },
        "junit": junit_evidence(junit_path),
        "validation_reason": _safe((snapshot.get("deterministic_validation") or {}).get("reason")) if isinstance(snapshot.get("deterministic_validation"), dict) else None,
    }
