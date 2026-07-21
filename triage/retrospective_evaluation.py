"""Bounded validator for independently curated retrospective evidence."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

SCHEMA_VERSION = "retrospective-v1"
ASSESSMENTS = {"SUPPORTS_INTERPRETATION", "CONTRADICTS_INTERPRETATION", "AMBIGUOUS", "INSUFFICIENT_EXTERNAL_EVIDENCE"}
SOURCE_TYPES = {"MERGED_PR", "MAINTAINER_COMMENT", "ISSUE_CLOSURE", "RELEASE_NOTE", "OTHER"}
MAX_TEXT = 500


class DatasetError(ValueError): pass


def load(path: Path, investigation_ids: set[str]) -> dict:
    try: data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error: raise DatasetError("Curated evaluation dataset could not be read.") from error
    return validate(data, investigation_ids)


def validate(data: object, investigation_ids: set[str]) -> dict:
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION: raise DatasetError("Curated evaluation dataset has an unsupported schema version.")
    cases = data.get("cases")
    if not isinstance(cases, list): raise DatasetError("Curated evaluation dataset cases must be a list.")
    case_ids: set[str] = set(); issues: set[tuple[str, int]] = set(); cleaned = []
    for case in cases:
        if not isinstance(case, dict): raise DatasetError("Curated evaluation dataset contains an invalid case.")
        required = {"case_id", "repository", "issue_number", "issue_url", "title", "included_at", "historical_state", "investigation_id", "terminal_status", "classification", "assertsFailure", "validation_reason", "tracked_openai_cost", "tracked_openai_latency", "codex_wall_time", "external_support", "evaluator_note", "sources", "inclusion_rationale", "limitations"}
        if not required.issubset(case): raise DatasetError("Curated evaluation case is missing required bounded fields.")
        case_id, repository, number = case["case_id"], case["repository"], case["issue_number"]
        if not isinstance(case_id, str) or not case_id or case_id in case_ids or not isinstance(repository, str) or not isinstance(number, int) or (repository, number) in issues: raise DatasetError("Curated evaluation case IDs and repository/issues must be unique.")
        case_ids.add(case_id); issues.add((repository, number))
        for key in ("case_id", "repository", "title", "included_at", "historical_state", "terminal_status", "classification", "validation_reason", "evaluator_note", "inclusion_rationale", "limitations"):
            value = case[key]
            if value is not None and (not isinstance(value, str) or len(value) > MAX_TEXT or "/../" in value or "..\\" in value): raise DatasetError("Curated evaluation contains an unsafe or unbounded text field.")
        _url(case["issue_url"])
        if case["external_support"] not in ASSESSMENTS: raise DatasetError("Curated evaluation has an invalid external-support assessment.")
        if not isinstance(case["sources"], list) or not case["sources"]: raise DatasetError("Every curated evaluation case requires a public source.")
        for source in case["sources"]:
            if not isinstance(source, dict) or source.get("source_type") not in SOURCE_TYPES: raise DatasetError("Curated evaluation has an invalid source type.")
            _url(source.get("url"))
            for key in ("title", "captured_at"):
                if not isinstance(source.get(key), str) or len(source[key]) > MAX_TEXT: raise DatasetError("Curated evaluation source metadata is invalid.")
        investigation_id = case["investigation_id"]
        if investigation_id is not None and (not isinstance(investigation_id, str) or investigation_id not in investigation_ids): raise DatasetError("Curated evaluation references an unavailable local investigation.")
        cleaned.append(case)
    excluded = data.get("excluded_case_count", 0)
    if not isinstance(excluded, int) or excluded < 0: raise DatasetError("Curated evaluation exclusion count is invalid.")
    captured = data.get("captured_at")
    if captured is not None and (not isinstance(captured, str) or len(captured) > MAX_TEXT): raise DatasetError("Curated evaluation capture date is invalid.")
    limitations = data.get("limitations", [])
    if not isinstance(limitations, list) or any(not isinstance(item, str) or len(item) > MAX_TEXT for item in limitations): raise DatasetError("Curated evaluation limitations are invalid.")
    exclusion_rationale = data.get("exclusion_rationale")
    if exclusion_rationale is not None and (not isinstance(exclusion_rationale, str) or len(exclusion_rationale) > MAX_TEXT): raise DatasetError("Curated evaluation exclusion rationale is invalid.")
    return {"schema_version": SCHEMA_VERSION, "captured_at": captured, "excluded_case_count": excluded, "exclusion_rationale": exclusion_rationale, "limitations": limitations, "cases": cleaned}


def _url(value: object) -> None:
    parsed = urlparse(value if isinstance(value, str) else "")
    if parsed.scheme != "https" or not parsed.netloc: raise DatasetError("Curated evaluation requires valid public HTTPS source URLs.")
