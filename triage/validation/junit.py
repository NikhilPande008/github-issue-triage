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


def parse_junit_xml(path: Path, runner_id: str = "pytest", selected_targets: list[object] | None = None) -> StructuredTestReport:
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
            cases.append(StructuredTestCase(_case_path(case, runner_id, selected_targets), case.attrib.get("name", ""), outcome))
    total = len(cases)
    failed = sum(case.outcome == "failure" for case in cases)
    errors = sum(case.outcome == "error" for case in cases)
    skipped = sum(case.outcome == "skipped" for case in cases)
    if has_declared and (declared_total != total or declared_failures != failed or declared_errors != errors or declared_skipped != skipped):
        return _reject(path, "Structured test-result counters are inconsistent with testcase entries.")
    return StructuredTestReport(total, total - failed - errors - skipped, failed, skipped, errors, cases, path)


def _case_path(case, runner_id: str, selected_targets: list[object] | None) -> Path | None:
    # An explicit path is producer-owned metadata and always takes precedence.
    explicit = case.attrib.get("file")
    if explicit:
        return Path(explicit)
    classname = case.attrib.get("classname")
    if not classname:
        return None
    if runner_id == "pytest":
        return _pytest_classname_path(classname, selected_targets)
    # Non-pytest producers may use path-shaped classnames. Do not reinterpret
    # dotted identifiers as Python modules outside the pytest adapter.
    candidate = Path(classname)
    return candidate if "/" in classname and candidate.suffix else None


def _pytest_classname_path(classname: str, selected_targets: list[object] | None) -> Path | None:
    """Map pytest's dotted module[.Class] metadata without using class casing."""
    for target in selected_targets or []:
        if not isinstance(target, str):
            continue
        module_path = target.split("::", 1)[0]
        if not module_path.endswith(".py"):
            continue
        module_name = module_path[:-3].replace("/", ".")
        if classname == module_name or classname.startswith(module_name + "."):
            return Path(module_path)
    parts = classname.split(".")
    module_indexes = [index for index, part in enumerate(parts) if part.startswith("test_") or part.endswith("_test")]
    if len(module_indexes) != 1:
        return None
    return Path("/".join(parts[:module_indexes[0] + 1]) + ".py")


def matches_selected_node(path: Path | None, name: str, targets: list[object]) -> bool:
    """Require both the normalized module path and the exact test name."""
    if path is None:
        return False
    normalized = str(path).removesuffix(".py")
    for target in targets:
        if not isinstance(target, str):
            continue
        parts = target.split("::")
        if normalized != parts[0].removesuffix(".py"):
            continue
        test_name = parts[-1]
        if name == test_name or name.endswith(f"::{test_name}") or name.endswith(f".{test_name}"):
            return True
    return False


def _int(value: str | None) -> int:
    try:
        return int(value or "0")
    except ValueError:
        return -1


def _reject(path: Path, reason: str) -> StructuredTestReport:
    return StructuredTestReport(0, 0, 0, 0, 0, [], path, reason)
