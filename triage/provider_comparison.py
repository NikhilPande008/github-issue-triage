"""Bounded consent-gated provider comparison planning; execution is operator-approved."""
from __future__ import annotations
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path
from triage.semantic_corpus import SemanticCorpusService
from triage.persistence.models import ReviewPacket,Investigation
from sqlalchemy import select
class ProviderComparisonService:
 def __init__(self,session):self.session=session
 def plan(self,repository,baseline,candidate,max_examples,max_wall_seconds,operator,output,now=None):
  if max_examples<1 or max_examples>50 or max_wall_seconds<1:raise ValueError("Comparison requires bounded example count and wall-time limit")
  now=now or datetime.now(timezone.utc);SemanticCorpusService(self.session).active_consent(repository,now)
  packets=list(self.session.scalars(select(ReviewPacket).join(Investigation,ReviewPacket.investigation_id==Investigation.id).where(Investigation.repository==repository).limit(max_examples)))
  manifest={"comparison_schema_version":"1.0","purpose":"EVALUATION_ONLY","repository":repository,"baseline_provider":baseline,"candidate_provider":candidate,"max_examples":max_examples,"max_unpriced_agent_wall_seconds":max_wall_seconds,"operator":operator,"source_packets":[{"id":p.id,"hash":p.integrity_hash} for p in packets],"semantic_alignment":"PENDING independent review; mechanical completion is not provider superiority."}
  manifest["manifest_hash"]=hashlib.sha256(json.dumps(manifest,sort_keys=True,separators=(",",":")).encode()).hexdigest();output.mkdir(parents=True,exist_ok=True);(output/"provider-comparison-plan.json").write_text(json.dumps(manifest,sort_keys=True),encoding="utf-8");return manifest
