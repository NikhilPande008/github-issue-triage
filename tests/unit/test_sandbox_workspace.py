import triage.sandbox.workspace as workspace_module
from triage.sandbox.workspace import SandboxWorkspace


def test_workspace_is_fresh_and_deleted(monkeypatch, tmp_path) -> None:
    cloned = []

    def fake_clone(url, destination, depth):
        cloned.append((url, destination, depth))
        destination.mkdir()

    monkeypatch.setattr(workspace_module.Repo, "clone_from", fake_clone)
    workspace = SandboxWorkspace.create(tmp_path, "run-1", "psf/requests")

    assert workspace.root == (tmp_path / "run_run-1").resolve()
    assert workspace.repository_path.exists()
    assert cloned == [("https://github.com/psf/requests.git", workspace.repository_path, 1)]
    workspace.delete()
    assert not workspace.root.exists()
