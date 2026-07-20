from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
from typing import Literal


class Settings(BaseSettings):
    """Process configuration loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openai_api_key: str | None = None
    github_token: str | None = None
    demo_repository: str = "psf/requests"
    database_url: str = "sqlite:///triage.db"
    log_level: str = "INFO"
    local_repository_path: Path = Path("repo")
    artifacts_dir: Path = Path("artifacts")
    investigation_runner: Literal["docker", "local"] = "docker"
    sandbox_workspace_dir: Path = Path("sandbox-workspaces")
    sandbox_image: str = "github-issue-triage:latest"
    dependency_install_timeout_seconds: int = 600
    sandbox_setup_command: str = "python -m pip install --upgrade pip && python -m pip install -r requirements-dev.txt"
    pytest_timeout_seconds: int = 300
    investigation_timeout_seconds: int = 900
    codex_auth_path: Path = Path.home() / ".codex" / "auth.json"
