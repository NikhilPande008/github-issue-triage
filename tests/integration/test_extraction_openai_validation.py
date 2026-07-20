from types import SimpleNamespace

import pytest

from triage.extraction.client import OpenAIExtractionClient
from triage.extraction.service import ExtractionFailure, ExtractionService
from triage.github.models import GitHubIssue


class FakeStore:
    def __init__(self) -> None:
        self.items = []

    def create(self, item):
        self.items.append(item)
        return item


class FakeResponses:
    def __init__(self, contents: list[str]):
        self.contents = contents

    def create(self, **kwargs):
        return SimpleNamespace(
            output_text=self.contents.pop(0),
            usage=SimpleNamespace(
                input_tokens=10,
                output_tokens=2,
                input_tokens_details=SimpleNamespace(cached_tokens=0),
            ),
        )


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


VALID = """{
  "summary": "Failure", "steps_to_reproduce": [], "expected_behavior": null,
  "actual_behavior": null, "environment": {}, "affected_area": null,
  "repro_code": null, "missing_info": [], "confidence": 0.5
}"""


def service_with(contents: list[str]) -> tuple[ExtractionService, FakeStore]:
    store = FakeStore()
    client = OpenAIExtractionClient(None, client=SimpleNamespace(responses=FakeResponses(contents)))
    return ExtractionService(client, store), store


def test_mock_openai_successful_extraction() -> None:
    service, store = service_with([VALID])
    assert service.extract(issue()).summary == "Failure"
    assert len(store.items) == 1


@pytest.mark.parametrize(
    "invalid",
    [
        "not json",
        '{"summary": "missing fields"}',
        VALID[:-2] + ', "hallucinated_field": "no"}',
    ],
)
def test_mock_openai_invalid_responses_are_not_repaired(invalid: str) -> None:
    service, store = service_with([invalid, invalid])
    with pytest.raises(ExtractionFailure):
        service.extract(issue())
    assert len(store.items) == 2
