from pathlib import Path

from triage.validation.diff import analyze_diff


def test_diff_detects_executable_test_change() -> None:
    diff = """diff --git a/tests/test_request.py b/tests/test_request.py
--- a/tests/test_request.py
+++ b/tests/test_request.py
@@ -1,2 +1,3 @@
 def test_request():
-    assert True
+    assert response.status_code == 200
"""
    assert analyze_diff(diff).changed_test_paths == [Path("tests/test_request.py")]


def test_diff_ignores_docs_and_formatting_only_test_change() -> None:
    diff = """diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
+Documentation
diff --git a/tests/test_request.py b/tests/test_request.py
--- a/tests/test_request.py
+++ b/tests/test_request.py
-    assert True
+assert   True
"""
    assert analyze_diff(diff).changed_test_paths == []
