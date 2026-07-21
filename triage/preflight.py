"""Read-only safety checks for live investigations."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from triage.config.settings import Settings


class PreflightError(RuntimeError):
    pass


@dataclass(frozen=True)
class PreflightResult:
    repository: str
    runner: str
    network_policy: str
    agent_network_policy: str
    setup_command: str
    setup_reason: str
    safe_to_start: bool
    warnings: tuple[str, ...] = field(default_factory=tuple)
    errors: tuple[str, ...] = field(default_factory=tuple)


NETWORK_ERROR = "Codex requires provider connectivity during the separate agent phase."
DEPENDENCY_GROUP_ERROR = (
    "This repository declares [dependency-groups], but the sandbox pip cannot consume "
    "pip install --group. Set an explicit repository-owned SANDBOX_SETUP_COMMAND; no "
    "dependency group or package list was inferred."
)


def fetch_public_pyproject(repository: str) -> str | None:
    """Read public metadata only; never authenticates or modifies GitHub."""
    url = f"https://raw.githubusercontent.com/{repository}/HEAD/pyproject.toml"
    try:
        with urlopen(url, timeout=10) as response:  # noqa: S310 - fixed public GitHub URL
            return response.read().decode("utf-8", errors="replace")
    except (OSError, URLError):
        return None


def has_dependency_groups(pyproject: str | None) -> bool:
    return bool(pyproject and any(line.strip() == "[dependency-groups]" for line in pyproject.splitlines()))


def run_preflight(settings: Settings, repository: str, metadata_reader=fetch_public_pyproject) -> PreflightResult:
    if "/" not in repository or repository.startswith("/") or repository.endswith("/"):
        raise PreflightError("Repository must use owner/repository form.")
    runner = settings.test_runner if settings.test_runner != "auto" else "auto (resolved during checkout)"
    errors: list[str] = []
    warnings: list[str] = []
    if settings.test_network_policy == "allowed":
        warnings.append("Test network access is explicitly allowed. Focused tests and confirmations will not be network-isolated.")

    pyproject = _local_pyproject(settings.local_repository_path) or metadata_reader(repository)
    if settings.sandbox_setup_command:
        setup_command = settings.sandbox_setup_command
        setup_reason = "explicit SANDBOX_SETUP_COMMAND"
    elif has_dependency_groups(pyproject):
        setup_command = "explicit command required"
        setup_reason = "[dependency-groups] detected"
        errors.append(DEPENDENCY_GROUP_ERROR)
    elif pyproject is not None:
        setup_command = "python -m pip install -e ."
        setup_reason = "Python packaging metadata (pyproject.toml)"
    else:
        setup_command = "resolved during checkout"
        setup_reason = "public pyproject.toml unavailable; actual setup selection still occurs after checkout"
        warnings.append("Could not read public pyproject.toml; no dependency-group diagnostic was available.")
    return PreflightResult(repository, runner, settings.test_network_policy, settings.agent_network_policy, setup_command, setup_reason, not errors, tuple(warnings), tuple(errors))


def require_safe_to_start(settings: Settings, repository: str) -> PreflightResult:
    result = run_preflight(settings, repository)
    if not result.safe_to_start:
        raise PreflightError("\n".join(result.errors))
    return result


def format_result(result: PreflightResult) -> str:
    lines = [
        "Live investigation preflight",
        f"Repository: {result.repository}",
        f"Selected runner: {result.runner}",
        f"Network policy: {result.network_policy}",
        f"Agent network policy: {result.agent_network_policy} (provider connectivity)",
        "Focused tests and confirmations have no agent credential mount; test networking is independent.",
        f"Setup command: {result.setup_command}",
        f"Setup selection: {result.setup_reason}",
    ]
    lines.extend(f"Warning: {warning}" for warning in result.warnings)
    lines.extend(f"Error: {error}" for error in result.errors)
    lines.append(f"Safe to start: {'yes' if result.safe_to_start else 'no'}")
    return "\n".join(lines)


def _local_pyproject(path: Path) -> str | None:
    try:
        return (path / "pyproject.toml").read_text(encoding="utf-8")
    except OSError:
        return None
