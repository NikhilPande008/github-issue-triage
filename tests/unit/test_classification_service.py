from pathlib import Path

import pytest

from triage.classification.client import ClassificationResponse, Usage
from triage.classification.models import ClassificationEvidence
from triage.classification.service import ClassificationFailure, ClassificationService
from triage.domain.enums import Classification


class FakeClient:
    def __init__(self, responses: list[str]):
        self.responses = iter(responses)
        self.calls: list[tuple[str, str]] = []

    def classify(self, system_prompt: str, evidence_prompt: str) -> ClassificationResponse:
        self.calls.append((system_prompt, evidence_prompt))
        return ClassificationResponse(next(self.responses), Usage(100, 20, 10))


class FakeCallStore:
    def __init__(self):
        self.items = []

    def create(self, item):
        self.items.append(item)
        return item


def evidence(tmp_path, reason: str = "Missing configuration details.") -> ClassificationEvidence:
    pytest_output = tmp_path / "pytest_output.txt"
    pytest_output.write_text("1 failed\n", encoding="utf-8")
    return ClassificationEvidence(False, reason, 1, pytest_output, None)


def test_valid_false_result_is_classified_and_instrumented(tmp_path) -> None:
    client = FakeClient(['{"classification": "NEEDS_INFO"}'])
    calls = FakeCallStore()

    result = ClassificationService(client, calls, investigation_id="investigation-1").classify(evidence(tmp_path))

    assert result is Classification.NEEDS_INFO
    assert len(client.calls) == 1
    assert calls.items[0].purpose == "evidence_classification"
    assert calls.items[0].input_tokens == 100
    assert calls.items[0].cached_input_tokens == 20
    assert calls.items[0].output_tokens == 10
    assert calls.items[0].cost_usd > 0
    assert calls.items[0].investigation_id == "investigation-1"
    assert calls.items[0].provider == "openai"


def test_validator_success_always_wins_without_model_call(tmp_path) -> None:
    client = FakeClient([])
    calls = FakeCallStore()
    successful = ClassificationEvidence(True, "Validated assertion failure.", 1, tmp_path / "missing.txt", None)

    assert ClassificationService(client, calls).classify(successful) is Classification.BEHAVIOR_GAP_CONFIRMED
    assert client.calls == []
    assert calls.items == []


@pytest.mark.parametrize("invalid", ["UNKNOWN", "DUPLICATE", "BEHAVIOR_GAP_CONFIRMED"])
def test_invalid_or_unsupported_model_output_is_retried_then_rejected(tmp_path, invalid) -> None:
    client = FakeClient([f'{{"classification": "{invalid}"}}', f'{{"classification": "{invalid}"}}'])
    calls = FakeCallStore()

    with pytest.raises(ClassificationFailure, match="after two attempts"):
        ClassificationService(client, calls).classify(evidence(tmp_path))

    assert len(client.calls) == 2
    assert len(calls.items) == 2


def test_invalid_first_response_is_retried_once(tmp_path) -> None:
    client = FakeClient(['{"classification": "DUPLICATE"}', '{"classification": "WONT_REPRO"}'])

    assert ClassificationService(client, FakeCallStore()).classify(evidence(tmp_path, "No missing setup evidence.")) is Classification.WONT_REPRO
    assert len(client.calls) == 2
