from types import SimpleNamespace
from pathlib import Path

import pytest

from triage.sandbox.container import CodexSandboxUnavailable, ContainerRole, DockerSandboxContainer


class FakeContainer:
    id = "container-1"

    def __init__(self, responses):
        self.responses = iter(responses)
        self.commands = []

    def exec_run(self, command, demux=False):
        self.commands.append(command)
        return next(self.responses)


def _result(exit_code: int, output: str):
    return SimpleNamespace(exit_code=exit_code, output=output.encode())


def test_codex_uses_workspace_write_when_bwrap_is_available() -> None:
    container = FakeContainer([_result(0, "changed tests/test_target.py")])
    sandbox = DockerSandboxContainer(container, 60)

    execution = sandbox.run_codex("make a focused test", 30)

    assert execution.fallback is None
    assert "--sandbox workspace-write" in container.commands[0][-1]
    assert "dangerously-bypass" not in container.commands[0][-1]


def test_codex_uses_docker_isolated_fallback_only_for_bwrap_failure() -> None:
    container = FakeContainer([
        _result(0, "bwrap: No permissions to create a new namespace"),
        _result(0, "changed tests/test_target.py"),
    ])
    sandbox = DockerSandboxContainer(container, 60)

    execution = sandbox.run_codex("make a focused test", 30)

    assert execution.fallback is not None
    assert "--sandbox workspace-write" in container.commands[0][-1]
    assert "--dangerously-bypass-approvals-and-sandbox" in container.commands[1][-1]


def test_codex_reports_clear_error_when_fallback_cannot_run() -> None:
    container = FakeContainer([
        _result(0, "bwrap: No permissions to create a new namespace"),
        _result(1, "bwrap: No permissions to create a new namespace"),
    ])
    sandbox = DockerSandboxContainer(container, 60)

    with pytest.raises(CodexSandboxUnavailable, match="Docker-isolated fallback"):
        sandbox.run_codex("make a focused test", 30)


def test_container_mounts_only_workspace_and_read_only_auth(tmp_path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    auth = tmp_path / "auth.json"
    auth.write_text("{}", encoding="utf-8")
    captured = {}

    class FakeContainers:
        def run(self, image_id, **kwargs):
            captured["image_id"] = image_id
            captured.update(kwargs)
            return FakeContainer([])

    docker_client = SimpleNamespace(containers=FakeContainers())
    DockerSandboxContainer.start(docker_client, SimpleNamespace(id="image-1"), repository, auth, 60, ContainerRole.AGENT)

    assert captured["volumes"] == {
        str(repository): {"bind": "/workspace/repo", "mode": "rw"},
        str(auth): {"bind": "/root/.codex/auth.json", "mode": "ro"},
    }
    assert "privileged" not in captured
    assert "userns_mode" not in captured


def test_test_role_cannot_invoke_codex() -> None:
    sandbox = DockerSandboxContainer(FakeContainer([]), 60, ContainerRole.TEST)
    with pytest.raises(RuntimeError, match="only in the agent container"):
        sandbox.run_codex("probe", 1)
