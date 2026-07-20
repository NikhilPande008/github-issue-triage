from triage.domain.enums import InvestigationStatus
from triage.persistence.database import Base, create_session_factory
from triage.persistence.models import Investigation
from triage.persistence.repositories import InvestigationRepository


def test_investigation_repository_crud(tmp_path) -> None:
    factory = create_session_factory(f"sqlite:///{tmp_path / 'triage.db'}")
    Base.metadata.create_all(factory.kw["bind"])
    with factory() as session:
        repository = InvestigationRepository(session)
        item = repository.create(Investigation(repository="psf/requests", issue_number=1))
        assert repository.get(item.id) is not None
        assert repository.update(item, status=InvestigationStatus.RUNNING).status is InvestigationStatus.RUNNING
        repository.delete(item)
        assert repository.list() == []
