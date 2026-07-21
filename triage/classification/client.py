from dataclasses import dataclass

from openai import OpenAI

from triage.domain.enums import Classification
from triage.providers import OPENAI_CAPABILITIES

MODEL = "gpt-5.6-luna"
LLM_ALLOWED_CLASSIFICATIONS = (
    Classification.NEEDS_INFO,
    Classification.WONT_REPRO,
    Classification.NOT_A_BUG,
)


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class ClassificationResponse:
    content: str
    usage: Usage


class OpenAIClassificationClient:
    identifier = "openai"
    capabilities = OPENAI_CAPABILITIES
    def __init__(self, api_key: str | None, client: OpenAI | None = None):
        self.api_key = api_key
        self.client = client

    def classify(self, system_prompt: str, evidence_prompt: str) -> ClassificationResponse:
        client = self.client or OpenAI(api_key=self.api_key)
        self.client = client
        response = client.responses.create(
            model=MODEL,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": evidence_prompt},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "investigation_classification",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "classification": {
                                "type": "string",
                                "enum": [item.value for item in LLM_ALLOWED_CLASSIFICATIONS],
                            }
                        },
                        "required": ["classification"],
                        "additionalProperties": False,
                    },
                }
            },
        )
        usage = response.usage
        cached_tokens = getattr(getattr(usage, "input_tokens_details", None), "cached_tokens", 0) or 0
        return ClassificationResponse(
            content=response.output_text,
            usage=Usage(
                input_tokens=usage.input_tokens or 0,
                cached_input_tokens=cached_tokens,
                output_tokens=usage.output_tokens or 0,
            ),
        )
