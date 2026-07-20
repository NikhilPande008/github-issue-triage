"""Opt-in smoke test that exercises Codex inside the real Docker isolation boundary."""

import os
import subprocess
from pathlib import Path

import docker
import pytest

from triage.config.settings import Settings
from triage.sandbox.container import DockerSandboxContainer
from triage.sandbox.images import ensure_image


@pytest.mark.skipif(
    os.environ.get("RUN_DOCKER_CODEX_SMOKE") != "1",
    reason="set RUN_DOCKER_CODEX_SMOKE=1 to run the paid Docker/Codex smoke test",
)
def test_codex_can_modify_fixture_and_run_a_focused_pytest(tmp_path: Path) -> None:
    settings = Settings()
    if not settings.codex_auth_path.is_file():
        pytest.skip("Codex authentication file is not available")

    repository = tmp_path / "fixture-repository"
    tests = repository / "tests"
    tests.mkdir(parents=True)
    (tests / "test_smoke.py").write_text(
        "def test_existing_fixture():\n    assert True\n", encoding="utf-8"
    )
    subprocess.run(["git", "init"], cwd=repository, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=repository, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.name=Smoke", "-c", "user.email=smoke@example.invalid", "commit", "-m", "fixture"],
        cwd=repository,
        check=True,
        capture_output=True,
    )

    client = docker.from_env()
    image = ensure_image(client, settings.sandbox_image)
    container = DockerSandboxContainer.start(
        client, image, repository.resolve(), settings.codex_auth_path, 180
    )
    try:
        container.run("python -m pip install pytest", 60)
        execution = container.run_codex(
            "Modify only tests/test_smoke.py. Add a test named test_codex_can_write that asserts "
            "2 + 2 == 4. Run exactly python -m pytest -q "
            "tests/test_smoke.py::test_codex_can_write. Do not modify any other file.",
            120,
        )
        pytest_result = container.run(
            "python -m pytest -q tests/test_smoke.py::test_codex_can_write", 60
        )
        diff = container.run("git diff --no-ext-diff", 30)
        artifact_dir = tmp_path / "artifacts" / "attempt_1"
        terminal = (
            f"$ {execution.result.command}\n{execution.result.output}"
            f"[exit {execution.result.exit_code}; elapsed {execution.result.elapsed_ms}ms]\n"
            f"$ {pytest_result.command}\n{pytest_result.output}"
            f"[exit {pytest_result.exit_code}; elapsed {pytest_result.elapsed_ms}ms]\n"
            f"$ {diff.command}\n{diff.output}"
            f"[exit {diff.exit_code}; elapsed {diff.elapsed_ms}ms]\n"
        )
        for name, content in {
            "terminal.log": terminal,
            "pytest_output.txt": pytest_result.output,
            "git.diff": diff.output,
        }.items():
            source = f"/sandbox-artifacts/smoke/{name}"
            container.write_artifact(source, content)
            container.copy_artifact(source, artifact_dir / name)

        assert pytest_result.exit_code == 0, pytest_result.output
        assert "test_codex_can_write" in diff.output
        assert "test_codex_can_write" in (tests / "test_smoke.py").read_text(encoding="utf-8")
        assert execution.result.exit_code == 0, execution.result.output
        assert "elapsed" in (artifact_dir / "terminal.log").read_text(encoding="utf-8")
        assert "test_codex_can_write" in (artifact_dir / "git.diff").read_text(encoding="utf-8")
    finally:
        container.remove()
