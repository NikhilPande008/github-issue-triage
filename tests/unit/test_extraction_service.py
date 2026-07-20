from dataclasses import dataclass
from decimal import Decimal

import pytest

from triage.extraction.client import ExtractionResponse, Usage
from triage.extraction.service import ExtractionFailure, ExtractionService, calculate_cost
from triage.github.models import GitHubIssue

VALID_EXTRACTION = """{
  "summary": "Failure",
  "steps_to_reproduce": [],
  "expected_behavior": null,
  "actual_behavior": null,
  "environment": {},
  "affected_area": null,
  "repro_code": null,
  "missing_info": ["Steps"],
  "confidence": 0.4
}"""


@dataclass
class FakeClient:
    contents: list[str]

    def extract(self, system_prompt: str, user_prompt: str) -> ExtractionResponse:
        return ExtractionResponse(self.contents.pop(0), Usage(100, 20, 10))


class FakeStore:
    def __init__(self) -> None:
        self.items = []

    def create(self, item):
        self.items.append(item)
        return item


def issue() -> GitHubIssue:
    return GitHubIssue(
        repository="psf/requests",
        issue_number=123,
        title="Failure",
        body="Details",
        author="reporter",
        labels=[],
        comments=[],
        state="open",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        url="https://github.com/psf/requests/issues/123",
    )


def test_service_retries_once_after_validation_failure_and_records_each_call() -> None:
    store = FakeStore()
    extraction = ExtractionService(FakeClient(["not json", VALID_EXTRACTION]), store).extract(issue())

    assert extraction.summary == "Failure"
    assert len(store.items) == 2
    assert store.items[0].investigation_id is None
    assert store.items[0].latency_ms >= 0


def test_service_raises_explicit_failure_after_second_invalid_response() -> None:
    store = FakeStore()
    with pytest.raises(ExtractionFailure, match="after two attempts"):
        ExtractionService(FakeClient(["not json", "also not json"]), store).extract(issue())
    assert len(store.items) == 2


def test_luna_cost_uses_cached_input_discount() -> None:
    assert calculate_cost(Usage(100, 20, 10)) == Decimal("0.000142")
