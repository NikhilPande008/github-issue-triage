from datetime import date, datetime, timezone
from triage.domain.enums import Classification, InvestigationStatus
from triage.persistence.database import Base, create_session_factory
from triage.persistence.models import Investigation
from triage.pilot_reports import PilotReportService, weekly_window

def test_weekly_window_and_immutable_report_hash(tmp_path):
    start,end=weekly_window(date(2026,7,20)); assert start.isoformat()=="2026-07-20T00:00:00+00:00" and (end-start).days==7
    factory=create_session_factory(f"sqlite:///{tmp_path/'report.db'}"); Base.metadata.create_all(factory.kw['bind'])
    with factory() as session:
        session.add(Investigation(repository="owner/repo",issue_number=1,status=InvestigationStatus.COMPLETED,classification=Classification.NEEDS_INFO,created_at=start));session.commit()
        first=PilotReportService(session).generate("owner/repo",start,end,datetime(2026,7,27,tzinfo=timezone.utc)); second=PilotReportService(session).generate("owner/repo",start,end,datetime(2026,7,27,tzinfo=timezone.utc))
        assert first.id!=second.id and first.report_hash==second.report_hash and "secret" not in first.report_json
