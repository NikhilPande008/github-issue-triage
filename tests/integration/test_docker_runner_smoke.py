from pathlib import Path

import pytest

from triage.sandbox.container import CodexExecutionResult, ContainerCommandResult
from triage.sandbox.container import SandboxTimeout
from triage.sandbox.manager import EnvironmentSetupFailure, SetupCommand
from triage.sandbox.runner import DockerInvestigationRunner, _focused_pytest_command


class FakeContainer:
    id = "container-smoke"

    def __init__(self):
        self.files = {}

    def run(self, command, timeout):
        if command.startswith("git status"):
            return ContainerCommandResult(0, " M tests/test_target.py\n")
        if command.startswith("python -m pytest"):
            return ContainerCommandResult(1, "one test failed")
        return ContainerCommandResult(0, "diff")

    def run_codex(self, prompt, timeout):
        result = ContainerCommandResult(0, "codex response", "codex exec --sandbox workspace-write --ephemeral 'prompt'", 12)
        return CodexExecutionResult(result, result, None)

    def write_artifact(self, path, content):
        self.files[path] = content

    def copy_artifact(self, source, destination):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(self.files[source], encoding="utf-8")
        return destination


class FakeSandbox:
    def __init__(self):
        self.container = FakeContainer()
        self.cleaned = False

    def cleanup(self):
        self.cleaned = True


class FakeManager:
    overall_timeout_seconds = 60

    def __init__(self):
        self.sandbox = FakeSandbox()
        self.created = []

    def create(self, run_id, repository):
        self.created.append((run_id, repository))
        return self.sandbox


def test_docker_runner_smoke_collects_artifacts_and_cleans_up(tmp_path) -> None:
    manager = FakeManager()
    with DockerInvestigationRunner(manager, "psf/requests", 30) as runner:
        result = runner.run_attempt(tmp_path, "prompt", tmp_path / "artifacts" / "run-1" / "attempt_1")

    assert manager.created == [("run-1", "psf/requests")]
    assert result.evidence.pytest_exit_code == 1
    assert result.evidence.pytest_output_path.read_text(encoding="utf-8") == "one test failed"
    assert result.evidence.git_diff_path.read_text(encoding="utf-8") == "diff"
    assert "--junitxml='/tmp/triage-run-1-attempt_1-junit.xml' 'tests/test_target.py'" in result.terminal_log_path.read_text(encoding="utf-8")
    assert manager.sandbox.cleaned is True


def test_docker_runner_preserves_timeout_evidence_when_container_is_unavailable(tmp_path) -> None:
    manager = FakeManager()

    def timeout(command, timeout):
        raise SandboxTimeout("pytest timeout")

    manager.sandbox.container.run = timeout
    with DockerInvestigationRunner(manager, "psf/requests", 30) as runner:
        result = runner.run_attempt(tmp_path, "prompt", tmp_path / "artifacts" / "run-2" / "attempt_1")

    assert "TIMEOUT: pytest timeout" in result.terminal_log_path.read_text(encoding="utf-8")
    assert result.evidence.pytest_output_path.exists()
    assert manager.sandbox.cleaned is True


def test_agent_edits_are_followed_by_test_and_confirmation_containers_only(tmp_path) -> None:
    events = []
    class Agent(FakeContainer):
        def run_codex(self, prompt, timeout):
            events.append("agent:codex"); return super().run_codex(prompt, timeout)
        def run(self, command, timeout):
            events.append("agent:status"); return super().run(command, timeout)
    class Test(FakeContainer):
        def run_codex(self, prompt, timeout): raise AssertionError("test container must not invoke Codex")
        def run(self, command, timeout):
            events.append("test:" + ("pytest" if command.startswith("python -m pytest") else "diff"))
            return super().run(command, timeout)
    class SplitSandbox(FakeSandbox):
        def __init__(self): self.agent_container = Agent(); self.test_container = None; self.cleaned = False
        def cleanup(self): self.cleaned = True
    class SplitManager:
        overall_timeout_seconds = 60
        def __init__(self): self.sandbox = SplitSandbox(); self.test = Test()
        def create(self, run_id, repository): return self.sandbox
        def close_agent_container(self, sandbox): events.append("agent:closed"); sandbox.agent_container = None
        def create_test_container(self, sandbox): sandbox.test_container = self.test; return self.test
    manager = SplitManager()
    with DockerInvestigationRunner(manager, "psf/requests", 30) as runner:
        runner.run_attempt(tmp_path, "prompt", tmp_path / "artifacts" / "split" / "attempt_1")
        runner.run_confirmation(tmp_path, "prompt", tmp_path / "artifacts" / "split" / "attempt_2")
    assert events[:4] == ["agent:codex", "agent:status", "agent:closed", "test:pytest"]
    assert events.count("agent:codex") == 1
    # Legacy in-memory fixture has no persisted exact selection, so the
    # confirmation fails closed before rerunning; it never reopens the agent.
    assert events.count("test:pytest") == 1


def test_focused_pytest_falls_back_to_the_full_suite_without_changed_tests() -> None:
    assert _focused_pytest_command(" M README.md\n?? notes.txt\n") == "python -m pytest -q"


def test_focused_pytest_accepts_a_root_level_pytest_file() -> None:
    assert _focused_pytest_command(" M test_regression.py\n") == "python -m pytest -q 'test_regression.py'"


def test_docker_runner_records_requirements_txt_setup_failure_for_non_requests_repository(tmp_path) -> None:
    class FailingManager(FakeManager):
        def create(self, run_id, repository):
            assert repository == "encode/httpx"
            raise EnvironmentSetupFailure(
                "Environment setup failed: requirements.txt installation exited 1",
                SetupCommand("python -m pip install -r requirements.txt", "requirements.txt"),
                "No matching distribution found",
            )

    runner = DockerInvestigationRunner(FailingManager(), "encode/httpx", 30)
    with pytest.raises(EnvironmentSetupFailure) as error:
        runner.run_attempt(tmp_path, "prompt", tmp_path / "artifacts" / "run-3" / "attempt_1")
    terminal = error.value.execution.terminal_log_path.read_text(encoding="utf-8")
    assert "ENVIRONMENT SETUP FAILURE" in terminal
    assert "Selected command: python -m pip install -r requirements.txt" in terminal
    assert "No matching distribution found" in terminal
