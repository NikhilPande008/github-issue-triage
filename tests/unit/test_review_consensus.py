from datetime import datetime, timezone
import hashlib

import pytest
from sqlalchemy import select

from triage.domain.enums import AssessmentConfidence, AssessmentJudgment, Classification, ConsensusState, InvestigationStatus, ReviewerCohort
from triage.persistence.database import Base, create_session_factory
from triage.persistence.models import Investigation, ReviewAssessment, ReviewConsensusSnapshot, ReviewPacket
from triage.review_assessments import PilotReviewer, ReviewAssessmentService
from triage.review_consensus import CONSENSUS_ALGORITHM_VERSION, ReviewConsensusService
from triage.review_packets import canonical_json, packet_hash


def _packet(session):
    investigation = Investigation(repository="example/repo", issue_number=1, status=InvestigationStatus.COMPLETED, classification=Classification.NEEDS_INFO, asserts_failure=False, validation_reason="preserve")
    session.add(investigation); session.flush()
    body = {"packet_schema_version": "1.0", "investigation": {"id": investigation.id}}
    packet = ReviewPacket(investigation_id=investigation.id, version=1, schema_version="1.0", snapshot_json=canonical_json(body), integrity_hash=packet_hash(body), created_at=datetime.now(timezone.utc))
    session.add(packet); session.commit()
    return investigation, packet


def _add(session, packet, reviewer_id, cohort, answers=None, supersedes=None):
    answers = answers or (AssessmentJudgment.YES,) * 4
    return ReviewAssessmentService(session).create(packet.id, PilotReviewer(reviewer_id, cohort), extraction_aligned=answers[0], test_aligned=answers[1], failure_supports_signal=answers[2], public_comment_appropriate=answers[3], confidence=AssessmentConfidence.HIGH, rationale="Recorded reviewer rationale.", supersedes_assessment_id=supersedes)


def _ready(session, packet, answers=None):
    _add(session, packet, "maintainer", ReviewerCohort.MAINTAINER, answers)
    _add(session, packet, "engineer-1", ReviewerCohort.INDEPENDENT_ENGINEER, answers)
    _add(session, packet, "engineer-2", ReviewerCohort.INDEPENDENT_ENGINEER, answers)


def test_consensus_pending_and_unanimously_aligned_with_auditable_snapshots(tmp_path) -> None:
    factory = create_session_factory(f"sqlite:///{tmp_path / 'consensus.db'}"); Base.metadata.create_all(factory.kw["bind"])
    with factory() as session:
        investigation, packet = _packet(session)
        assert ReviewConsensusService(session).current(packet.id)["state"] == ConsensusState.PENDING_REVIEW.value
        _add(session, packet, "maintainer", ReviewerCohort.MAINTAINER)
        assert ReviewConsensusService(session).current(packet.id)["state"] == ConsensusState.PENDING_REVIEW.value
        _add(session, packet, "engineer-1", ReviewerCohort.INDEPENDENT_ENGINEER)
        assert ReviewConsensusService(session).current(packet.id)["state"] == ConsensusState.PENDING_REVIEW.value
        _add(session, packet, "engineer-2", ReviewerCohort.INDEPENDENT_ENGINEER)
        result = ReviewConsensusService(session).current(packet.id)
        assert result["state"] == ConsensusState.UNANIMOUSLY_ALIGNED.value
        snapshots = list(session.scalars(select(ReviewConsensusSnapshot).where(ReviewConsensusSnapshot.review_packet_id == packet.id)))
        assert len(snapshots) == 3
        latest = snapshots[-1]
        assert latest.algorithm_version == CONSENSUS_ALGORITHM_VERSION
        assert latest.snapshot_hash == hashlib.sha256(latest.snapshot_json.encode()).hexdigest()
        assert len(result["active_assessment_ids"]) == len(result["active_assessment_payload_hashes"]) == 3
        assert investigation.classification == Classification.NEEDS_INFO and investigation.validation_reason == "preserve"


@pytest.mark.parametrize("question", range(4))
def test_each_differing_judgment_is_disagreed(tmp_path, question) -> None:
    factory = create_session_factory(f"sqlite:///{tmp_path / f'disagree-{question}.db'}"); Base.metadata.create_all(factory.kw["bind"])
    with factory() as session:
        _, packet = _packet(session)
        _ready(session, packet)
        # Supersede one active assessment so the final active set differs only here.
        prior = session.scalar(select(ReviewAssessment).where(ReviewAssessment.reviewer_external_id == "engineer-2"))
        answers = [AssessmentJudgment.YES] * 4; answers[question] = AssessmentJudgment.NO
        _add(session, packet, "engineer-2", ReviewerCohort.INDEPENDENT_ENGINEER, tuple(answers), supersedes=prior.id)
        result = ReviewConsensusService(session).current(packet.id)
        assert result["state"] == ConsensusState.DISAGREED.value
        assert result["disagreement"][0]["question"] == ("extraction_aligned", "test_aligned", "failure_supports_signal", "public_comment_appropriate")[question]
        assert result["superseded_assessment_count"] == 1


def test_rejection_and_context_states_are_not_votes(tmp_path) -> None:
    factory = create_session_factory(f"sqlite:///{tmp_path / 'states.db'}"); Base.metadata.create_all(factory.kw["bind"])
    with factory() as session:
        _, rejected = _packet(session)
        _ready(session, rejected, (AssessmentJudgment.YES, AssessmentJudgment.NO, AssessmentJudgment.YES, AssessmentJudgment.YES))
        assert ReviewConsensusService(session).current(rejected.id)["state"] == ConsensusState.REJECTED_ALIGNMENT.value
        _, context = _packet(session)
        _ready(session, context, (AssessmentJudgment.UNCERTAIN,) * 4)
        assert ReviewConsensusService(session).current(context.id)["state"] == ConsensusState.INSUFFICIENT_CONTEXT.value
