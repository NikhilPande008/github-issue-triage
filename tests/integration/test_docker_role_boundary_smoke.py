"""Opt-in Docker-only verification of the setup/agent/test role boundary.

This fixture never invokes Codex, OpenAI, GitHub, or a live investigation.
"""

import os

import docker
import pytest

from triage.config.settings import Settings
from triage.sandbox.container import ContainerRole, DockerSandboxContainer
from triage.sandbox.images import ensure_image


@pytest.mark.skipif(
    os.environ.get("RUN_DOCKER_BOUNDARY_SMOKE") != "1",
    reason="set RUN_DOCKER_BOUNDARY_SMOKE=1 to verify Docker role boundaries",
)
def test_setup_agent_and_test_boundaries_with_temporary_fixture(tmp_path) -> None:
    settings = Settings()
    repository = tmp_path / "fixture-repository"; repository.mkdir()
    auth = tmp_path / "probe-auth.json"; auth.write_text("probe-only", encoding="utf-8")
    client = docker.from_env(); image = ensure_image(client, settings.sandbox_image)
    setup = DockerSandboxContainer.start(client, image, repository, auth, 60, ContainerRole.SETUP, "allowed")
    agent = DockerSandboxContainer.start(client, image, repository, auth, 60, ContainerRole.AGENT, "allowed")
    test = DockerSandboxContainer.start(client, image, repository, auth, 60, ContainerRole.TEST, "isolated")
    confirmation = DockerSandboxContainer.start(client, image, repository, auth, 60, ContainerRole.TEST, "isolated")
    try:
        assert str(auth) not in (setup.container.attrs["HostConfig"].get("Binds") or [])
        assert str(auth) in " ".join(agent.container.attrs["HostConfig"].get("Binds") or [])
        for container in (test, confirmation):
            assert str(auth) not in " ".join(container.container.attrs["HostConfig"].get("Binds") or [])
            assert container.container.attrs["HostConfig"]["NetworkMode"] == "none"
            assert not any("CODEX" in value.upper() or "AUTH.JSON" in value for value in container.container.attrs["Config"].get("Env", []))
        assert agent.run("printf agent-change > agent-visible.txt", 10).exit_code == 0
        assert test.run("test \"$(cat agent-visible.txt)\" = agent-change", 10).exit_code == 0
        assert test.run("test ! -e /root/.codex/auth.json", 10).exit_code == 0
        # A socket connection is the portable network probe available in the
        # Python-based sandbox image; no external request is made on failure.
        assert test.run("python -c 'import socket; socket.create_connection((\"1.1.1.1\", 53), 1)'", 10).exit_code != 0
        assert confirmation.run("test ! -e /root/.codex/auth.json", 10).exit_code == 0
    finally:
        for container in (setup, agent, test, confirmation):
            container.remove()
