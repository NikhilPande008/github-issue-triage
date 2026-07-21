from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AliasChoices, Field
from decimal import Decimal
from pathlib import Path
from typing import Literal


class Settings(BaseSettings):
    """Process configuration loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openai_api_key: str | None = None
    github_token: str | None = None
    # Webhook/commenting are deliberately opt-in.  A token should normally be a
    # short-lived GitHub App installation token with Issues: read/write access.
    github_webhook_secret: str | None = None
    webhook_allowed_repositories: str = ""
    github_auto_post_enabled: bool = False
    github_auto_post_repositories: str = ""
    github_auto_post_dry_run: bool = True
    worker_concurrency: int = 1
    worker_per_repository_concurrency: int = 1
    worker_queue_limit: int = 100
    worker_lease_seconds: int = 1800
    worker_max_attempts: int = 3
    confirmation_runs: int = Field(default=2, validation_alias=AliasChoices("TRIAGE_CONFIRMATION_RUNS", "CONFIRMATION_RUNS"))
    test_network_policy: Literal["isolated", "allowed"] = Field(default="isolated", validation_alias=AliasChoices("TRIAGE_TEST_NETWORK_POLICY", "TEST_NETWORK_POLICY"))
    agent_network_policy: Literal["allowed"] = "allowed"
    live_demo_enabled: bool = False
    live_demo_repositories: str = ""
    live_demo_allowed_issue_numbers: str = ""
    live_demo_request_token: str | None = None
    live_demo_max_concurrent_runs: int = 1
    live_demo_max_issues_per_session: int = 1
    budget_openai_per_investigation_usd: Decimal | None = Decimal("1.00")
    budget_openai_repository_daily_usd: Decimal | None = Decimal("20.00")
    budget_openai_repository_monthly_usd: Decimal | None = Decimal("100.00")
    budget_openai_reservation_usd: Decimal = Decimal("0.10")
    budget_codex_per_investigation_seconds: int = 900
    budget_codex_repository_daily_seconds: int | None = 3600
    duplicate_detection_enabled: bool = True
    duplicate_similarity_threshold: float = 0.75
    duplicate_embedding_provider: str | None = None
    duplicate_embedding_model: str | None = None
    extraction_provider: Literal["openai"] = "openai"
    classification_provider: Literal["openai"] = "openai"
    investigation_agent_provider: Literal["codex", "claude_code"] = "codex"
    claude_code_command: str | None = None
    claude_code_model: str | None = None
    pilot_review_enabled: bool = False
    # JSON map: {"reviewer-id": {"cohort": "MAINTAINER", "token": "..."}}.
    # This is an internal-pilot credential registry, not an SSO/RBAC system.
    pilot_reviewer_registry: str = "{}"
    posting_approval_ttl_seconds: int = 86400
    pilot_session_ttl_seconds: int = 28_800
    pilot_session_secure_cookie: bool = True
    pilot_telemetry_retention_days: int = 90
    pilot_review_idle_timeout_seconds: int = 900
    demo_repository: str = "psf/requests"
    database_url: str = "sqlite:///triage.db"
    log_level: str = "INFO"
    local_repository_path: Path = Path("repo")
    artifacts_dir: Path = Path("artifacts")
    investigation_runner: Literal["docker", "local"] = "docker"
    test_runner: Literal["pytest", "vitest", "auto"] = "pytest"
    sandbox_workspace_dir: Path = Path("sandbox-workspaces")
    sandbox_image: str = "github-issue-triage:latest"
    dependency_install_timeout_seconds: int = 600
    # When unset, the sandbox selects a supported dependency manifest from the
    # checked-out repository.  A configured value is intentionally authoritative.
    sandbox_setup_command: str | None = None
    pytest_timeout_seconds: int = 300
    investigation_timeout_seconds: int = 900
    codex_auth_path: Path = Path.home() / ".codex" / "auth.json"

    def repository_allowlist(self) -> set[str]:
        return {item.strip().lower() for item in self.webhook_allowed_repositories.split(",") if item.strip()}

    def auto_post_allowlist(self) -> set[str]:
        return {item.strip().lower() for item in self.github_auto_post_repositories.split(",") if item.strip()}

    def live_demo_repository_allowlist(self) -> set[str]:
        return {item.strip().lower() for item in self.live_demo_repositories.split(",") if item.strip()}

    def live_demo_issue_allowlist(self) -> set[int]:
        values: set[int] = set()
        for item in self.live_demo_allowed_issue_numbers.split(","):
            try:
                if item.strip(): values.add(int(item.strip()))
            except ValueError:
                continue
        return values
