from time import perf_counter
from decimal import Decimal
from typing import Protocol

from triage.extraction.client import MODEL, ExtractionResponse, Usage
from triage.extraction.prompts import load_system_prompt, render_user_prompt
from triage.extraction.schema import ExtractionValidationError, validate_extraction_json
from triage.github.models import GitHubIssue
from triage.llm.pricing import OPENAI_PROVIDER, PRICE_BOOK_VERSION, calculate_cost as calculate_priced_cost
from triage.persistence.models import LLMCall


class ExtractionClient(Protocol):
    def extract(self, system_prompt: str, user_prompt: str) -> ExtractionResponse: ...


class LLMCallStore(Protocol):
    def create(self, item: LLMCall) -> LLMCall: ...


class ExtractionFailure(RuntimeError):
    pass


def calculate_cost(usage: Usage):
    """Compatibility wrapper for the configured extraction model tariff."""
    return calculate_priced_cost(MODEL, usage.input_tokens, usage.cached_input_tokens, usage.output_tokens)


class ExtractionService:
    """Executes and records up to two source-bound extraction calls."""

    def __init__(self, client: ExtractionClient, llm_calls: LLMCallStore, investigation_id: str | None = None, budget=None):
        self.client = client
        self.llm_calls = llm_calls
        self.investigation_id = investigation_id
        self.budget = budget

    def extract(self, issue: GitHubIssue) -> "IssueExtraction":
        system_prompt = load_system_prompt()
        user_prompt = render_user_prompt(issue)
        failures: list[str] = []
        for _ in range(2):
            reservation = self.budget.reserve_openai(self.investigation_id) if self.budget and self.investigation_id else None
            started = perf_counter()
            try:
                response = self.client.extract(system_prompt, user_prompt)
            except Exception:
                if reservation is not None:
                    self.budget.reconcile_openai(self.investigation_id, reservation, Decimal("0"))
                raise
            latency_ms = round((perf_counter() - started) * 1000)
            self._record(response, latency_ms)
            if reservation is not None:
                self.budget.reconcile_openai(self.investigation_id, reservation, calculate_cost(response.usage))
            try:
                return validate_extraction_json(response.content)
            except ExtractionValidationError as error:
                failures.append(str(error))
        raise ExtractionFailure("Extraction failed validation after two attempts: " + failures[-1])

    def _record(self, response: ExtractionResponse, latency_ms: int) -> None:
        self.llm_calls.create(
            LLMCall(
                investigation_id=self.investigation_id,
                provider=OPENAI_PROVIDER,
                model=MODEL,
                pricing_version=PRICE_BOOK_VERSION,
                purpose="issue_extraction",
                input_tokens=response.usage.input_tokens,
                cached_input_tokens=response.usage.cached_input_tokens,
                output_tokens=response.usage.output_tokens,
                cost_usd=calculate_cost(response.usage),
                latency_ms=latency_ms,
            )
        )
