from triage.extraction.client import ExtractionResponse, Usage
from triage.extraction.service import ExtractionService
from triage.github.models import GitHubIssue
from triage.persistence.database import Base, create_session_factory
from triage.persistence.models import Investigation, LLMCall
from triage.domain.enums import InvestigationStatus
from triage.persistence.repositories import LLMCallRepository


class FakeClient:
    def extract(self, system_prompt: str, user_prompt: str) -> ExtractionResponse:
        return ExtractionResponse(
            """{
                "summary": "Failure",
                "steps_to_reproduce": [],
                "expected_behavior": null,
                "actual_behavior": null,
                "environment": {},
                "affected_area": null,
                "repro_code": null,
                "missing_info": [],
                "confidence": 0.5
            }""",
            Usage(100, 20, 10),
        )


def test_extraction_records_llm_call(tmp_path) -> None:
    factory = create_session_factory(f"sqlite:///{tmp_path / 'triage.db'}")
    Base.metadata.create_all(factory.kw["bind"])
    issue = GitHubIssue(
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
    with factory() as session:
        investigation = Investigation(repository="psf/requests", issue_number=123, status=InvestigationStatus.PENDING)
        session.add(investigation)
        session.commit()
        ExtractionService(FakeClient(), LLMCallRepository(session), investigation.id).extract(issue)
        call = session.query(LLMCall).one()

    assert call.investigation_id == investigation.id
    assert call.provider == "openai"
    assert call.pricing_version == "2026-07-20"
    assert call.input_tokens == 100
    assert call.cached_input_tokens == 20
    assert call.output_tokens == 10
    assert call.latency_ms >= 0
