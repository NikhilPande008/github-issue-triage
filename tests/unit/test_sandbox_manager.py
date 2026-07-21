from pathlib import Path

import pytest

import triage.sandbox.manager as manager_module
from triage.sandbox.container import ContainerCommandResult
from triage.sandbox.manager import EnvironmentSetupFailure, Sandbox, SandboxManager, resolve_setup_command
from triage.sandbox.workspace import SandboxWorkspace


class FakeContainer:
    id = "container-1"

    def __init__(self):
        self.removed = False

    def remove(self):
        self.removed = True


def test_cleanup_removes_container_and_workspace(tmp_path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    container = FakeContainer()
    sandbox = Sandbox(SandboxWorkspace(root, root / "repository"), container, "image-1", "run-1", 0)

    sandbox.cleanup()

    assert container.removed is True
    assert not root.exists()


def test_manager_cleans_container_when_dependency_setup_fails(monkeypatch, tmp_path) -> None:
    workspace = SandboxWorkspace(tmp_path / "workspace", tmp_path / "workspace" / "repository")
    workspace.repository_path.mkdir(parents=True)
    (workspace.repository_path / "requirements.txt").write_text("example==1", encoding="utf-8")
    removed = []

    class FakeStartedContainer:
        id = "container-1"

        def run(self, command, timeout):
            return ContainerCommandResult(1, "pip exploded")

        def remove(self):
            removed.append(True)

    monkeypatch.setattr(manager_module.SandboxWorkspace, "create", lambda *args: workspace)
    monkeypatch.setattr(manager_module, "ensure_image", lambda client, name: type("Image", (), {"id": "image-1"})())
    monkeypatch.setattr(manager_module.DockerSandboxContainer, "start", lambda *args: FakeStartedContainer())
    manager = SandboxManager(tmp_path, "image", 10, 20, Path("missing"), docker_client=object())

    with pytest.raises(EnvironmentSetupFailure, match="requirements.txt installation exited 1") as error:
        manager.create("run-1", "psf/requests")
    assert error.value.output == "pip exploded"
    assert removed == [True]
    assert not workspace.root.exists()


def test_manager_uses_configured_setup_command(monkeypatch, tmp_path) -> None:
    workspace = SandboxWorkspace(tmp_path / "workspace", tmp_path / "workspace" / "repository")
    workspace.root.mkdir()
    commands = []

    class FakeStartedContainer:
        id = "container-1"
        def run(self, command, timeout): commands.append(command)
        def remove(self): pass

    monkeypatch.setattr(manager_module.SandboxWorkspace, "create", lambda *args: workspace)
    monkeypatch.setattr(manager_module, "ensure_image", lambda client, name: type("Image", (), {"id": "image-1"})())
    monkeypatch.setattr(manager_module.DockerSandboxContainer, "start", lambda *args: FakeStartedContainer())
    manager = SandboxManager(tmp_path, "image", 10, 20, Path("missing"), docker_client=object(), setup_command="python -m pip install -e . pytest")
    manager.create("run-1", "encode/httpx")
    assert commands == ["python -m pip install -e . pytest"]


@pytest.mark.parametrize(
    ("files", "command", "reason"),
    [
        (["requirements-dev.txt", "requirements.txt", "pyproject.toml"], "python -m pip install -r requirements-dev.txt", "requirements-dev.txt"),
        (["requirements.txt", "pyproject.toml"], "python -m pip install -r requirements.txt", "requirements.txt"),
        (["pyproject.toml"], "python -m pip install -e .", "Python packaging metadata (pyproject.toml)"),
        (["setup.py"], "python -m pip install -e .", "Python packaging metadata (setup.py)"),
    ],
)
def test_resolve_setup_command_uses_supported_repository_manifests(tmp_path, files, command, reason) -> None:
    for name in files:
        (tmp_path / name).write_text("", encoding="utf-8")
    setup = resolve_setup_command(tmp_path, None)
    assert (setup.command, setup.reason) == (command, reason)


def test_resolve_setup_command_prefers_explicit_configuration(tmp_path) -> None:
    (tmp_path / "requirements-dev.txt").write_text("", encoding="utf-8")
    setup = resolve_setup_command(tmp_path, "python -m pip install -e .[test]")
    assert setup.command == "python -m pip install -e .[test]"
    assert setup.reason == "explicit SANDBOX_SETUP_COMMAND"


def test_resolve_setup_command_rejects_repository_without_supported_manifest(tmp_path) -> None:
    with pytest.raises(EnvironmentSetupFailure, match="no requirements-dev.txt, requirements.txt, or Python package metadata found"):
        resolve_setup_command(tmp_path, None)
