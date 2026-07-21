import hashlib, json
from datetime import datetime, timezone
import pytest
from triage.domain.enums import Classification, CorpusConsentStatus, InvestigationStatus
from triage.persistence.database import Base, create_session_factory
from triage.persistence.models import CorpusConsent, Investigation, ReviewPacket
from triage.semantic_corpus import CorpusExportError, SemanticCorpusService
from triage.review_packets import canonical_json, packet_hash

def test_consent_gated_evaluation_export_is_bounded_and_revocable(tmp_path):
 factory=create_session_factory(f"sqlite:///{tmp_path/'corpus.db'}");Base.metadata.create_all(factory.kw['bind']);now=datetime(2026,7,21,tzinfo=timezone.utc)
 with factory() as session:
  inv=Investigation(repository="owner/repo",issue_number=1,status=InvestigationStatus.COMPLETED,classification=Classification.NEEDS_INFO);session.add(inv);session.flush();snap={"investigation":{"id":inv.id},"generated_test_diff":{"content_excerpt":"bounded"},"classification":{"primary":"NEEDS_INFO"}};packet=ReviewPacket(investigation_id=inv.id,version=1,schema_version="1",snapshot_json=canonical_json(snap),integrity_hash=packet_hash(snap),created_at=now);session.add(packet);session.commit()
  service=SemanticCorpusService(session)
  with pytest.raises(CorpusExportError):service.export(["owner/repo"],tmp_path/'missing','operator',now)
  consent=CorpusConsent(repository="owner/repo",purpose="EVALUATION_ONLY",status=CorpusConsentStatus.ACTIVE,consent_version="1",operator_reference="org",allowed_data_classes_json="[]",retention_policy_reference="90d",effective_at=now,expires_at=None,audit_hash=hashlib.sha256(b"consent").hexdigest(),created_at=now);session.add(consent);session.commit()
  result=service.export(["owner/repo"],tmp_path/'out','operator',now);manifest=json.loads((tmp_path/'out'/'manifest.json').read_text());example=(tmp_path/'out'/'examples.jsonl').read_text()
  assert result.manifest_hash==manifest['manifest_hash'] and 'terminal' not in example and 'EVALUATION_ONLY'==manifest['purpose']
  consent.status=CorpusConsentStatus.REVOKED;session.commit()
  with pytest.raises(CorpusExportError):service.export(["owner/repo"],tmp_path/'revoked','operator',now)
