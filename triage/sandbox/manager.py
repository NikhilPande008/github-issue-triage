import logging
from dataclasses import dataclass
from pathlib import Path
from time import monotonic

import docker

from triage.sandbox.container import DockerSandboxContainer
from triage.sandbox.images import ensure_image
from triage.sandbox.workspace import SandboxWorkspace

logger = logging.getLogger(__name__)


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
    def __init__(self, workspace_root: Path, image_name: str, dependency_timeout_seconds: int, overall_timeout_seconds: int, auth_path: Path, docker_client=None):
        self.workspace_root = workspace_root
        self.image_name = image_name
        self.dependency_timeout_seconds = dependency_timeout_seconds
        self.overall_timeout_seconds = overall_timeout_seconds
        self.auth_path = auth_path
        self.docker_client = docker_client or docker.from_env()

    def create(self, run_id: str, repository: str) -> Sandbox:
        workspace = SandboxWorkspace.create(self.workspace_root, run_id, repository)
        container = None
        try:
            image = ensure_image(self.docker_client, self.image_name)
            container = DockerSandboxContainer.start(
                self.docker_client, image, workspace.repository_path, self.auth_path, self.overall_timeout_seconds
            )
            sandbox = Sandbox(workspace, container, image.id, run_id, monotonic())
            logger.info(
                "sandbox created",
                extra={"run_id": run_id, "container_id": container.id, "image_id": image.id, "workspace_path": str(workspace.root)},
            )
            container.run("python -m pip install --upgrade pip && python -m pip install -r requirements-dev.txt", self.dependency_timeout_seconds)
            return sandbox
        except Exception:
            if container is not None:
                container.remove()
            workspace.delete()
            raise
