from types import SimpleNamespace

from triage.classification.client import MODEL, OpenAIClassificationClient


def test_openai_classification_client_uses_strict_schema() -> None:
    captured = {}

    class FakeResponses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                output_text='{"classification":"NEEDS_INFO"}',
                usage=SimpleNamespace(
                    input_tokens=12,
                    output_tokens=3,
                    input_tokens_details=SimpleNamespace(cached_tokens=4),
                ),
            )

    response = OpenAIClassificationClient(None, client=SimpleNamespace(responses=FakeResponses())).classify("system", "evidence")

    assert captured["model"] == MODEL
    assert captured["text"]["format"]["strict"] is True
    assert captured["text"]["format"]["schema"]["additionalProperties"] is False
    assert "BEHAVIOR_GAP_CONFIRMED" not in captured["text"]["format"]["schema"]["properties"]["classification"]["enum"]
    assert response.usage.cached_input_tokens == 4
