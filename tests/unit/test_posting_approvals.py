from datetime import datetime, timedelta, timezone

import pytest

from triage.domain.enums import Classification, InvestigationStatus, ReviewerCohort, WebhookJobStatus
from triage.persistence.database import Base, create_session_factory
from triage.persistence.models import Investigation, PostingApprovalEvent, ReviewPacket, WebhookJob
from triage.posting_approvals import PostingApprovalService, comment_hash
from triage.review_assessments import PilotReviewer
from triage.review_packets import canonical_json, packet_hash


def _ready(session, classification=Classification.NEEDS_INFO, body="### Information requested\n\n- details\n\n<!-- marker -->"):
    investigation = Investigation(repository="owner/repo", issue_number=1, status=InvestigationStatus.COMPLETED, classification=classification, validation_reason="unchanged")
    session.add(investigation); session.flush()
    snapshot = {"packet_schema_version": "1.0", "investigation": {"id": investigation.id}}
    packet = ReviewPacket(investigation_id=investigation.id, version=1, schema_version="1.0", snapshot_json=canonical_json(snapshot), integrity_hash=packet_hash(snapshot), created_at=datetime.now(timezone.utc))
    job = WebhookJob(delivery_id="delivery", repository="owner/repo", issue_number=1, event="issues", action="opened", status=WebhookJobStatus.QUEUED, investigation_id=investigation.id, proposed_comment_body=body)
    session.add_all([packet, job]); session.commit()
    return investigation, packet, job


def test_needs_info_approval_binds_exact_packet_and_body_and_is_consumed(tmp_path) -> None:
    factory = create_session_factory(f"sqlite:///{tmp_path / 'approval.db'}"); Base.metadata.create_all(factory.kw["bind"])
    with factory() as session:
        investigation, packet, job = _ready(session)
        service = PostingApprovalService(session)
        assert service.valid_approval(investigation.id, job.proposed_comment_body)[1] == "REVIEW_REQUIRED"
        approval = service.create(investigation.id, PilotReviewer("engineer", ReviewerCohort.INDEPENDENT_ENGINEER), rationale="looks good", ttl_seconds=3600)
        assert approval.packet_hash == packet.integrity_hash and approval.comment_body_hash == comment_hash(job.proposed_comment_body)
        assert service.valid_approval(investigation.id, job.proposed_comment_body)[0].id == approval.id
        assert service.valid_approval(investigation.id, job.proposed_comment_body + " changed")[0] is None
        service.consume(approval)
        assert service.valid_approval(investigation.id, job.proposed_comment_body)[0] is None
        assert session.query(PostingApprovalEvent).filter_by(approval_id=approval.id, event_type="CONSUMED").count() == 1
        assert investigation.classification == Classification.NEEDS_INFO and investigation.validation_reason == "unchanged"


def test_behavior_gap_requires_aligned_consensus_and_authorized_approver(tmp_path) -> None:
    factory = create_session_factory(f"sqlite:///{tmp_path / 'gap.db'}"); Base.metadata.create_all(factory.kw["bind"])
    with factory() as session:
        investigation, _, _ = _ready(session, Classification.BEHAVIOR_GAP_CONFIRMED)
        service = PostingApprovalService(session)
        assert service.eligibility(investigation.id)["status"] == "CONSENSUS_REQUIRED"
        with pytest.raises(ValueError):
            service.create(investigation.id, PilotReviewer("engineer", ReviewerCohort.INDEPENDENT_ENGINEER), rationale=None, ttl_seconds=60)
