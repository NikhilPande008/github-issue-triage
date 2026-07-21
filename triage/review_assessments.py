"""Pilot-only, append-only semantic-fidelity assessment ledger."""
from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from triage.domain.enums import AssessmentConfidence, AssessmentJudgment, ReviewerCohort
from triage.persistence.models import ReviewAssessment, ReviewAssessmentAudit, ReviewPacket
from triage.review_packets import canonical_json
from triage.semantic_review import review_outcome

ASSESSMENT_SCHEMA_VERSION = "1.0"
MAX_RATIONALE_CHARS = 4_000
REASON_TAGS = {"EXTRACTION_INCOMPLETE", "TEST_UNRELATED", "TEST_TOO_BROAD", "TEST_TOO_NARROW", "FAILURE_NOT_DIAGNOSTIC", "MISSING_CONTEXT", "COMMENT_INAPPROPRIATE", "ENVIRONMENT_DEPENDENT", "OTHER"}


class AssessmentPermissionError(ValueError):
    pass


@dataclass(frozen=True)
class PilotReviewer:
    external_id: str
    cohort: ReviewerCohort
    posting_approver: bool = False
    repositories: frozenset[str] = frozenset()


def verify_pilot_reviewer(registry_json: str, external_id: str | None, token: str | None) -> PilotReviewer:
    """Verify against configured registry; callers receive no registry details."""
    if not external_id or not token:
        raise AssessmentPermissionError("Pilot reviewer verification failed")
    try:
        registry = json.loads(registry_json)
        entry = registry.get(external_id)
        cohort = ReviewerCohort(entry["cohort"])
        configured_token = entry["token"]
    except (AttributeError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise AssessmentPermissionError("Pilot reviewer verification failed") from None
    if not isinstance(configured_token, str) or not hmac.compare_digest(configured_token, token):
        raise AssessmentPermissionError("Pilot reviewer verification failed")
    repositories = entry.get("repositories", [])
    if not isinstance(repositories, list) or not all(isinstance(item, str) for item in repositories):
        raise AssessmentPermissionError("Pilot reviewer verification failed")
    return PilotReviewer(external_id=external_id, cohort=cohort, posting_approver=bool(entry.get("posting_approver", False)), repositories=frozenset(item.lower() for item in repositories))


class ReviewAssessmentService:
    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        packet_id: str,
        reviewer: PilotReviewer,
        *,
        extraction_aligned: AssessmentJudgment,
        test_aligned: AssessmentJudgment,
        failure_supports_signal: AssessmentJudgment,
        public_comment_appropriate: AssessmentJudgment,
        confidence: AssessmentConfidence,
        rationale: str | None = None,
        reason_tags: list[str] | None = None,
        supersedes_assessment_id: str | None = None,
    ) -> ReviewAssessment:
        packet = self.session.get(ReviewPacket, packet_id)
        if packet is None:
            raise ValueError("Review packet not found")
        existing = list(self.session.scalars(select(ReviewAssessment).where(
            ReviewAssessment.review_packet_id == packet.id,
            ReviewAssessment.reviewer_external_id == reviewer.external_id,
            ReviewAssessment.schema_version == ASSESSMENT_SCHEMA_VERSION,
        )))
        if existing:
            self._validate_supersession(existing, supersedes_assessment_id, packet.id, reviewer.external_id)
        elif supersedes_assessment_id is not None:
            raise ValueError("Superseded assessment must belong to the same reviewer and packet")
        tags = sorted(set(reason_tags or []))
        if len(tags) > 5 or any(tag not in REASON_TAGS for tag in tags): raise ValueError("Invalid assessment reason tags")
        outcome = review_outcome(extraction_aligned, test_aligned, failure_supports_signal, public_comment_appropriate)
        clean_rationale = (rationale or "").strip()[:MAX_RATIONALE_CHARS]
        if outcome in {"UNCLEAR", "MISALIGNED"} and not clean_rationale:
            raise ValueError("A rationale is required for an unclear or misaligned review")
        payload = {
            "packet_id": packet.id, "packet_hash": packet.integrity_hash, "packet_version": packet.version,
            "reviewer_external_id": reviewer.external_id, "reviewer_cohort": reviewer.cohort.value,
            "schema_version": ASSESSMENT_SCHEMA_VERSION,
            "extraction_aligned": extraction_aligned.value, "test_aligned": test_aligned.value,
            "failure_supports_signal": failure_supports_signal.value,
            "public_comment_appropriate": public_comment_appropriate.value, "confidence": confidence.value,
            "derived_review_outcome": outcome, "rationale": clean_rationale, "supersedes_assessment_id": supersedes_assessment_id,
            "reason_tags": tags,
        }
        assessment = ReviewAssessment(
            review_packet_id=packet.id, investigation_id=packet.investigation_id,
            packet_hash=packet.integrity_hash, packet_version=packet.version,
            reviewer_external_id=reviewer.external_id, reviewer_cohort=reviewer.cohort,
            schema_version=ASSESSMENT_SCHEMA_VERSION, extraction_aligned=extraction_aligned,
            test_aligned=test_aligned, failure_supports_signal=failure_supports_signal,
            public_comment_appropriate=public_comment_appropriate, confidence=confidence,
            rationale=clean_rationale or None, supersedes_assessment_id=supersedes_assessment_id,
            reason_tags_json=json.dumps(tags),
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(assessment)
        self.session.flush()
        self.session.add(ReviewAssessmentAudit(
            assessment_id=assessment.id, reviewer_external_id=reviewer.external_id,
            packet_hash=packet.integrity_hash,
            payload_hash=hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest(),
            created_at=datetime.now(timezone.utc),
        ))
        self.session.commit()
        self.session.refresh(assessment)
        # Derived consensus is advisory-only. A calculation/storage error must
        # never roll back or alter this independently submitted assessment.
        try:
            from triage.review_consensus import ReviewConsensusService
            ReviewConsensusService(self.session).recalculate(packet.id)
        except Exception:
            self.session.rollback()
        return assessment

    def _validate_supersession(self, existing: list[ReviewAssessment], supersedes_id: str | None, packet_id: str, reviewer_id: str) -> None:
        if supersedes_id is None:
            raise ValueError("An active assessment already exists; submit an explicit superseding assessment")
        previous = next((item for item in existing if item.id == supersedes_id), None)
        superseded = {item.supersedes_assessment_id for item in existing if item.supersedes_assessment_id}
        if previous is None or previous.id in superseded or previous.review_packet_id != packet_id or previous.reviewer_external_id != reviewer_id:
            raise ValueError("Superseded assessment must be the reviewer’s active assessment for this packet")
