from datetime import datetime,timezone
from triage.automation_eligibility import EligibilityService,wilson_lower
from triage.domain.enums import CorpusConsentStatus
from triage.persistence.database import Base,create_session_factory
from triage.persistence.models import CorpusConsent

def test_wilson_vectors_and_missing_consent_blocks(tmp_path):
 assert wilson_lower(0,1)==0 and wilson_lower(300,300)>.99 and wilson_lower(299,300)<.99
 factory=create_session_factory(f"sqlite:///{tmp_path/'eligibility.db'}");Base.metadata.create_all(factory.kw['bind']);now=datetime(2026,7,21,tzinfo=timezone.utc)
 with factory() as session:
  service=EligibilityService(session);policy=service.create_policy("pytest-needs-info","test",["owner/repo"],{"runners":["pytest"]},"operator",now)
  report=service.evaluate(policy.id,"operator",now)
  assert report.state.value=="DATA_QUALITY_BLOCKED"
  session.add(CorpusConsent(repository="owner/repo",purpose="EVALUATION_ONLY",status=CorpusConsentStatus.ACTIVE,consent_version="1",operator_reference="org",allowed_data_classes_json="[]",retention_policy_reference="x",effective_at=now,expires_at=None,audit_hash="a"*64,created_at=now));session.commit()
  report=service.evaluate(policy.id,"operator",now);assert report.state.value=="INSUFFICIENT_SAMPLE" and "Measurement-only" in report.report_json
