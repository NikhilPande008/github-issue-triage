from pathlib import Path

from triage.runners.adapters import PytestAdapter
from triage.validation.models import ValidationEvidence
from triage.validation.validator import EvidenceValidator


def diff(path: str, line: int, body: str) -> str:
    return f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -{line},1 +{line},1 @@\n-{body}\n+{body}  # changed\n"


def test_requests_class_method_is_selected_as_an_exact_pytest_node(tmp_path):
    path = tmp_path / "tests" / "test_requests.py"; path.parent.mkdir(); path.write_text("class TestRequests:\n    def test_invalid_ssl_certificate_files(self):\n        assert True\n\n    def test_timeout(self):\n        assert True\n", encoding="utf-8")
    selection = PytestAdapter().select_targets(tmp_path, diff("tests/test_requests.py", 3, "        assert True"))
    assert selection.precision == "EXACT"
    assert selection.targets == ("tests/test_requests.py::TestRequests::test_invalid_ssl_certificate_files",)
    assert "test_timeout" not in PytestAdapter().command_for_selection(selection)


def test_top_level_parametrized_and_multiple_tests_are_exact(tmp_path):
    path = tmp_path / "tests" / "test_a.py"; path.parent.mkdir(); path.write_text("import pytest\n\n@pytest.mark.parametrize('x', [1])\ndef test_parametrized(x):\n    assert x\n\ndef test_other():\n    assert True\n", encoding="utf-8")
    patch = "diff --git a/tests/test_a.py b/tests/test_a.py\n--- a/tests/test_a.py\n+++ b/tests/test_a.py\n@@ -5,1 +5,1 @@\n-    assert x\n+    assert x == 1\n@@ -8,1 +8,1 @@\n-    assert True\n+    assert 1\n"
    selection = PytestAdapter().select_targets(tmp_path, patch)
    assert selection.targets == ("tests/test_a.py::test_other", "tests/test_a.py::test_parametrized")


def test_import_or_fixture_change_is_not_exact(tmp_path):
    path = tmp_path / "tests" / "test_a.py"; path.parent.mkdir(); path.write_text("import os\n\nimport pytest\n\n@pytest.fixture\ndef thing():\n    return 1\n\ndef test_a(thing):\n    assert thing\n", encoding="utf-8")
    selection = PytestAdapter().select_targets(tmp_path, diff("tests/test_a.py", 1, "import os"))
    assert selection.precision == "FILE_ONLY"


def test_file_only_and_junit_outside_exact_scope_cannot_confirm(tmp_path):
    diff_path = tmp_path / "diff"; diff_path.write_text("diff --git a/tests/test_a.py b/tests/test_a.py\n--- a/tests/test_a.py\n+++ b/tests/test_a.py\n@@ -2,1 +2,1 @@\n-    assert True\n+    assert value\n", encoding="utf-8")
    output = tmp_path / "out"; output.write_text("", encoding="utf-8")
    junit = tmp_path / "junit.xml"; junit.write_text('<testsuite tests="1" failures="1"><testcase classname="tests.test_a" name="test_other"><failure/></testcase></testsuite>', encoding="utf-8")
    file_only = EvidenceValidator().validate(ValidationEvidence(diff_path, output, 1, structured_results_path=junit, focused_test_selection={"precision": "FILE_ONLY", "targets": ["tests/test_a.py"]}))
    assert file_only.asserts_failure is False
    exact = EvidenceValidator().validate(ValidationEvidence(diff_path, output, 1, structured_results_path=junit, focused_test_selection={"precision": "EXACT", "targets": ["tests/test_a.py::test_expected"]}))
    assert exact.asserts_failure is False and "exact selected" in exact.reason


def test_requests_shaped_pytest_junit_classname_confirms_only_the_selected_method(tmp_path):
    diff_path = tmp_path / "diff"; diff_path.write_text("diff --git a/tests/test_requests.py b/tests/test_requests.py\n--- a/tests/test_requests.py\n+++ b/tests/test_requests.py\n@@ -3,1 +3,1 @@\n-        assert True\n+        assert False\n", encoding="utf-8")
    output = tmp_path / "out"; output.write_text("", encoding="utf-8")
    junit = tmp_path / "junit.xml"; junit.write_text('<testsuite tests="1" failures="1" errors="0" skipped="0"><testcase classname="tests.test_requests.TestRequests" name="test_invalid_ssl_certificate_files"><failure/></testcase></testsuite>', encoding="utf-8")
    target = "tests/test_requests.py::TestRequests::test_invalid_ssl_certificate_files"
    result = EvidenceValidator().validate(ValidationEvidence(diff_path, output, 1, structured_results_path=junit, focused_test_selection={"precision": "EXACT", "targets": [target]}, focused_test_selection_required=True))
    assert result.asserts_failure is True
    wrong_name = EvidenceValidator().validate(ValidationEvidence(diff_path, output, 1, structured_results_path=junit, focused_test_selection={"precision": "EXACT", "targets": ["tests/test_requests.py::TestRequests::test_timeout"]}, focused_test_selection_required=True))
    assert wrong_name.asserts_failure is False
    assert "exact selected" in wrong_name.reason
