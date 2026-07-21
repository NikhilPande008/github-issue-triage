from datetime import datetime,timezone
import hashlib
import pytest
from triage.domain.enums import CorpusConsentStatus
from triage.persistence.database import Base,create_session_factory
from triage.persistence.models import CorpusConsent
from triage.provider_comparison import ProviderComparisonService
def test_comparison_plan_requires_consent_and_bounds(tmp_path):
 factory=create_session_factory(f"sqlite:///{tmp_path/'compare.db'}");Base.metadata.create_all(factory.kw['bind']);now=datetime(2026,7,21,tzinfo=timezone.utc)
 with factory() as session:
  service=ProviderComparisonService(session)
  with pytest.raises(ValueError):service.plan("owner/repo","codex","claude_code",1,60,"op",tmp_path/'out',now)
  session.add(CorpusConsent(repository="owner/repo",purpose="EVALUATION_ONLY",status=CorpusConsentStatus.ACTIVE,consent_version="1",operator_reference="op",allowed_data_classes_json="[]",retention_policy_reference="x",effective_at=now,expires_at=None,audit_hash="a"*64,created_at=now));session.commit()
  plan=service.plan("owner/repo","codex","claude_code",1,60,"op",tmp_path/'out',now);assert plan["candidate_provider"]=="claude_code" and "PENDING" in plan["semantic_alignment"]
