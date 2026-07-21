"""Runner-neutral, conservative JUnit XML evidence parser."""

from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree


@dataclass(frozen=True)
class StructuredTestCase:
    path: Path | None
    name: str
    outcome: str  # passed, skipped, failure, error


@dataclass(frozen=True)
class StructuredTestReport:
    total: int
    passed: int
    failed: int
    skipped: int
    errors: int
    cases: list[StructuredTestCase]
    path: Path
    rejection_reason: str | None = None


def parse_junit_xml(path: Path) -> StructuredTestReport:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return _reject(path, "Structured test results are missing.")
    if not content.strip():
        return _reject(path, "Structured test results are empty.")
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError:
        return _reject(path, "Structured test results are malformed JUnit XML.")
    suites = [root] if root.tag == "testsuite" else list(root.findall(".//testsuite"))
    if not suites:
        return _reject(path, "Structured test results contain no test suites.")
    cases: list[StructuredTestCase] = []
    declared_total = declared_failures = declared_errors = declared_skipped = 0
    has_declared = False
    for suite in suites:
        if any(key in suite.attrib for key in ("tests", "failures", "errors", "skipped")):
            has_declared = True
            declared_total += _int(suite.attrib.get("tests"))
            declared_failures += _int(suite.attrib.get("failures"))
            declared_errors += _int(suite.attrib.get("errors"))
            declared_skipped += _int(suite.attrib.get("skipped"))
        for case in suite.findall("testcase"):
            outcome = "passed"
            if case.find("error") is not None:
                outcome = "error"
            elif case.find("failure") is not None:
                outcome = "failure"
            elif case.find("skipped") is not None:
                outcome = "skipped"
            cases.append(StructuredTestCase(_case_path(case), case.attrib.get("name", ""), outcome))
    total = len(cases)
    failed = sum(case.outcome == "failure" for case in cases)
    errors = sum(case.outcome == "error" for case in cases)
    skipped = sum(case.outcome == "skipped" for case in cases)
    if has_declared and (declared_total != total or declared_failures != failed or declared_errors != errors or declared_skipped != skipped):
        return _reject(path, "Structured test-result counters are inconsistent with testcase entries.")
    return StructuredTestReport(total, total - failed - errors - skipped, failed, skipped, errors, cases, path)


def _case_path(case) -> Path | None:
    raw = case.attrib.get("file") or case.attrib.get("classname")
    if not raw:
        return None
    if "/" not in raw and "." in raw:
        raw = raw.replace(".", "/")
    candidate = Path(raw)
    if candidate.suffix:
        return candidate
    # pytest typically writes dotted module names; Vitest commonly uses paths.
    return Path(str(candidate) + ".py")


def _int(value: str | None) -> int:
    try:
        return int(value or "0")
    except ValueError:
        return -1


def _reject(path: Path, reason: str) -> StructuredTestReport:
    return StructuredTestReport(0, 0, 0, 0, 0, [], path, reason)
