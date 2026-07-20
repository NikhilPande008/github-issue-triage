from pathlib import Path

from triage.validation.pytest_parser import parse_pytest_output


def test_parser_finds_assertion_failure_from_pytest_summary() -> None:
    output = """==================== FAILURES ====================
tests/test_api.py:10: AssertionError
================ short test summary info ================
FAILED tests/test_api.py::test_api - AssertionError: bad
===================== 1 failed in 0.1s =====================
"""
    report = parse_pytest_output(output, 1)
    assert report.completed is True
    assert report.assertion_failures == [Path("tests/test_api.py")]


def test_parser_accepts_plain_completed_failure_counts_from_recorded_rerun() -> None:
    output = """=================================== FAILURES ===================================
_______________ TestRequests.test_invalid_ssl_certificate_files ________________

>       requests.get(httpbin_secure(), cert=INVALID_PATH)
E       OSError: Could not find the TLS certificate file, invalid path: /garbage

src/requests/adapters.py:356: OSError
=========================== short test summary info ============================
FAILED tests/test_requests.py::TestRequests::test_invalid_ssl_certificate_files
1 failed, 338 passed, 1 skipped, 1 xfailed, 12 warnings in 40.39s
"""
    report = parse_pytest_output(output, 1)
    assert report.completed is True
    assert report.assertion_failures == [Path("tests/test_requests.py")]


def test_parser_rejects_collection_failure() -> None:
    report = parse_pytest_output("ERROR collecting tests/test_api.py\nImportError", 2)
    assert report.completed is False
    assert report.rejection_reason == "Pytest collection failed."
