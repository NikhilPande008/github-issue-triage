"""Privacy-bounded pilot review telemetry; never evidence or policy input."""
from __future__ import annotations
import hashlib, json
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from triage.domain.enums import ReviewActivityType
from triage.persistence.models import ReviewActivity, ReviewAssessment, ReviewConsensusSnapshot, ReviewWorkSession
from triage.review_assessments import PilotReviewer

TELEMETRY_SCHEMA_VERSION = "1.0"

def session_hash(session_id: str | None) -> str:
    return hashlib.sha256((session_id or "legacy-internal").encode()).hexdigest()

class ReviewTelemetryService:
    def __init__(self, session: Session, idle_seconds: int = 900): self.session, self.idle_seconds = session, idle_seconds
    def event(self, investigation_id: str, reviewer: PilotReviewer, session_id: str | None, event_type: ReviewActivityType, packet_id: str | None = None, metadata: dict | None = None, now: datetime | None = None) -> ReviewActivity:
        safe = {str(k)[:64]: str(v)[:128] for k, v in (metadata or {}).items() if k in {"source", "assessment_id", "approval_id", "reason"}}
        item = ReviewActivity(review_packet_id=packet_id, investigation_id=investigation_id, reviewer_external_id=reviewer.external_id, reviewer_cohort=reviewer.cohort, session_hash=session_hash(session_id), event_type=event_type, metadata_json=json.dumps(safe, sort_keys=True), schema_version=TELEMETRY_SCHEMA_VERSION, created_at=now or datetime.now(timezone.utc))
        self.session.add(item); self.session.commit(); return item
    def start(self, packet_id: str, investigation_id: str, reviewer: PilotReviewer, session_id: str | None, now: datetime | None = None) -> ReviewWorkSession:
        now = now or datetime.now(timezone.utc); key = session_hash(session_id)
        active = self.session.scalar(select(ReviewWorkSession).where(ReviewWorkSession.review_packet_id == packet_id, ReviewWorkSession.reviewer_external_id == reviewer.external_id, ReviewWorkSession.session_hash == key, ReviewWorkSession.ended_at.is_(None)))
        if active: self._touch(active, now); event = ReviewActivityType.REVIEW_RESUMED
        else:
            active = ReviewWorkSession(review_packet_id=packet_id, investigation_id=investigation_id, reviewer_external_id=reviewer.external_id, reviewer_cohort=reviewer.cohort, session_hash=key, started_at=now, last_active_at=now, active_seconds=0, estimated=False); self.session.add(active); self.session.commit(); event = ReviewActivityType.REVIEW_STARTED
        self.event(investigation_id, reviewer, session_id, event, packet_id, now=now); return active
    def heartbeat(self, work_id: str, reviewer: PilotReviewer, session_id: str | None, now: datetime | None = None) -> ReviewWorkSession:
        work = self.session.get(ReviewWorkSession, work_id)
        if work is None or work.ended_at is not None or work.reviewer_external_id != reviewer.external_id or work.session_hash != session_hash(session_id): raise ValueError("Active review session not found")
        self._touch(work, now or datetime.now(timezone.utc)); self.event(work.investigation_id, reviewer, session_id, ReviewActivityType.HEARTBEAT, work.review_packet_id); return work
    def complete(self, work_id: str, reviewer: PilotReviewer, session_id: str | None, now: datetime | None = None) -> ReviewWorkSession:
        work = self.heartbeat(work_id, reviewer, session_id, now); work.ended_at = now or datetime.now(timezone.utc); self.session.commit(); self.event(work.investigation_id, reviewer, session_id, ReviewActivityType.REVIEW_COMPLETED, work.review_packet_id); return work
    def _touch(self, work: ReviewWorkSession, now: datetime) -> None:
        previous = work.last_active_at if work.last_active_at.tzinfo else work.last_active_at.replace(tzinfo=timezone.utc)
        elapsed = max(0, int((now - previous).total_seconds())); work.active_seconds += min(elapsed, self.idle_seconds); work.estimated = work.estimated or elapsed > 0; work.last_active_at = now; self.session.commit()
    def purge_expired(self, retention_days: int, now: datetime | None = None) -> int:
        cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=retention_days)
        events = list(self.session.scalars(select(ReviewActivity).where(ReviewActivity.created_at < cutoff))); sessions = list(self.session.scalars(select(ReviewWorkSession).where(ReviewWorkSession.last_active_at < cutoff)))
        for item in events + sessions: self.session.delete(item)
        self.session.commit(); return len(events) + len(sessions)
