from pathlib import Path

import pytest

from triage.config.settings import Settings
from triage.preflight import DEPENDENCY_GROUP_ERROR, NETWORK_ERROR, PreflightError, require_safe_to_start, run_preflight


def test_isolated_test_policy_keeps_agent_and_test_boundaries_distinct() -> None:
    called = False
    def reader(repository: str):
        nonlocal called; called = True; return "[dependency-groups]"
    result = run_preflight(Settings(TRIAGE_TEST_NETWORK_POLICY="isolated", _env_file=None), "openai/openai-agents-python", reader)
    assert not result.safe_to_start  # dependency groups still need explicit setup
    assert NETWORK_ERROR not in result.errors
    assert called
    assert result.network_policy == "isolated"
    assert result.agent_network_policy == "allowed"


def test_allowed_docker_codex_passes_configuration_gate() -> None:
    result = run_preflight(Settings(TRIAGE_TEST_NETWORK_POLICY="allowed", _env_file=None), "openai/openai-agents-python", lambda _: "[project]\nname = 'demo'")
    assert result.safe_to_start
    assert result.network_policy == "allowed"
    assert result.setup_command == "python -m pip install -e ."


def test_dependency_groups_require_explicit_command() -> None:
    result = run_preflight(Settings(TRIAGE_TEST_NETWORK_POLICY="allowed", _env_file=None), "owner/repo", lambda _: "[dependency-groups]\ntest = ['pytest']")
    assert not result.safe_to_start
    assert result.setup_command == "explicit command required"
    assert DEPENDENCY_GROUP_ERROR in result.errors


def test_explicit_setup_command_takes_precedence_over_dependency_groups() -> None:
    result = run_preflight(Settings(TRIAGE_TEST_NETWORK_POLICY="allowed", sandbox_setup_command="python -m pip install -e . pytest", _env_file=None), "owner/repo", lambda _: "[dependency-groups]")
    assert result.safe_to_start
    assert result.setup_command == "python -m pip install -e . pytest"
    assert result.setup_reason == "explicit SANDBOX_SETUP_COMMAND"


def test_require_safe_to_start_does_not_create_any_local_state_for_dependency_diagnostic(tmp_path) -> None:
    (tmp_path / "pyproject.toml").write_text("[dependency-groups]", encoding="utf-8")
    settings = Settings(TRIAGE_TEST_NETWORK_POLICY="isolated", database_url="sqlite:////definitely-not-created.db", artifacts_dir=Path("/definitely-not-created"), local_repository_path=tmp_path, _env_file=None)
    with pytest.raises(PreflightError, match="dependency-groups"):
        require_safe_to_start(settings, "openai/openai-agents-python")
