import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from triage.domain.enums import AssessmentConfidence, AssessmentJudgment, Classification, InvestigationStatus, ReviewerCohort
from triage.persistence.database import Base, create_session_factory
from triage.persistence.models import Investigation, ReviewAssessment, ReviewAssessmentAudit, ReviewPacket
from triage.review_assessments import ASSESSMENT_SCHEMA_VERSION, AssessmentPermissionError, PilotReviewer, ReviewAssessmentService, verify_pilot_reviewer
from triage.review_packets import canonical_json, packet_hash
from triage.semantic_review import review_outcome


def _packet(session):
    investigation = Investigation(repository="example/repo", issue_number=1, status=InvestigationStatus.COMPLETED, classification=Classification.NEEDS_INFO)
    session.add(investigation); session.flush()
    snapshot = {"packet_schema_version": "1.0", "investigation": {"id": investigation.id}}
    packet = ReviewPacket(investigation_id=investigation.id, version=1, schema_version="1.0", snapshot_json=canonical_json(snapshot), integrity_hash=packet_hash(snapshot), created_at=datetime.now(timezone.utc))
    session.add(packet); session.commit()
    return investigation, packet


def _create(service, packet_id, reviewer, **values):
    values.setdefault("rationale", "Review rationale.")
    return service.create(packet_id, reviewer, extraction_aligned=AssessmentJudgment.YES, test_aligned=AssessmentJudgment.NO, failure_supports_signal=AssessmentJudgment.UNCERTAIN, public_comment_appropriate=AssessmentJudgment.NOT_ENOUGH_CONTEXT, confidence=AssessmentConfidence.HIGH, **values)


def test_assessments_capture_packet_provenance_audit_and_supersession(tmp_path) -> None:
    factory = create_session_factory(f"sqlite:///{tmp_path / 'assessments.db'}"); Base.metadata.create_all(factory.kw["bind"])
    with factory() as session:
        investigation, packet = _packet(session)
        service = ReviewAssessmentService(session)
        maintainer = PilotReviewer("maintainer-a", ReviewerCohort.MAINTAINER)
        original = _create(service, packet.id, maintainer, rationale="The test checks a different behavior.")
        assert original.packet_hash == packet.integrity_hash and original.packet_version == 1
        assert original.schema_version == ASSESSMENT_SCHEMA_VERSION
        assert session.scalar(select(ReviewAssessmentAudit).where(ReviewAssessmentAudit.assessment_id == original.id)).payload_hash
        with pytest.raises(ValueError, match="active assessment"):
            _create(service, packet.id, maintainer)
        replacement = _create(service, packet.id, maintainer, supersedes_assessment_id=original.id)
        assert replacement.supersedes_assessment_id == original.id
        assert session.get(ReviewAssessment, original.id).rationale == "The test checks a different behavior."
        independent = _create(service, packet.id, PilotReviewer("engineer-b", ReviewerCohort.INDEPENDENT_ENGINEER))
        assert independent.reviewer_cohort == ReviewerCohort.INDEPENDENT_ENGINEER
        original.confidence = AssessmentConfidence.LOW
        with pytest.raises(ValueError, match="append-only"):
            session.commit()
        session.rollback()


def test_configured_pilot_identity_is_not_an_arbitrary_name() -> None:
    registry = json.dumps({"maintainer-a": {"cohort": "MAINTAINER", "token": "pilot-secret"}})
    assert verify_pilot_reviewer(registry, "maintainer-a", "pilot-secret").cohort == ReviewerCohort.MAINTAINER
    with pytest.raises(AssessmentPermissionError):
        verify_pilot_reviewer(registry, "unregistered", "pilot-secret")
    with pytest.raises(AssessmentPermissionError):
        verify_pilot_reviewer(registry, "maintainer-a", "wrong")


def test_derived_outcome_is_deterministic_and_non_aligned_reviews_require_rationale(tmp_path) -> None:
    factory = create_session_factory(f"sqlite:///{tmp_path / 'outcome.db'}"); Base.metadata.create_all(factory.kw["bind"])
    with factory() as session:
        _, packet = _packet(session)
        service = ReviewAssessmentService(session)
        reviewer = PilotReviewer("maintainer-a", ReviewerCohort.MAINTAINER)
        with pytest.raises(ValueError, match="rationale is required"):
            service.create(packet.id, reviewer, extraction_aligned=AssessmentJudgment.YES, test_aligned=AssessmentJudgment.NO, failure_supports_signal=AssessmentJudgment.YES, public_comment_appropriate=AssessmentJudgment.YES, confidence=AssessmentConfidence.LOW)
        item = service.create(packet.id, reviewer, extraction_aligned=AssessmentJudgment.YES, test_aligned=AssessmentJudgment.NO, failure_supports_signal=AssessmentJudgment.YES, public_comment_appropriate=AssessmentJudgment.YES, confidence=AssessmentConfidence.HIGH, rationale="The changed assertion tests a different behavior.")
        assert review_outcome(item.extraction_aligned, item.test_aligned, item.failure_supports_signal, item.public_comment_appropriate) == "MISALIGNED"
        assert review_outcome(AssessmentJudgment.YES, AssessmentJudgment.UNCERTAIN, AssessmentJudgment.YES, AssessmentJudgment.YES) == "UNCLEAR"
        assert review_outcome(*(AssessmentJudgment.YES,) * 4) == "ALIGNED"
