import shutil
from dataclasses import dataclass
from pathlib import Path

from git import Repo


@dataclass(frozen=True)
class SandboxWorkspace:
    root: Path
    repository_path: Path

    @classmethod
    def create(cls, workspaces_root: Path, run_id: str, repository: str) -> "SandboxWorkspace":
        root = (workspaces_root / f"run_{run_id}").resolve()
        repository_path = root / "repository"
        root.mkdir(parents=True, exist_ok=False)
        try:
            Repo.clone_from(f"https://github.com/{repository}.git", repository_path, depth=1)
        except Exception:
            shutil.rmtree(root, ignore_errors=True)
            raise
        return cls(root=root, repository_path=repository_path)

    def delete(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)
