from pathlib import Path

from triage.api.routes.investigations import get_summary
from triage.classification.client import ClassificationResponse, Usage as ClassificationUsage
from triage.classification.models import ClassificationEvidence
from triage.classification.service import ClassificationService
from triage.domain.enums import Classification, InvestigationStatus
from triage.extraction.client import ExtractionResponse, Usage as ExtractionUsage
from triage.extraction.service import ExtractionService
from triage.github.models import GitHubIssue
from triage.persistence.database import Base, create_session_factory
from triage.persistence.models import Investigation, LLMCall
from triage.persistence.repositories import LLMCallRepository


class ExtractionClient:
    def extract(self, system_prompt: str, user_prompt: str) -> ExtractionResponse:
        return ExtractionResponse(
            '{"summary":"Missing TLS file","steps_to_reproduce":[],"expected_behavior":null,"actual_behavior":null,"environment":{},"affected_area":null,"repro_code":null,"missing_info":[],"confidence":0.5}',
            ExtractionUsage(100, 20, 10),
        )


class ClassificationClient:
    def classify(self, system_prompt: str, evidence_prompt: str) -> ClassificationResponse:
        return ClassificationResponse('{"classification":"NEEDS_INFO"}', ClassificationUsage(50, 0, 5))


def test_new_investigation_links_extraction_and_classification_metrics(tmp_path: Path) -> None:
    factory = create_session_factory(f"sqlite:///{tmp_path / 'triage.db'}")
    Base.metadata.create_all(factory.kw["bind"])
    issue = GitHubIssue(
        repository="psf/requests", issue_number=7564, title="Raise FileNotFoundError", body="", author="reporter",
        labels=[], comments=[], state="open", created_at="2026-01-01T00:00:00Z", updated_at="2026-01-01T00:00:00Z",
        url="https://github.com/psf/requests/issues/7564",
    )
    pytest_output = tmp_path / "pytest.txt"
    pytest_output.write_text("1 failed\n", encoding="utf-8")
    with factory() as session:
        investigation = Investigation(
            repository=issue.repository, issue_number=issue.issue_number, issue_title=issue.title,
            status=InvestigationStatus.RUNNING,
        )
        session.add(investigation)
        session.commit()
        calls = LLMCallRepository(session)
        ExtractionService(ExtractionClient(), calls, investigation.id).extract(issue)
        result = ClassificationService(ClassificationClient(), calls, investigation.id).classify(
            ClassificationEvidence(False, "Missing reproduction details", 1, pytest_output, None)
        )
        linked = session.query(LLMCall).filter_by(investigation_id=investigation.id).all()
        summary = get_summary(investigation.id, session)

    assert result is Classification.NEEDS_INFO
    assert {call.purpose for call in linked} == {"issue_extraction", "evidence_classification"}
    assert all(call.provider == "openai" and call.pricing_version == "2026-07-20" for call in linked)
    assert all(call.cost_usd is not None and call.latency_ms >= 0 for call in linked)
    assert summary["issue_title"] == "Raise FileNotFoundError"
    assert summary["tracked_llm_api_cost_usd"] == 0.000222
    assert summary["tracked_llm_api_latency_ms"] == sum(call.latency_ms for call in linked)
    assert summary["tracked_llm_api_input_tokens"] == 150
    assert summary["tracked_llm_api_output_tokens"] == 15
