from pathlib import Path

import pytest

from triage.validation.models import ValidationEvidence
from triage.validation.validator import EvidenceValidator

FIXTURES = Path(__file__).parents[1] / "fixtures" / "pytest"
DIFF = """diff --git a/tests/test_reproduction.py b/tests/test_reproduction.py
--- a/tests/test_reproduction.py
+++ b/tests/test_reproduction.py
@@ -1 +1,2 @@
+def test_reproduces_issue():
+    assert response.status_code == 200
"""


def validate(tmp_path, fixture: str, exit_code: int, diff: str = DIFF):
    diff_path = tmp_path / "git.diff"
    output_path = tmp_path / "pytest_output.txt"
    diff_path.write_text(diff, encoding="utf-8")
    output_path.write_text((FIXTURES / fixture).read_text(encoding="utf-8"), encoding="utf-8")
    return EvidenceValidator().validate(ValidationEvidence(diff_path, output_path, exit_code))


def test_successful_reproduction_fixture(tmp_path) -> None:
    result = validate(tmp_path, "successful_reproduction.txt", 1)
    assert result.asserts_failure is True
    assert result.failing_test_paths == [Path("tests/test_reproduction.py")]
    assert result.assertion_count == 1


def test_completed_plain_failure_summary_in_changed_test_is_reproduced(tmp_path) -> None:
    output = """=================================== FAILURES ===================================
_______________ TestRequests.test_invalid_ssl_certificate_files ________________

E       OSError: Could not find the TLS certificate file, invalid path: /garbage

=========================== short test summary info ============================
FAILED tests/test_requests.py::TestRequests::test_invalid_ssl_certificate_files
1 failed, 338 passed, 1 skipped, 1 xfailed, 12 warnings in 40.39s
"""
    diff = DIFF.replace("tests/test_reproduction.py", "tests/test_requests.py")
    diff_path = tmp_path / "git.diff"
    output_path = tmp_path / "pytest_output.txt"
    diff_path.write_text(diff, encoding="utf-8")
    output_path.write_text(output, encoding="utf-8")

    result = EvidenceValidator().validate(ValidationEvidence(diff_path, output_path, 1))

    assert result.asserts_failure is True
    assert result.failing_test_paths == [Path("tests/test_requests.py")]


@pytest.mark.parametrize(
    ("fixture", "exit_code"),
    [
        ("syntax_error.txt", 2),
        ("timeout.txt", 124),
        ("import_error.txt", 2),
        ("no_tests_collected.txt", 5),
    ],
)
def test_non_reproduction_fixtures(tmp_path, fixture, exit_code) -> None:
    assert validate(tmp_path, fixture, exit_code).asserts_failure is False


def test_modified_existing_passing_test_is_not_reproduced(tmp_path) -> None:
    result = validate(tmp_path, "passing_test.txt", 0)
    assert result.asserts_failure is False
    assert result.reason == "Pytest did not complete with a test failure summary."


def test_assertion_in_preexisting_test_is_rejected(tmp_path) -> None:
    result = validate(
        tmp_path,
        "successful_reproduction.txt",
        1,
        DIFF.replace("tests/test_reproduction.py", "tests/test_other.py"),
    )
    assert result.asserts_failure is False
    assert "pre-existing tests" in result.reason
