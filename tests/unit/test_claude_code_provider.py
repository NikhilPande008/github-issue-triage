import pytest
from triage.sandbox.claude_code import ClaudeCodeInvestigationAgentProvider

class Manager: network_policy="isolated"
def test_claude_code_fails_before_work_without_required_config():
 provider=ClaudeCodeInvestigationAgentProvider(Manager(),"owner/repo",30,"")
 with pytest.raises(ValueError,match="CLAUDE_CODE_COMMAND"):provider.validate()
 provider=ClaudeCodeInvestigationAgentProvider(Manager(),"owner/repo",30,"claude")
 with pytest.raises(ValueError,match="NETWORK"):provider.validate()
