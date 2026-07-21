import pytest

from triage.validation.junit import parse_junit_xml


def _parse(tmp_path, body: str):
    path = tmp_path / "results.xml"
    path.write_text(body, encoding="utf-8")
    return parse_junit_xml(path)


def test_junit_accepts_failure_with_passed_and_skipped_cases(tmp_path) -> None:
    report = _parse(tmp_path, '''<testsuite tests="3" failures="1" errors="0" skipped="1">
      <testcase file="tests/a.py" name="pass"/><testcase file="tests/a.py" name="fail"><failure/></testcase><testcase file="tests/a.py" name="skip"><skipped/></testcase>
    </testsuite>''')
    assert report.rejection_reason is None
    assert (report.total, report.passed, report.failed, report.skipped, report.errors) == (3, 1, 1, 1, 0)


@pytest.mark.parametrize("body,reason", [
    ('<testsuite tests="0" failures="0" errors="0" skipped="0"/>', None),
    ('<testsuite tests="1" failures="0" errors="1" skipped="0"><testcase name="x"><error/></testcase></testsuite>', None),
    ('<testsuite tests="2" failures="1" errors="0" skipped="0"><testcase name="x"><failure/></testcase></testsuite>', "inconsistent"),
    ('<testsuite', "malformed"),
])
def test_junit_rejects_malformed_or_inconsistent_data(tmp_path, body, reason) -> None:
    report = _parse(tmp_path, body)
    if reason:
        assert reason in (report.rejection_reason or "")
    else:
        assert report.rejection_reason is None
