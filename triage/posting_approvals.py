"""Pilot-only per-result public-comment approval gate."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from triage.domain.enums import Classification, ConsensusState, PostingApprovalStatus, ReviewerCohort
from triage.persistence.models import Investigation, PostingApproval, PostingApprovalEvent, ReviewConsensusSnapshot, ReviewPacket, WebhookJob
from triage.review_assessments import PilotReviewer
from triage.review_consensus import CONSENSUS_ALGORITHM_VERSION, ReviewConsensusService
from triage.review_packets import canonical_json

POSTING_POLICY_VERSION = "1.0"
MAX_RATIONALE_CHARS = 2_000


def normalize_comment_body(body: str) -> str:
    return "\n".join(line.rstrip() for line in body.replace("\r\n", "\n").replace("\r", "\n").strip().split("\n"))


def comment_hash(body: str) -> str:
    return hashlib.sha256(normalize_comment_body(body).encode("utf-8")).hexdigest()


class PostingApprovalService:
    def __init__(self, session: Session): self.session = session

    def eligibility(self, investigation_id: str, body: str | None = None) -> dict[str, object]:
        investigation = self.session.get(Investigation, investigation_id)
        if investigation is None or investigation.classification not in {Classification.BEHAVIOR_GAP_CONFIRMED, Classification.NEEDS_INFO} or investigation.status.value not in {"COMPLETED", "COMPLETED_NO_GAP", "FAILED"}:
            return {"eligible": False, "status": "REVIEW_REQUIRED", "reason": "Investigation outcome is not eligible for public posting."}
        packet = self.session.scalar(select(ReviewPacket).where(ReviewPacket.investigation_id == investigation_id).order_by(ReviewPacket.version.desc()))
        if packet is None:
            return {"eligible": False, "status": "REVIEW_REQUIRED", "reason": "An immutable review packet is required."}
        if body is None:
            job = self.session.scalar(select(WebhookJob).where(WebhookJob.investigation_id == investigation_id).order_by(WebhookJob.created_at.desc()))
            body = job.proposed_comment_body if job else None
        if not body:
            return {"eligible": False, "status": "REVIEW_REQUIRED", "reason": "Exact comment preview is required."}
        consensus, snapshot = self._consensus(packet)
        if investigation.classification == Classification.BEHAVIOR_GAP_CONFIRMED:
            if consensus.get("state") != ConsensusState.UNANIMOUSLY_ALIGNED.value:
                return {"eligible": False, "status": "CONSENSUS_REQUIRED", "reason": "Behavior-gap comments require unanimously aligned semantic review.", "packet": packet, "consensus": consensus}
        return {"eligible": True, "status": "REVIEW_REQUIRED", "reason": "A current human posting approval is required.", "packet": packet, "consensus": consensus, "consensus_snapshot": snapshot, "body_hash": comment_hash(body), "comment_type": investigation.classification.value}

    def create(self, investigation_id: str, reviewer: PilotReviewer, *, rationale: str | None, ttl_seconds: int) -> PostingApproval:
        eligibility = self.eligibility(investigation_id)
        if not eligibility["eligible"]:
            raise ValueError(str(eligibility["reason"]))
        investigation = self.session.get(Investigation, investigation_id); assert investigation is not None
        if investigation.classification == Classification.BEHAVIOR_GAP_CONFIRMED and reviewer.cohort != ReviewerCohort.MAINTAINER and not reviewer.posting_approver:
            raise PermissionError("Reviewer is not authorized to approve behavior-gap comments")
        packet = eligibility["packet"]; consensus = eligibility["consensus"]; snapshot = eligibility["consensus_snapshot"]
        if snapshot is None:
            # NEEDS_INFO does not require aligned consensus, but every approval
            # still binds the contemporaneous deterministic review-state record.
            snapshot = ReviewConsensusService(self.session).recalculate(packet.id)
        now = datetime.now(timezone.utc)
        payload = {"investigation_id": investigation_id, "packet_id": packet.id, "packet_hash": packet.integrity_hash, "packet_version": packet.version, "consensus_snapshot_id": snapshot.id if snapshot else None, "consensus_snapshot_hash": snapshot.snapshot_hash if snapshot else None, "consensus_algorithm_version": CONSENSUS_ALGORITHM_VERSION, "comment_body_hash": eligibility["body_hash"], "classification": investigation.classification.value, "comment_type": eligibility["comment_type"], "policy_version": POSTING_POLICY_VERSION, "reviewer_external_id": reviewer.external_id, "reviewer_cohort": reviewer.cohort.value, "reviewer_role": "POSTING_APPROVER" if reviewer.posting_approver else "PILOT_REVIEWER", "rationale": (rationale or "")[:MAX_RATIONALE_CHARS]}
        model_values = {**payload, "review_packet_id": payload["packet_id"]}
        del model_values["packet_id"]
        approval = PostingApproval(**model_values, status=PostingApprovalStatus.ACTIVE, approval_hash=hashlib.sha256(canonical_json(payload).encode()).hexdigest(), created_at=now, expires_at=now + timedelta(seconds=max(1, ttl_seconds)))
        self.session.add(approval); self.session.flush()
        self.session.add(PostingApprovalEvent(approval_id=approval.id, event_type="CREATED", payload_hash=approval.approval_hash, created_at=now))
        self.session.commit(); self.session.refresh(approval)
        return approval

    def valid_approval(self, investigation_id: str, body: str) -> tuple[PostingApproval | None, str]:
        eligibility = self.eligibility(investigation_id, body)
        if not eligibility["eligible"]:
            return None, str(eligibility["status"])
        packet = eligibility["packet"]; snapshot = eligibility["consensus_snapshot"]
        approvals = list(self.session.scalars(select(PostingApproval).where(PostingApproval.investigation_id == investigation_id).order_by(PostingApproval.created_at.desc())))
        now = datetime.now(timezone.utc)
        for approval in approvals:
            consumed = self.session.scalar(select(PostingApprovalEvent).where(PostingApprovalEvent.approval_id == approval.id, PostingApprovalEvent.event_type == "CONSUMED"))
            if consumed: continue
            expiry = approval.expires_at if approval.expires_at.tzinfo else approval.expires_at.replace(tzinfo=timezone.utc)
            if expiry <= now: continue
            if approval.packet_hash != packet.integrity_hash or approval.packet_version != packet.version or approval.comment_body_hash != eligibility["body_hash"] or approval.classification != self.session.get(Investigation, investigation_id).classification or approval.policy_version != POSTING_POLICY_VERSION: continue
            if approval.consensus_snapshot_hash != (snapshot.snapshot_hash if snapshot else None): continue
            return approval, "APPROVED"
        return None, "APPROVAL_EXPIRED" if any((item.expires_at if item.expires_at.tzinfo else item.expires_at.replace(tzinfo=timezone.utc)) <= now for item in approvals) else "REVIEW_REQUIRED"

    def consume(self, approval: PostingApproval) -> None:
        payload = {"approval_id": approval.id, "approval_hash": approval.approval_hash, "event": "CONSUMED"}
        self.session.add(PostingApprovalEvent(approval_id=approval.id, event_type="CONSUMED", payload_hash=hashlib.sha256(canonical_json(payload).encode()).hexdigest(), created_at=datetime.now(timezone.utc)))
        self.session.commit()

    def _consensus(self, packet: ReviewPacket):
        result = ReviewConsensusService(self.session).current(packet.id)
        snapshot = self.session.scalar(select(ReviewConsensusSnapshot).where(ReviewConsensusSnapshot.review_packet_id == packet.id).order_by(ReviewConsensusSnapshot.computed_at.desc(), ReviewConsensusSnapshot.id.desc()))
        return result, snapshot
