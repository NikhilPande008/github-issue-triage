import pytest
from triage.providers import validate_provider_selection, OPENAI_CAPABILITIES, CODEX_CAPABILITIES

def test_default_provider_capabilities_and_rejects_no_fallback():
 validate_provider_selection("openai","openai","codex",None)
 assert OPENAI_CAPABILITIES.structured_output and CODEX_CAPABILITIES.sandbox_compatible
 with pytest.raises(ValueError,match="Unsupported extraction provider"): validate_provider_selection("other","openai","codex",None)
 with pytest.raises(ValueError,match="Unsupported investigation-agent"): validate_provider_selection("openai","openai","other",None)
