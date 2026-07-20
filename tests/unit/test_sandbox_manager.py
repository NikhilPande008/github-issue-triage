from pathlib import Path

import pytest

import triage.sandbox.manager as manager_module
from triage.sandbox.manager import Sandbox, SandboxManager
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
    workspace.root.mkdir()
    removed = []

    class FakeStartedContainer:
        id = "container-1"

        def run(self, command, timeout):
            raise RuntimeError("install failed")

        def remove(self):
            removed.append(True)

    monkeypatch.setattr(manager_module.SandboxWorkspace, "create", lambda *args: workspace)
    monkeypatch.setattr(manager_module, "ensure_image", lambda client, name: type("Image", (), {"id": "image-1"})())
    monkeypatch.setattr(manager_module.DockerSandboxContainer, "start", lambda *args: FakeStartedContainer())
    manager = SandboxManager(tmp_path, "image", 10, 20, Path("missing"), docker_client=object())

    with pytest.raises(RuntimeError, match="install failed"):
        manager.create("run-1", "psf/requests")
    assert removed == [True]
    assert not workspace.root.exists()
