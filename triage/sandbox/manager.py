import logging
from dataclasses import dataclass
from pathlib import Path
from time import monotonic

import docker

from triage.sandbox.container import ContainerCommandResult, ContainerRole, DockerSandboxContainer, SandboxTimeout
from triage.sandbox.images import ensure_image
from triage.sandbox.workspace import SandboxWorkspace

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SetupCommand:
    command: str
    reason: str


class EnvironmentSetupFailure(RuntimeError):
    """A repository could not be prepared, before any issue evidence was run."""

    def __init__(self, message: str, setup: SetupCommand | None = None, output: str = ""):
        super().__init__(message)
        self.setup = setup
        self.output = output
        self.execution = None


def resolve_setup_command(repository_path: Path, configured_command: str | None, runner=None) -> SetupCommand:
    """Choose one setup strategy.  Installation failures must never trigger fallback."""
    if runner is not None:
        return runner.setup_command(repository_path, configured_command)
    if configured_command:
        return SetupCommand(configured_command, "explicit SANDBOX_SETUP_COMMAND")
    if (repository_path / "requirements-dev.txt").is_file():
        return SetupCommand("python -m pip install -r requirements-dev.txt", "requirements-dev.txt")
    if (repository_path / "requirements.txt").is_file():
        return SetupCommand("python -m pip install -r requirements.txt", "requirements.txt")
    for name in ("pyproject.toml", "setup.py", "setup.cfg"):
        if (repository_path / name).is_file():
            return SetupCommand("python -m pip install -e .", f"Python packaging metadata ({name})")
    raise EnvironmentSetupFailure(
        "Environment setup unavailable: no requirements-dev.txt, requirements.txt, or Python package metadata found"
    )


@dataclass
class Sandbox:
    workspace: SandboxWorkspace
    agent_container: DockerSandboxContainer | None
    test_container: DockerSandboxContainer | None
    image_id: str
    prepared_image: object
    run_id: str
    started_at: float
    setup: SetupCommand | None = None
    network_policy: str = "isolated"
    manifest_base: dict | None = None

    def cleanup(self) -> None:
        container_removed = False
        workspace_deleted = False
        try:
            for container in (self.agent_container, self.test_container):
                if container is not None:
                    container.remove()
                    container_removed = True
        finally:
            self.workspace.delete()
            workspace_deleted = not self.workspace.root.exists()
            logger.info(
                "sandbox cleanup complete",
                extra={
                    "run_id": self.run_id,
                    "container_id": self.test_container.id if self.test_container is not None else (self.agent_container.id if self.agent_container is not None else None),
                    "workspace_path": str(self.workspace.root),
                    "duration_ms": round((monotonic() - self.started_at) * 1000),
                    "container_removed": container_removed,
                    "workspace_deleted": workspace_deleted,
                },
            )


