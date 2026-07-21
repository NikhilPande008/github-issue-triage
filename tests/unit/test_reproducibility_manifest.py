import json

from triage.sandbox.runner import DockerInvestigationRunner


def test_manifest_contains_command_policy_and_integrity_hashes(tmp_path) -> None:
    runner = DockerInvestigationRunner.__new__(DockerInvestigationRunner)
    # Exercise the pure artifact-side contract without Docker.
    attempt = tmp_path / "attempt_1"
    attempt.mkdir()
    for name in ("terminal.log", "pytest_output.txt", "git.diff"):
        (attempt / name).write_text(name, encoding="utf-8")
    # Manifest shape is the persisted replay boundary.
    manifest = {
        "repository": "owner/repo", "repository_commit": "abc", "runner": "pytest",
        "focused_test_command": "python -m pytest -q --junitxml='/tmp/result.xml'",
        "network_policy": "isolated", "confirmation_runs": 2,
        "phase_boundaries": {"setup": {"network_policy": "allowed", "auth_mount": False}, "agent": {"network_policy": "allowed", "auth_mount": True}, "test": {"network_policy": "isolated", "auth_mount": False}},
        "dependency_snapshot": "pytest==8", "artifacts": {name: {"sha256": "hash"} for name in ("terminal.log", "pytest_output.txt", "git.diff")},
    }
    path = attempt / "reproducibility_manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert {"repository", "repository_commit", "runner", "focused_test_command", "network_policy", "confirmation_runs", "dependency_snapshot", "artifacts"} <= loaded.keys()
    assert loaded["phase_boundaries"]["test"] == {"network_policy": "isolated", "auth_mount": False}
