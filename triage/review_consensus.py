"""Deterministic, non-authoritative semantic-review consensus calculation."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from triage.domain.enums import AssessmentJudgment, ConsensusState, ReviewerCohort
from triage.persistence.models import ReviewAssessment, ReviewAssessmentAudit, ReviewConsensusSnapshot, ReviewPacket
from triage.review_assessments import ASSESSMENT_SCHEMA_VERSION
from triage.review_packets import canonical_json

CONSENSUS_ALGORITHM_VERSION = "1.0"
QUESTIONS = ("extraction_aligned", "test_aligned", "failure_supports_signal", "public_comment_appropriate")
# Every required question is core to semantic fidelity in version 1.0.
CORE_ALIGNMENT_QUESTIONS = QUESTIONS


class ReviewConsensusService:
    def __init__(self, session: Session):
        self.session = session

    def current(self, packet_id: str) -> dict[str, object]:
        packet = self.session.get(ReviewPacket, packet_id)
        if packet is None:
            raise ValueError("Review packet not found")
        return self._calculate(packet)

    def recalculate(self, packet_id: str) -> ReviewConsensusSnapshot:
        packet = self.session.get(ReviewPacket, packet_id)
        if packet is None:
            raise ValueError("Review packet not found")
        result = self._calculate(packet)
        computed_at = datetime.now(timezone.utc)
        snapshot_payload = {**result, "computed_at": computed_at.isoformat()}
        encoded = canonical_json(snapshot_payload)
        snapshot = ReviewConsensusSnapshot(
            review_packet_id=packet.id, investigation_id=packet.investigation_id,
            packet_hash=packet.integrity_hash, packet_version=packet.version,
            algorithm_version=CONSENSUS_ALGORITHM_VERSION, state=ConsensusState(str(result["state"])),
            snapshot_json=encoded,
            snapshot_hash=hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
            computed_at=computed_at,
        )
        self.session.add(snapshot)
        self.session.commit()
        self.session.refresh(snapshot)
        return snapshot

    def _calculate(self, packet: ReviewPacket) -> dict[str, object]:
        assessments = list(self.session.scalars(select(ReviewAssessment).where(
            ReviewAssessment.review_packet_id == packet.id,
            ReviewAssessment.schema_version == ASSESSMENT_SCHEMA_VERSION,
        ).order_by(ReviewAssessment.created_at, ReviewAssessment.id)))
        superseded = {item.supersedes_assessment_id for item in assessments if item.supersedes_assessment_id}
        active = [item for item in assessments if item.id not in superseded]
        coverage = {"MAINTAINER": sum(item.reviewer_cohort == ReviewerCohort.MAINTAINER for item in active), "INDEPENDENT_ENGINEER": sum(item.reviewer_cohort == ReviewerCohort.INDEPENDENT_ENGINEER for item in active)}
        base: dict[str, object] = {
            "packet_id": packet.id, "packet_hash": packet.integrity_hash, "packet_version": packet.version,
            "algorithm_version": CONSENSUS_ALGORITHM_VERSION, "active_assessment_ids": [item.id for item in active],
            "active_assessment_payload_hashes": [], "coverage": coverage,
            "active_assessment_count": len(active), "superseded_assessment_count": len(assessments) - len(active),
            "disagreement": [], "unavailable_reason": None,
        }
        audits = {audit.assessment_id: audit for audit in self.session.scalars(select(ReviewAssessmentAudit).where(ReviewAssessmentAudit.assessment_id.in_([item.id for item in active]))) } if active else {}
        if any(item.packet_hash != packet.integrity_hash or item.packet_version != packet.version or item.investigation_id != packet.investigation_id or item.id not in audits for item in active):
            return {**base, "state": ConsensusState.UNAVAILABLE.value, "unavailable_reason": "Assessment provenance or audit record is inconsistent."}
        base["active_assessment_payload_hashes"] = [{"assessment_id": item.id, "payload_hash": audits[item.id].payload_hash} for item in active]
        if coverage["MAINTAINER"] < 1 or coverage["INDEPENDENT_ENGINEER"] < 2:
            return {**base, "state": ConsensusState.PENDING_REVIEW.value}
        disagreement = []
        for question in QUESTIONS:
            by_value: dict[str, list[str]] = {}
            for item in active:
                by_value.setdefault(getattr(item, question).value, []).append(item.id)
            if len(by_value) > 1:
                disagreement.append({"question": question, "values": by_value})
        if disagreement:
            return {**base, "state": ConsensusState.DISAGREED.value, "disagreement": disagreement}
        unanimous = {question: getattr(active[0], question) for question in QUESTIONS}
        if any(unanimous[question] == AssessmentJudgment.NO for question in CORE_ALIGNMENT_QUESTIONS):
            return {**base, "state": ConsensusState.REJECTED_ALIGNMENT.value}
        if any(unanimous[question] in {AssessmentJudgment.UNCERTAIN, AssessmentJudgment.NOT_ENOUGH_CONTEXT} for question in QUESTIONS):
            return {**base, "state": ConsensusState.INSUFFICIENT_CONTEXT.value}
        if all(unanimous[question] == AssessmentJudgment.YES for question in QUESTIONS):
            return {**base, "state": ConsensusState.UNANIMOUSLY_ALIGNED.value}
        return {**base, "state": ConsensusState.UNAVAILABLE.value, "unavailable_reason": "Unsupported unanimous assessment values."}
