"""Read-only safety checks for live investigations."""

from __future__ import annotations

from dataclasses import dataclass, field
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


def run_preflight(settings: Settings, repository: str) -> PreflightResult:
    if "/" not in repository or repository.startswith("/") or repository.endswith("/"):
        raise PreflightError("Repository must use owner/repository form.")
    runner = settings.test_runner if settings.test_runner != "auto" else "auto (resolved during checkout)"
    errors: list[str] = []
    warnings: list[str] = []
    if settings.test_network_policy == "allowed":
        warnings.append("Test network access is explicitly allowed. Focused tests and confirmations will not be network-isolated.")

    if settings.sandbox_setup_command:
        setup_command = settings.sandbox_setup_command
        setup_reason = "explicit SANDBOX_SETUP_COMMAND"
    else:
        setup_command = "resolved during checkout"
        setup_reason = "setup selection occurs after the live checkout; preflight performs no GitHub read"
    warnings.append("Agent provider connectivity is separate from focused test networking.")
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
        "Focused tests and confirmations have no Codex credential mount and use the selected test-network policy.",
        f"Setup command: {result.setup_command}",
        f"Setup selection: {result.setup_reason}",
    ]
    lines.extend(f"Warning: {warning}" for warning in result.warnings)
    lines.extend(f"Error: {error}" for error in result.errors)
    lines.append(f"Safe to start: {'yes' if result.safe_to_start else 'no'}")
    return "\n".join(lines)