class SandboxManager:
    def __init__(self, workspace_root: Path, image_name: str, dependency_timeout_seconds: int, overall_timeout_seconds: int, auth_path: Path, docker_client=None, setup_command: str | None = None, test_runner: str = "pytest", network_policy: str = "isolated", agent_network_policy: str = "allowed", confirmation_runs: int = 2):
        self.workspace_root = workspace_root
        self.image_name = image_name
        self.dependency_timeout_seconds = dependency_timeout_seconds
        self.overall_timeout_seconds = overall_timeout_seconds
        self.auth_path = auth_path
        self.docker_client = docker_client or docker.from_env()
        self.setup_command = setup_command
        self.test_runner = test_runner
        self.network_policy = network_policy
        self.agent_network_policy = agent_network_policy
        self.confirmation_runs = confirmation_runs

    def create(self, run_id: str, repository: str) -> Sandbox:
        workspace = SandboxWorkspace.create(self.workspace_root, run_id, repository)
        setup_container = agent_container = None
        try:
            from triage.runners import select_runner
            runner = select_runner(self.test_runner, workspace.repository_path)
            setup = resolve_setup_command(workspace.repository_path, self.setup_command, runner)
            image = ensure_image(self.docker_client, self.image_name)
            setup_container = DockerSandboxContainer.start(self.docker_client, image, workspace.repository_path, self.auth_path, self.overall_timeout_seconds, ContainerRole.SETUP, "allowed")
            logger.info(
                "sandbox created",
                extra={"run_id": run_id, "container_id": setup_container.id, "image_id": image.id, "workspace_path": str(workspace.root)},
            )
            try:
                result = setup_container.run(setup.command, self.dependency_timeout_seconds)
            except SandboxTimeout as error:
                raise EnvironmentSetupFailure(
                    f"Environment setup failed: {setup.reason} installation timed out",
                    setup,
                    str(error),
                ) from error
            if isinstance(result, ContainerCommandResult) and result.exit_code != 0:
                raise EnvironmentSetupFailure(
                    f"Environment setup failed: {setup.reason} installation exited {result.exit_code}",
                    setup,
                    result.output,
                )
            prepared_image = setup_container.commit()
            setup_container.remove(); setup_container = None
            agent_container = DockerSandboxContainer.start(self.docker_client, prepared_image, workspace.repository_path, self.auth_path, self.overall_timeout_seconds, ContainerRole.AGENT, self.agent_network_policy)
            sandbox = Sandbox(workspace, agent_container, None, image.id, prepared_image, run_id, monotonic(), setup, self.network_policy)
            sandbox.runner = runner
            sandbox.manifest_base = self._manifest_base(workspace.repository_path, repository, image, runner, setup, agent_container)
            return sandbox
        except Exception:
            for container in (setup_container, agent_container):
                if container is not None:
                    container.remove()
            workspace.delete()
            raise

    def create_test_container(self, sandbox: Sandbox) -> DockerSandboxContainer:
        if sandbox.test_container is None:
            sandbox.test_container = DockerSandboxContainer.start(
                self.docker_client, sandbox.prepared_image, sandbox.workspace.repository_path,
                self.auth_path, self.overall_timeout_seconds, ContainerRole.TEST, self.network_policy,
            )
        return sandbox.test_container

    def create_agent_container(self, sandbox: Sandbox) -> DockerSandboxContainer:
        """Restore the required agent role only while an investigation attempt starts.

        This is deliberately separate from test-container creation: confirmation
        executions never call this method and therefore cannot regain the Codex
        credential mount.
        """
        if sandbox.agent_container is None:
            sandbox.agent_container = DockerSandboxContainer.start(
                self.docker_client, sandbox.prepared_image, sandbox.workspace.repository_path,
                self.auth_path, self.overall_timeout_seconds, ContainerRole.AGENT,
                self.agent_network_policy,
            )
        return sandbox.agent_container

    def close_agent_container(self, sandbox: Sandbox) -> None:
        if sandbox.agent_container is not None:
            sandbox.agent_container.remove()
            sandbox.agent_container = None

    def _manifest_base(self, repository_path: Path, repository: str, image, runner, setup: SetupCommand, container) -> dict:
        def command(value: str) -> str:
            try:
                return container.run(value, min(30, self.dependency_timeout_seconds)).output
            except Exception as error:
                return f"unavailable: {error}"
        from hashlib import sha256
        import platform
        commit = command("git rev-parse HEAD").strip()
        lockfile = repository_path / "package-lock.json"
        return {
            "repository": repository,
            "repository_commit": commit or "unavailable",
            "runner": runner.id,
            "sandbox_image_id": getattr(image, "id", None),
            "sandbox_image_digests": getattr(image, "attrs", {}).get("RepoDigests", []),
            "operating_system": platform.platform(),
            "runtime": command("python --version; node --version; npm --version").strip(),
            "setup_command": setup.command,
            "setup_reason": setup.reason,
            "dependency_snapshot": command("pip freeze; printf '\\n-- node --\\n'; npm ls --all --json 2>/dev/null || true"),
            "lockfile_sha256": sha256(lockfile.read_bytes()).hexdigest() if lockfile.is_file() else None,
            "network_policy": self.network_policy,
            "phase_boundaries": {
                "setup": {"network_policy": "allowed", "auth_mount": False},
                "agent": {"network_policy": self.agent_network_policy, "auth_mount": True},
                "test": {"network_policy": self.network_policy, "auth_mount": False},
            },
            "confirmation_boundary": {
                "container_role": "test",
                "network_policy": self.network_policy,
                "auth_mount": False,
                "codex_invocation": False,
            },
            "confirmation_runs": self.confirmation_runs,
            "timeouts": {"dependency_seconds": self.dependency_timeout_seconds, "overall_seconds": self.overall_timeout_seconds},
        }
