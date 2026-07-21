import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VitestReport:
    completed: bool
    rejection_reason: str | None
    assertion_failures: list[Path]


FAILED_FILE = re.compile(r"(?:FAIL|×)\s+([^\s]+\.(?:[cm]?[jt]sx?))", re.MULTILINE)
SUMMARY = re.compile(r"Tests\s+\d+ failed", re.IGNORECASE)


def parse_vitest_output(output: str, exit_code: int) -> VitestReport:
    lowered = output.lower()
    if "command not found" in lowered or "could not determine executable" in lowered:
        return VitestReport(False, "Vitest command was unavailable.", [])
    if "failed to resolve import" in lowered or "cannot find module" in lowered or "module not found" in lowered:
        return VitestReport(False, "Vitest encountered a module-resolution error.", [])
    if "syntaxerror" in lowered or "transform error" in lowered:
        return VitestReport(False, "Vitest encountered a syntax error.", [])
    if "no test suite found" in lowered or "no test files found" in lowered:
        return VitestReport(False, "Vitest test discovery failed.", [])
    if "timeout" in lowered or exit_code in {124, 137}:
        return VitestReport(False, "Vitest timed out or was terminated.", [])
    if "segmentation fault" in lowered or "fatal error" in lowered or "process exited unexpectedly" in lowered:
        return VitestReport(False, "Vitest process crashed.", [])
    if "tests" not in lowered or ("failed" not in lowered):
        return VitestReport(False, "Vitest did not complete with a test failure summary.", [])
    if exit_code != 1 or not SUMMARY.search(output):
        return VitestReport(False, "Vitest did not complete with a test failure summary.", [])
    paths = sorted({Path(match.group(1)) for match in FAILED_FILE.finditer(output)})
    if not paths:
        return VitestReport(False, "Vitest failure output did not identify a failing test file.", [])
    return VitestReport(True, None, paths)
