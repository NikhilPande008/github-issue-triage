from triage.config.settings import Settings
from triage.preflight import NETWORK_ERROR, run_preflight


def test_isolated_test_policy_keeps_agent_and_test_boundaries_distinct() -> None:
    result = run_preflight(Settings(TRIAGE_TEST_NETWORK_POLICY="isolated", _env_file=None), "openai/openai-agents-python")
    assert result.safe_to_start
    assert NETWORK_ERROR not in result.errors
    assert result.network_policy == "isolated"
    assert result.agent_network_policy == "allowed"
    assert "no GitHub read" in result.setup_reason


def test_allowed_docker_codex_passes_configuration_gate() -> None:
    result = run_preflight(Settings(TRIAGE_TEST_NETWORK_POLICY="allowed", _env_file=None), "openai/openai-agents-python")
    assert result.safe_to_start
    assert result.network_policy == "allowed"
    assert result.setup_command == "resolved during checkout"


def test_explicit_setup_command_takes_precedence_over_dependency_groups() -> None:
    result = run_preflight(Settings(TRIAGE_TEST_NETWORK_POLICY="allowed", sandbox_setup_command="python -m pip install -e . pytest", _env_file=None), "owner/repo")
    assert result.safe_to_start
    assert result.setup_command == "python -m pip install -e . pytest"
    assert result.setup_reason == "explicit SANDBOX_SETUP_COMMAND"
