import pytest
from pathlib import Path

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


@pytest.mark.parametrize(
    ("classname", "targets", "expected"),
    [
        ("tests.test_requests", ["tests/test_requests.py::test_top_level"], "tests/test_requests.py"),
        ("tests.test_requests.TestRequests", ["tests/test_requests.py::TestRequests::test_invalid_ssl_certificate_files"], "tests/test_requests.py"),
        ("package.subpackage.test_module.TestClass", ["package/subpackage/test_module.py::TestClass::test_case"], "package/subpackage/test_module.py"),
    ],
)
def test_pytest_classname_maps_to_its_module_not_its_class(tmp_path, classname, targets, expected) -> None:
    report = _parse(tmp_path, f'<testsuite tests="1" failures="1" errors="0" skipped="0"><testcase classname="{classname}" name="test_case"><failure/></testcase></testsuite>')
    # The parser is intentionally runner-aware; use selected targets as fresh
    # exact-selection provenance just as the validator does.
    path = tmp_path / "results.xml"
    report = parse_junit_xml(path, "pytest", targets)
    assert report.cases[0].path == Path(expected)


def test_explicit_file_path_takes_precedence_and_unknown_pytest_classname_is_unavailable(tmp_path) -> None:
    path = tmp_path / "results.xml"
    path.write_text('<testsuite tests="2"><testcase file="tests/example.test.ts" classname="ignored.name" name="a"/><testcase classname="application.service.Widget" name="b"/></testsuite>', encoding="utf-8")
    report = parse_junit_xml(path, "pytest", ["tests/test_selected.py::test_selected"])
    assert report.cases[0].path == Path("tests/example.test.ts")
    assert report.cases[1].path is None
