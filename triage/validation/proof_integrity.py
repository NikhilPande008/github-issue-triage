"""Conservative static checks for obviously manufactured generated-test failures."""
from __future__ import annotations

import json
import re
from pathlib import Path

from triage.domain.models import IssueExtraction

ANALYZER_VERSION = "proof-integrity-v1"
_FALSE_ASSERT = re.compile(r"^\s*assert\s+(?:False|0|0\.0|\[\]|\{\}|\(\))\s*(?:,.*)?$")
_FAIL = re.compile(r"^\s*(?:raise\s+(?:AssertionError|Exception|RuntimeError|ValueError)|pytest\.fail\s*\(|self\.fail\s*\()")
_IDENTIFIER = re.compile(r"\b(?:[A-Z][A-Za-z0-9_]{2,}|[a-z][a-z0-9]*_[a-zA-Z0-9_]{2,})\b")


def _finding(rule: str, severity: str, explanation: str, path: str | None = None, line: int | None = None) -> dict[str, object]:
    return {"rule_id": rule, "severity": severity, "explanation": explanation[:800], "path": path, "line": line}


def _files(diff: str) -> list[tuple[str, list[tuple[int, str]]]]:
    current: str | None = None; added: list[tuple[int, str]] = []; result = []
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            if current is not None: result.append((current, added))
            parts = line.split(); current = parts[3][2:] if len(parts) > 3 and parts[3].startswith("b/") else None; added = []
        elif current is not None and line.startswith("@@"):
            match = re.search(r"\+(\d+)", line)
            if match: number = int(match.group(1))
        elif current is not None and line.startswith("+") and not line.startswith("+++"):
            added.append((locals().get("number", 0), line[1:])); number = locals().get("number", 0) + 1
    if current is not None: result.append((current, added))
    return result


def _is_test_path(path: Path, runner_id: str) -> bool:
    if runner_id == "pytest":
        return path.suffix == ".py" and (path.parts[0] == "tests" or path.name.startswith("test_"))
    if runner_id == "vitest":
        return path.suffix in {".ts", ".tsx", ".js", ".jsx"} and ("test" in path.name.lower() or "spec" in path.name.lower())
    return False


def _direct_test_body_statement(content: str) -> bool:
    """Hard-reject only a statement directly in the test body, not guarded code."""
    return bool(re.match(r"^ {4}(?:assert\b|raise\b|pytest\.fail\b|self\.fail\b)", content))


def analyze(diff_path: Path, runner_id: str, extraction: IssueExtraction) -> dict[str, object]:
    try:
        diff = diff_path.read_text(encoding="utf-8")
    except OSError:
        return {"version": ANALYZER_VERSION, "result": "UNAVAILABLE", "findings": [_finding("DIFF_UNAVAILABLE", "INFO", "The persisted diff could not be read.")]}
    if runner_id not in {"pytest", "vitest"}:
        return {"version": ANALYZER_VERSION, "result": "UNAVAILABLE", "findings": [_finding("RUNNER_UNAVAILABLE", "INFO", "The stored runner cannot be analyzed.")]}
    findings: list[dict[str, object]] = []; files = _files(diff)
    executable = [(path, lines) for path, lines in files if _is_test_path(Path(path), runner_id)]
    if not executable: findings.append(_finding("NO_CHANGED_EXECUTABLE_TEST", "REJECT", "No changed executable test was detected."))
    for path, lines in files:
        is_test = _is_test_path(Path(path), runner_id)
        local_helper = path.startswith("tests/") and Path(path).name in {"conftest.py", "helpers.py", "utils.py"}
        if not is_test and not local_helper:
            severity = "REJECT"
            explanation = "Changed path is not an allowed test or test-local helper file; production/configuration changes cannot serve as proof."
            if re.search(r"(?:fixture|fixtures|snapshot|snapshots|golden)", path, re.I): explanation = "Modified fixture, snapshot, or golden path can manufacture expected output."
            findings.append(_finding("DISALLOWED_CHANGED_PATH", severity, explanation, path))
        if re.search(r"(?:fixture|fixtures|snapshot|snapshots|golden)", path, re.I): findings.append(_finding("MODIFIED_FIXTURE_OR_SNAPSHOT", "REJECT", "Modified fixture/snapshot evidence cannot be used to manufacture a failing proof.", path))
        if not is_test: continue
        for number, content in lines:
            if _direct_test_body_statement(content) and _FALSE_ASSERT.match(content): findings.append(_finding("UNCONDITIONAL_FALSE_ASSERTION", "REJECT", "Added literal-false assertion does not exercise the reported behavior.", path, number))
            if _direct_test_body_statement(content) and _FAIL.match(content): findings.append(_finding("UNCONDITIONAL_FAILURE_HELPER", "REJECT", "Added unconditional failure helper does not exercise the reported behavior.", path, number))
    test_text = "\n".join(line for _, lines in executable for _, line in lines)
    anchors = {item for source in (extraction.affected_area, extraction.expected_behavior, extraction.actual_behavior, extraction.summary) if source for item in _IDENTIFIER.findall(source)}
    stable = {item for item in anchors if "_" in item or item[:1].isupper()}
    if stable and not any(re.search(rf"\b{re.escape(anchor)}\b", test_text) for anchor in stable): findings.append(_finding("MISSING_BEHAVIOR_ANCHOR", "REVIEW_FLAG", "Changed test contains no stable extracted API/function/class anchor; human semantic review is required."))
    if re.search(r"(?:side_effect\s*=\s*(?:RuntimeError|Exception|AssertionError)|mock\w*\.side_effect)", test_text) and not stable.intersection(set(_IDENTIFIER.findall(test_text))): findings.append(_finding("MOCKED_FAILURE_WITHOUT_ANCHOR", "REVIEW_FLAG", "Changed test injects a mock failure without a stable behavior anchor; human semantic review is required."))
    result = "REJECTED_PROOF_PATTERN" if any(item["severity"] == "REJECT" for item in findings) else "REVIEW_FLAGGED" if any(item["severity"] == "REVIEW_FLAG" for item in findings) else "ACCEPTABLE"
    return {"version": ANALYZER_VERSION, "result": result, "findings": findings}


def write_report(report: dict[str, object], path: Path) -> Path:
    path.write_text(json.dumps(report, sort_keys=True, indent=2), encoding="utf-8")
    return path
