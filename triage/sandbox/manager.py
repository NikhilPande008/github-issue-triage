import logging
from dataclasses import dataclass
from pathlib import Path
from time import monotonic

import docker

from triage.sandbox.container import ContainerCommandResult, DockerSandboxContainer, SandboxTimeout
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


def resolve_setup_command(repository_path: Path, configured_command: str | None) -> SetupCommand:
    """Choose one setup strategy.  Installation failures must never trigger fallback."""
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
    container: DockerSandboxContainer
    image_id: str
    run_id: str
    started_at: float

    def cleanup(self) -> None:
        container_removed = False
        workspace_deleted = False
        try:
            self.container.remove()
            container_removed = True
        finally:
            self.workspace.delete()
            workspace_deleted = not self.workspace.root.exists()
            logger.info(
                "sandbox cleanup complete",
                extra={
                    "run_id": self.run_id,
                    "container_id": self.container.id,
                    "workspace_path": str(self.workspace.root),
                    "duration_ms": round((monotonic() - self.started_at) * 1000),
                    "container_removed": container_removed,
                    "workspace_deleted": workspace_deleted,
                },
            )


class SandboxManager:
    def __init__(self, workspace_root: Path, image_name: str, dependency_timeout_seconds: int, overall_timeout_seconds: int, auth_path: Path, docker_client=None, setup_command: str | None = None):
        self.workspace_root = workspace_root
        self.image_name = image_name
        self.dependency_timeout_seconds = dependency_timeout_seconds
        self.overall_timeout_seconds = overall_timeout_seconds
        self.auth_path = auth_path
        self.docker_client = docker_client or docker.from_env()
        self.setup_command = setup_command

    def create(self, run_id: str, repository: str) -> Sandbox:
        workspace = SandboxWorkspace.create(self.workspace_root, run_id, repository)
        container = None
        try:
            setup = resolve_setup_command(workspace.repository_path, self.setup_command)
            image = ensure_image(self.docker_client, self.image_name)
            container = DockerSandboxContainer.start(
                self.docker_client, image, workspace.repository_path, self.auth_path, self.overall_timeout_seconds
            )
            sandbox = Sandbox(workspace, container, image.id, run_id, monotonic())
            logger.info(
                "sandbox created",
                extra={"run_id": run_id, "container_id": container.id, "image_id": image.id, "workspace_path": str(workspace.root)},
            )
            try:
                result = container.run(setup.command, self.dependency_timeout_seconds)
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
            return sandbox
        except Exception:
            if container is not None:
                container.remove()
            workspace.delete()
            raise
