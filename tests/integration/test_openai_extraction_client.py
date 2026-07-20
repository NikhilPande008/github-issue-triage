from types import SimpleNamespace

from triage.extraction.client import MODEL, OpenAIExtractionClient


class FakeResponses:
    def __init__(self, content: str):
        self.content = content
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            output_text=self.content,
            usage=SimpleNamespace(
                input_tokens=12,
                output_tokens=3,
                input_tokens_details=SimpleNamespace(cached_tokens=4),
            ),
        )


def test_openai_client_uses_luna_and_json_object_mode() -> None:
    responses = FakeResponses('{"summary": null}')
    client = OpenAIExtractionClient(None, client=SimpleNamespace(responses=responses))

    response = client.extract("system", "user")

    assert response.content == '{"summary": null}'
    assert response.usage.cached_input_tokens == 4
    assert responses.calls[0]["model"] == MODEL
    assert responses.calls[0]["text"]["format"] == {"type": "json_object"}
