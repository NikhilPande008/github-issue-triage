"""Consent-gated, evaluation-only semantic-fidelity corpus exports."""
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.orm import Session
from triage.domain.enums import CorpusConsentStatus
from triage.persistence.models import CorpusConsent, CorpusExport, Investigation, PostingApproval, ReviewAssessment, ReviewConsensusSnapshot, ReviewPacket, WebhookJob
from triage.review_packets import canonical_json

CORPUS_SCHEMA_VERSION="1.0"; PURPOSE="EVALUATION_ONLY"
class CorpusExportError(ValueError): pass
class SemanticCorpusService:
 def __init__(self,session:Session):self.session=session
 def active_consent(self,repository:str,now:datetime):
  rows=list(self.session.scalars(select(CorpusConsent).where(CorpusConsent.repository==repository).order_by(CorpusConsent.created_at.desc())))
  aware=lambda value:value if value.tzinfo else value.replace(tzinfo=timezone.utc)
  consent=next((x for x in rows if x.status==CorpusConsentStatus.ACTIVE and x.purpose==PURPOSE and aware(x.effective_at)<=now and (x.expires_at is None or aware(x.expires_at)>now)),None)
  if consent is None: raise CorpusExportError(f"Active evaluation consent is required for {repository}")
  return consent
 def export(self,repositories:list[str],output:Path,operator_reference:str,now:datetime|None=None,runner:str|None=None,consensus_state:str|None=None):
  if not repositories: raise CorpusExportError("At least one repository is required")
  now=now or datetime.now(timezone.utc)
  if output.exists() and any(output.iterdir()): raise CorpusExportError("Output directory must be empty")
  output.mkdir(parents=True,exist_ok=True); consents=[self.active_consent(repo,now) for repo in repositories]
  packets=list(self.session.scalars(select(ReviewPacket).join(Investigation,ReviewPacket.investigation_id==Investigation.id).where(Investigation.repository.in_(repositories),ReviewPacket.created_at<=now).order_by(ReviewPacket.id)))
  examples=[]
  for packet in packets:
   snapshot=json.loads(packet.snapshot_json); inv=session_inv=self.session.get(Investigation,packet.investigation_id)
   if runner and snapshot.get("runner",{}).get("id")!=runner: continue
   consensus=list(self.session.scalars(select(ReviewConsensusSnapshot).where(ReviewConsensusSnapshot.review_packet_id==packet.id).order_by(ReviewConsensusSnapshot.computed_at)))
   latest=json.loads(consensus[-1].snapshot_json) if consensus else {"state":"PENDING_REVIEW"}
   if consensus_state and latest.get("state")!=consensus_state: continue
   assessments=list(self.session.scalars(select(ReviewAssessment).where(ReviewAssessment.review_packet_id==packet.id).order_by(ReviewAssessment.created_at)))
   labels=[{"cohort":a.reviewer_cohort.value,"extraction_aligned":a.extraction_aligned.value,"test_aligned":a.test_aligned.value,"failure_supports_signal":a.failure_supports_signal.value,"public_comment_appropriate":a.public_comment_appropriate.value,"confidence":a.confidence.value,"reason_tags":json.loads(a.reason_tags_json),"supersedes_assessment_id":a.supersedes_assessment_id,"created_date":a.created_at.date().isoformat()} for a in assessments]
   examples.append({"corpus_example_id":hashlib.sha256(packet.integrity_hash.encode()).hexdigest()[:24],"repository":inv.repository,"source":{"packet_id":packet.id,"packet_hash":packet.integrity_hash,"packet_version":packet.version,"issued_at":packet.created_at.date().isoformat()},"runner":snapshot.get("runner"),"extraction":(snapshot.get("extraction") or {}).get("structured_output"),"test_diff":snapshot.get("generated_test_diff"),"junit":snapshot.get("structured_junit_result"),"validation":snapshot.get("deterministic_validation"),"classification":snapshot.get("classification"),"reproducibility_manifest":snapshot.get("reproducibility_manifest"),"versions":snapshot.get("versions"),"assessments":labels,"consensus_history":[{"state":json.loads(x.snapshot_json).get("state"),"coverage":json.loads(x.snapshot_json).get("coverage"),"algorithm_version":x.algorithm_version,"snapshot_hash":x.snapshot_hash} for x in consensus],"posting_outcome":self._posting(packet.investigation_id)})
  lines=[]
  for ex in examples: lines.append(canonical_json({**ex,"example_hash":hashlib.sha256(canonical_json(ex).encode()).hexdigest()}))
  (output/"examples.jsonl").write_text("\n".join(lines)+("\n" if lines else ""),encoding="utf-8")
  manifest={"corpus_schema_version":CORPUS_SCHEMA_VERSION,"purpose":PURPOSE,"repositories":sorted(repositories),"source_cutoff_at":now.isoformat(),"example_count":len(examples),"source_packets":[{"id":p.id,"hash":p.integrity_hash} for p in packets],"consents":[{"id":c.id,"version":c.consent_version,"audit_hash":c.audit_hash} for c in consents],"exclusions":["raw issue body","terminal logs","raw rationale","reviewer/session identity","full repository"],"dataset_card":{"intended_use":"evaluation only","prohibited_use":["automatic public-comment authorization","unconsented training","identity inference"],"limitations":["pilot selection bias","small sample","no universal ground truth","model/prompt version dependence"]}}
  encoded=canonical_json(manifest); manifest["manifest_hash"]=hashlib.sha256(encoded.encode()).hexdigest(); (output/"manifest.json").write_text(canonical_json(manifest),encoding="utf-8")
  row=CorpusExport(repositories_json=canonical_json(sorted(repositories)),consent_provenance_json=canonical_json(manifest["consents"]),purpose=PURPOSE,schema_version=CORPUS_SCHEMA_VERSION,source_cutoff_at=now,manifest_json=canonical_json(manifest),manifest_hash=manifest["manifest_hash"],operator_reference=operator_reference,created_at=now);self.session.add(row);self.session.commit();return row
 def _posting(self,investigation_id):
  job=self.session.scalar(select(WebhookJob).where(WebhookJob.investigation_id==investigation_id).order_by(WebhookJob.created_at.desc()));return job.comment_status.value if job else None
