from decimal import Decimal, ROUND_HALF_UP
from time import perf_counter
from typing import Protocol

from triage.extraction.client import MODEL, ExtractionResponse, Usage
from triage.extraction.prompts import load_system_prompt, render_user_prompt
from triage.extraction.schema import ExtractionValidationError, validate_extraction_json
from triage.github.models import GitHubIssue
from triage.persistence.models import LLMCall


class ExtractionClient(Protocol):
    def extract(self, system_prompt: str, user_prompt: str) -> ExtractionResponse: ...


class LLMCallStore(Protocol):
    def create(self, item: LLMCall) -> LLMCall: ...


class ExtractionFailure(RuntimeError):
    pass


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


class ExtractionService:
    """Executes and records up to two source-bound extraction calls."""

    def __init__(self, client: ExtractionClient, llm_calls: LLMCallStore):
        self.client = client
        self.llm_calls = llm_calls

    def extract(self, issue: GitHubIssue) -> "IssueExtraction":
        system_prompt = load_system_prompt()
        user_prompt = render_user_prompt(issue)
        failures: list[str] = []
        for _ in range(2):
            started = perf_counter()
            response = self.client.extract(system_prompt, user_prompt)
            latency_ms = round((perf_counter() - started) * 1000)
            self._record(response, latency_ms)
            try:
                return validate_extraction_json(response.content)
            except ExtractionValidationError as error:
                failures.append(str(error))
        raise ExtractionFailure("Extraction failed validation after two attempts: " + failures[-1])

    def _record(self, response: ExtractionResponse, latency_ms: int) -> None:
        self.llm_calls.create(
            LLMCall(
                investigation_id=None,
                model=MODEL,
                purpose="issue_extraction",
                input_tokens=response.usage.input_tokens,
                cached_input_tokens=response.usage.cached_input_tokens,
                output_tokens=response.usage.output_tokens,
                cost_usd=calculate_cost(response.usage),
                latency_ms=latency_ms,
            )
        )
