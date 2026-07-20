import subprocess

import triage.investigation.runner as runner_module
from triage.investigation.runner import LocalInvestigationRunner


def test_local_runner_captures_mocked_codex_pytest_and_diff(monkeypatch, tmp_path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        if command[0] == "codex":
            return subprocess.CompletedProcess(command, 0, "codex output", "")
        if command[1:3] == ["-m", "pytest"]:
            return subprocess.CompletedProcess(command, 1, "pytest output", "pytest error")
        return subprocess.CompletedProcess(command, 0, "diff output", "")

    monkeypatch.setattr(runner_module.subprocess, "run", fake_run)
    result = LocalInvestigationRunner().run_attempt(repository, "prompt", tmp_path / "artifacts")

    assert result.evidence.pytest_exit_code == 1
    assert result.evidence.pytest_output_path.read_text(encoding="utf-8") == "pytest outputpytest error"
    assert result.evidence.git_diff_path.read_text(encoding="utf-8") == "diff output"
    assert "codex output" in result.terminal_log_path.read_text(encoding="utf-8")
    assert [command[0] for command in commands] == ["codex", "python", "git"]
