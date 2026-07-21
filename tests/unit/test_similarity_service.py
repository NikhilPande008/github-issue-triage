import json

from sqlalchemy.orm import sessionmaker

from triage.config.settings import Settings
from triage.domain.enums import InvestigationStatus
from triage.persistence.database import Base, create_engine_from_url
from triage.persistence.models import Artifact, Investigation
from triage.similarity import DuplicateSimilarityService


def _investigation(session, tmp_path, number, summary, raw_body="secret raw body"):
    item = Investigation(repository="owner/repo", issue_number=number, status=InvestigationStatus.COMPLETED, validation_reason="New failing assertion introduced in: tests/test_api.py")
    session.add(item); session.commit()
    extraction = tmp_path / f"extraction-{number}.json"
    extraction.write_text(json.dumps({"summary": summary, "expected_behavior": "works", "actual_behavior": "fails", "missing_info": []}), encoding="utf-8")
    diff = tmp_path / f"diff-{number}.txt"
    diff.write_text("+++ b/tests/test_api.py\n+assert value\n", encoding="utf-8")
    session.add_all([Artifact(investigation_id=item.id, kind="extraction_json", path=str(extraction)), Artifact(investigation_id=item.id, kind="git_diff", path=str(diff))]); session.commit()
    return item


def test_similarity_is_repository_scoped_advisory_and_excludes_raw_body(tmp_path) -> None:
    engine = create_engine_from_url(f"sqlite:///{tmp_path / 'similarity.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        first = _investigation(session, tmp_path, 1, "TLS file fails")
        second = _investigation(session, tmp_path, 2, "TLS file fails")
        service = DuplicateSimilarityService(session, Settings(duplicate_similarity_threshold=0.7))
        service.analyze(first.id)
        candidates = service.analyze(second.id)
        assert len(candidates) == 1
        assert candidates[0].similarity_score == 1
        document = service.canonical_document(first)
        assert "secret raw body" not in document
        assert candidates[0].source_investigation_id != candidates[0].candidate_investigation_id
