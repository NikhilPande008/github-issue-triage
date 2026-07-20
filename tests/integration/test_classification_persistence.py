from datetime import datetime, timezone

from triage.domain.enums import Classification, InvestigationStatus
from triage.persistence.models import Investigation
from triage.persistence.repositories import InvestigationRepository


def test_classification_metadata_is_persisted(tmp_path) -> None:
    from triage.persistence.database import Base, create_session_factory

    factory = create_session_factory(f"sqlite:///{tmp_path / 'triage.db'}")
    Base.metadata.create_all(factory.kw["bind"])
    session = factory()
    repository = InvestigationRepository(session)
    investigation = repository.create(
        Investigation(repository="psf/requests", issue_number=123, status=InvestigationStatus.COMPLETED)
    )
    completed_at = datetime.now(timezone.utc)

    repository.update(
        investigation,
        classification=Classification.NEEDS_INFO,
        classification_model="gpt-5.6-luna",
        classification_completed_at=completed_at,
    )
    persisted = repository.get(investigation.id)

    assert persisted is not None
    assert persisted.classification is Classification.NEEDS_INFO
    assert persisted.classification_model == "gpt-5.6-luna"
    assert persisted.classification_completed_at is not None
    session.close()
