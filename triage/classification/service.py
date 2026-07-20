import json
from decimal import Decimal, ROUND_HALF_UP
from time import perf_counter
from typing import Protocol

from pydantic import BaseModel, ConfigDict, ValidationError

from triage.classification.client import MODEL, ClassificationResponse, Usage
from triage.classification.models import ClassificationEvidence
from triage.classification.prompts import load_system_prompt, render_evidence_prompt
from triage.domain.enums import Classification
from triage.persistence.models import LLMCall


class ClassificationClient(Protocol):
    def classify(self, system_prompt: str, evidence_prompt: str) -> ClassificationResponse: ...


class LLMCallStore(Protocol):
    def create(self, item: LLMCall) -> LLMCall: ...


class ClassificationFailure(RuntimeError):
    pass


class _ClassificationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    classification: Classification


def calculate_cost(usage: Usage) -> Decimal:
    uncached = usage.input_tokens - usage.cached_input_tokens
    if uncached < 0:
        raise ValueError("cached input tokens cannot exceed input tokens")
    cost = (
        Decimal(uncached) * Decimal("1.00")
        + Decimal(usage.cached_input_tokens) * Decimal("0.10")
        + Decimal(usage.output_tokens) * Decimal("6.00")
    ) / Decimal("1000000")
    return cost.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


class ClassificationService:
    """Classifies only validated execution evidence, never issue narrative."""

    def __init__(self, client: ClassificationClient, llm_calls: LLMCallStore):
        self.client = client
        self.llm_calls = llm_calls

    def classify(self, evidence: ClassificationEvidence) -> Classification:
        if evidence.asserts_failure:
            return Classification.REPRODUCED

        system_prompt = load_system_prompt()
        evidence_prompt = render_evidence_prompt(evidence)
        failures: list[str] = []
        for _ in range(2):
            started = perf_counter()
            response = self.client.classify(system_prompt, evidence_prompt)
            latency_ms = round((perf_counter() - started) * 1000)
            self._record(response, latency_ms)
            try:
                classification = _ClassificationOutput.model_validate_json(response.content).classification
                self._validate_allowed(classification)
                return classification
            except (ValidationError, ValueError) as error:
                failures.append(str(error))
        raise ClassificationFailure("Classification failed validation after two attempts: " + failures[-1])

    @staticmethod
    def _validate_allowed(classification: Classification) -> None:
        if classification in {Classification.REPRODUCED, Classification.DUPLICATE}:
            raise ValueError(f"{classification.value} is unsupported without its required evidence")

    def _record(self, response: ClassificationResponse, latency_ms: int) -> None:
        self.llm_calls.create(
            LLMCall(
                investigation_id=None,
                model=MODEL,
                purpose="evidence_classification",
                input_tokens=response.usage.input_tokens,
                cached_input_tokens=response.usage.cached_input_tokens,
                output_tokens=response.usage.output_tokens,
                cost_usd=calculate_cost(response.usage),
                latency_ms=latency_ms,
            )
        )
