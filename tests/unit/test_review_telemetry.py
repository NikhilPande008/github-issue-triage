from datetime import datetime, timedelta, timezone

from triage.domain.enums import Classification, InvestigationStatus, ReviewerCohort
from triage.persistence.database import Base, create_session_factory
from triage.persistence.models import Investigation, ReviewPacket
from triage.review_assessments import PilotReviewer
from triage.review_packets import canonical_json, packet_hash
from triage.review_telemetry import ReviewTelemetryService

def test_review_work_is_distinct_and_idle_capped_and_purge_preserves_packets(tmp_path) -> None:
    factory = create_session_factory(f"sqlite:///{tmp_path / 'telemetry.db'}"); Base.metadata.create_all(factory.kw["bind"])
    with factory() as session:
        inv = Investigation(repository="owner/repo", issue_number=1, status=InvestigationStatus.COMPLETED, classification=Classification.NEEDS_INFO); session.add(inv); session.flush()
        data={"investigation":{"id":inv.id}}; packet=ReviewPacket(investigation_id=inv.id, version=1, schema_version="1.0", snapshot_json=canonical_json(data), integrity_hash=packet_hash(data), created_at=datetime.now(timezone.utc)); session.add(packet); session.commit()
        now=datetime.now(timezone.utc); service=ReviewTelemetryService(session, idle_seconds=60)
        a=service.start(packet.id, inv.id, PilotReviewer("a", ReviewerCohort.MAINTAINER), "session-a", now)
        service.heartbeat(a.id, PilotReviewer("a", ReviewerCohort.MAINTAINER), "session-a", now + timedelta(seconds=600))
        b=service.start(packet.id, inv.id, PilotReviewer("b", ReviewerCohort.INDEPENDENT_ENGINEER), "session-b", now)
        assert a.active_seconds == 60 and a.estimated and b.id != a.id
        assert service.purge_expired(0, now + timedelta(days=1)) > 0
        assert session.get(ReviewPacket, packet.id) is not None
