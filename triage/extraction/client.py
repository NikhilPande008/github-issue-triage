from dataclasses import dataclass

from openai import OpenAI

from triage.domain.models import IssueExtraction

MODEL = "gpt-5.6-luna"


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class ExtractionResponse:
    content: str
    usage: Usage


class OpenAIExtractionClient:
    """OpenAI Responses API adapter for the extraction-only model call."""

    def __init__(self, api_key: str | None, client: OpenAI | None = None):
        if not api_key and client is None:
            raise ValueError("OPENAI_API_KEY is required for extraction")
        self.client = client or OpenAI(api_key=api_key)

    def extract(self, system_prompt: str, user_prompt: str) -> ExtractionResponse:
        response = self.client.responses.create(
            model=MODEL,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            text={
                "format": {
                    "type": "json_object",
                }
            },
        )
        usage = response.usage
        cached_tokens = getattr(getattr(usage, "input_tokens_details", None), "cached_tokens", 0) or 0
        return ExtractionResponse(
            content=response.output_text,
            usage=Usage(
                input_tokens=usage.input_tokens,
                cached_input_tokens=cached_tokens,
                output_tokens=usage.output_tokens,
            ),
        )
