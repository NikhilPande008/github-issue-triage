from triage.persistence.database import Base, create_session_factory
from triage.persistence.models import Investigation, LLMCall
from triage.persistence.repositories import LLMCallRepository
from triage.domain.enums import InvestigationStatus


def test_tracked_cost_uses_only_linked_priced_openai_calls(tmp_path) -> None:
    factory = create_session_factory(f"sqlite:///{tmp_path / 'calls.db'}")
    Base.metadata.create_all(factory.kw["bind"])
    with factory() as session:
        first = Investigation(repository="psf/requests", issue_number=1, status=InvestigationStatus.COMPLETED)
        second = Investigation(repository="psf/requests", issue_number=2, status=InvestigationStatus.COMPLETED)
        session.add_all([first, second])
        session.flush()
        session.add_all([
            LLMCall(investigation_id=first.id, provider="openai", model="gpt-5.6-luna", pricing_version="2026-07-20", purpose="issue_extraction", input_tokens=1, cached_input_tokens=0, output_tokens=1, cost_usd="0.004184", latency_ms=1),
            LLMCall(investigation_id=first.id, provider="codex", model="codex", purpose="investigation", input_tokens=0, cached_input_tokens=0, output_tokens=0, cost_usd=0, latency_ms=1),
            LLMCall(investigation_id=second.id, provider="openai", model="unknown", pricing_version=None, purpose="issue_extraction", input_tokens=1, cached_input_tokens=0, output_tokens=1, cost_usd=None, latency_ms=1),
        ])
        session.commit()
        repository = LLMCallRepository(session)
        assert repository.tracked_cost_usd(first.id) == 0.004184
        assert repository.tracked_cost_usd(second.id) is None
