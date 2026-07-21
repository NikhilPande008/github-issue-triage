import json
from time import perf_counter
from typing import Protocol

from pydantic import BaseModel, ConfigDict, ValidationError

from triage.classification.client import LLM_ALLOWED_CLASSIFICATIONS, MODEL, ClassificationResponse, Usage
from triage.classification.models import ClassificationEvidence
from triage.classification.prompts import load_system_prompt, render_evidence_prompt
from triage.domain.enums import Classification
from triage.llm.pricing import OPENAI_PROVIDER, PRICE_BOOK_VERSION, calculate_cost as calculate_priced_cost
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


def calculate_cost(usage: Usage):
    return calculate_priced_cost(MODEL, usage.input_tokens, usage.cached_input_tokens, usage.output_tokens)


class ClassificationService:
    """Classifies only validated execution evidence, never issue narrative."""

    def __init__(self, client: ClassificationClient, llm_calls: LLMCallStore, investigation_id: str | None = None, budget=None):
        self.client = client
        self.llm_calls = llm_calls
        self.investigation_id = investigation_id
        self.budget = budget

    def classify(self, evidence: ClassificationEvidence) -> Classification:
        if evidence.asserts_failure:
            return Classification.BEHAVIOR_GAP_CONFIRMED

        system_prompt = load_system_prompt()
        evidence_prompt = render_evidence_prompt(evidence)
        failures: list[str] = []
        for _ in range(2):
            reservation = self.budget.reserve_openai(self.investigation_id) if self.budget and self.investigation_id else None
            started = perf_counter()
            try:
                response = self.client.classify(system_prompt, evidence_prompt)
            except Exception:
                if reservation is not None:
                    from decimal import Decimal
                    self.budget.reconcile_openai(self.investigation_id, reservation, Decimal("0"))
                raise
            latency_ms = round((perf_counter() - started) * 1000)
            self._record(response, latency_ms)
            if reservation is not None:
                self.budget.reconcile_openai(self.investigation_id, reservation, calculate_cost(response.usage))
            try:
                classification = _ClassificationOutput.model_validate_json(response.content).classification
                self._validate_allowed(classification)
                return classification
            except (ValidationError, ValueError) as error:
                failures.append(str(error))
        raise ClassificationFailure("Classification failed validation after two attempts: " + failures[-1])

    @staticmethod
    def _validate_allowed(classification: Classification) -> None:
        if classification not in LLM_ALLOWED_CLASSIFICATIONS:
            raise ValueError(f"{classification.value} is unsupported without its required evidence")

    def _record(self, response: ClassificationResponse, latency_ms: int) -> None:
        self.llm_calls.create(
            LLMCall(
                investigation_id=self.investigation_id,
                provider=OPENAI_PROVIDER,
                model=MODEL,
                pricing_version=PRICE_BOOK_VERSION,
                purpose="evidence_classification",
                input_tokens=response.usage.input_tokens,
                cached_input_tokens=response.usage.cached_input_tokens,
                output_tokens=response.usage.output_tokens,
                cost_usd=calculate_cost(response.usage),
                latency_ms=latency_ms,
            )
        )
