import json

import pytest

from triage.runners import RunnerSelectionError, select_runner


def test_explicit_runner_selection_wins_over_repository_metadata(tmp_path) -> None:
    (tmp_path / "package.json").write_text(json.dumps({"devDependencies": {"vitest": "1"}}))
    (tmp_path / "pyproject.toml").write_text("[project]\nname='both'")
    assert select_runner("vitest", tmp_path).id == "vitest"


def test_auto_runner_rejects_ambiguous_or_unsupported_repository(tmp_path) -> None:
    (tmp_path / "package.json").write_text(json.dumps({"devDependencies": {"vitest": "1"}}))
    (tmp_path / "pyproject.toml").write_text("[project]\nname='both'")
    with pytest.raises(RunnerSelectionError, match="Ambiguous"):
        select_runner("auto", tmp_path)
    with pytest.raises(RunnerSelectionError, match="Unsupported repository"):
        select_runner("auto", tmp_path / "empty")


def test_vitest_setup_and_focused_command_are_safe(tmp_path) -> None:
    (tmp_path / "package.json").write_text(json.dumps({"devDependencies": {"vitest": "1"}}))
    (tmp_path / "package-lock.json").write_text("{}")
    runner = select_runner("vitest", tmp_path)
    assert runner.setup_command(tmp_path, None).command == "npm ci"
    command = runner.focused_command(" M tests/a test.spec.ts\n M package.json\n")
    assert command == "npm exec -- vitest run -- 'tests/a test.spec.ts'"


def test_runners_emit_safe_junit_result_paths(tmp_path) -> None:
    pytest_runner = select_runner("pytest", tmp_path)
    assert "--junitxml='/tmp/result.xml'" in pytest_runner.focused_command(" M tests/test_a.py\n", "/tmp/result.xml")
    (tmp_path / "package.json").write_text(json.dumps({"devDependencies": {"vitest": "1"}}))
    vitest_runner = select_runner("vitest", tmp_path)
    command = vitest_runner.focused_command(" M tests/a.spec.ts\n", "/tmp/result.xml")
    assert "--reporter=junit --outputFile='/tmp/result.xml'" in command
