import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PytestReport:
    completed: bool
    rejection_reason: str | None
    assertion_failures: list[Path]


SUMMARY_FAILURE = re.compile(r"^FAILED\s+(?P<nodeid>\S+)(?:\s+-\s+(?P<reason>.*))?$", re.MULTILINE)
ASSERTION_LOCATION = re.compile(r"^(?P<path>(?:[^\n:]+/)?[^\n:]+\.py):\d+: AssertionError", re.MULTILINE)
TERMINAL_SUMMARY = re.compile(r"^=+\s+.*\bfailed\b.*\s+=+$", re.MULTILINE)


def parse_pytest_output(output: str, exit_code: int) -> PytestReport:
    rejection = _rejection_reason(output, exit_code)
    if rejection:
        return PytestReport(completed=False, rejection_reason=rejection, assertion_failures=[])
    if exit_code != 1 or not TERMINAL_SUMMARY.search(output):
        return PytestReport(completed=False, rejection_reason="Pytest did not complete with a test failure summary.", assertion_failures=[])

    assertion_paths = {Path(match.group("path")) for match in ASSERTION_LOCATION.finditer(output)}
    for match in SUMMARY_FAILURE.finditer(output):
        reason = (match.group("reason") or "").lstrip()
        if reason.startswith("assert ") or reason.startswith("AssertionError"):
            assertion_paths.add(Path(match.group("nodeid").split("::", maxsplit=1)[0]))
    return PytestReport(completed=True, rejection_reason=None, assertion_failures=sorted(assertion_paths))


def _rejection_reason(output: str, exit_code: int) -> str | None:
    normalized = output.lower()
    if exit_code == 5 or "no tests ran" in normalized or "collected 0 items" in normalized:
        return "No tests were collected."
    if "error collecting" in normalized or "collection errors" in normalized:
        return "Pytest collection failed."
    if "syntaxerror" in normalized:
        return "Pytest encountered a syntax error."
    if "importerror" in normalized or "modulenotfounderror" in normalized:
        return "Pytest encountered an import error."
    if "internalerror" in normalized:
        return "Pytest encountered an internal error."
    if "segmentation fault" in normalized or "fatal python error" in normalized:
        return "Pytest process crashed."
    if "timeout" in normalized or exit_code in {124, 137}:
        return "Pytest timed out or was terminated."
    return None
