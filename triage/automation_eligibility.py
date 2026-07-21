"""Measurement-only, deterministic semantic-alignment eligibility reports."""
from __future__ import annotations
import hashlib,json,math
from datetime import datetime,timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from triage.domain.enums import AssessmentJudgment, ConsensusState, CorpusConsentStatus, EligibilityState, ReviewerCohort
from triage.persistence.models import AutomationEligibilityPolicy, CorpusConsent, EligibilityReport, Investigation, ReviewAssessment, ReviewPacket
from triage.review_consensus import ReviewConsensusService
from triage.review_packets import canonical_json

POLICY_VERSION="1.0"; WILSON_Z=1.6448536269514722; THRESHOLD=.99; MIN_SAMPLE=300
def wilson_lower(successes:int,total:int,z:float=WILSON_Z)->float:
 if total<=0:return 0.0
 p=successes/total;d=1+z*z/total;return (p+z*z/(2*total)-z*math.sqrt((p*(1-p)+z*z/(4*total))/total))/d
class EligibilityService:
 def __init__(self,session:Session):self.session=session
 def create_policy(self,key,description,repositories,predicates,operator,now=None):
  data={"cohort_key":key,"description":description,"repositories":sorted(repositories),"predicates":predicates,"policy_version":POLICY_VERSION};now=now or datetime.now(timezone.utc)
  item=AutomationEligibilityPolicy(cohort_key=key,description=description,repositories_json=canonical_json(sorted(repositories)),predicates_json=canonical_json(predicates),policy_version=POLICY_VERSION,policy_hash=hashlib.sha256(canonical_json(data).encode()).hexdigest(),operator_reference=operator,created_at=now);self.session.add(item);self.session.commit();return item
 def evaluate(self,policy_id,operator,now=None):
  now=now or datetime.now(timezone.utc);policy=self.session.get(AutomationEligibilityPolicy,policy_id)
  if policy is None:raise ValueError("Policy not found")
  repos=json.loads(policy.repositories_json); consents=[self._consent(repo,now) for repo in repos]
  if any(c is None for c in consents):return self._save(policy,EligibilityState.DATA_QUALITY_BLOCKED,{"reason":"Missing active evaluation consent"},operator,now)
  predicates=json.loads(policy.predicates_json); packets=list(self.session.scalars(select(ReviewPacket).join(Investigation,ReviewPacket.investigation_id==Investigation.id).where(Investigation.repository.in_(repos),ReviewPacket.created_at<=now)))
  included=[];pending=0;false=0;disagreed=0;states={};tags={}
  for packet in packets:
   inv=self.session.get(Investigation,packet.investigation_id); snap=json.loads(packet.snapshot_json)
   if predicates.get("runners") and snap.get("runner",{}).get("id") not in predicates["runners"]:continue
   if predicates.get("classifications") and inv.classification.value not in predicates["classifications"]:continue
   consensus=ReviewConsensusService(self.session).current(packet.id);state=consensus["state"];states[state]=states.get(state,0)+1
   assessments=list(self.session.scalars(select(ReviewAssessment).where(ReviewAssessment.review_packet_id==packet.id)));coverage={"M":sum(a.reviewer_cohort==ReviewerCohort.MAINTAINER for a in assessments if a.id in consensus["active_assessment_ids"]),"I":sum(a.reviewer_cohort==ReviewerCohort.INDEPENDENT_ENGINEER for a in assessments if a.id in consensus["active_assessment_ids"])}
   for a in assessments:
    for tag in json.loads(a.reason_tags_json):tags[tag]=tags.get(tag,0)+1
   if state==ConsensusState.PENDING_REVIEW.value:pending+=1;continue
   if coverage["M"]<1 or coverage["I"]<2:continue
   included.append((packet,state,assessments));
   if state==ConsensusState.DISAGREED.value:disagreed+=1
   if state==ConsensusState.REJECTED_ALIGNMENT.value or any(any(getattr(a,q)==AssessmentJudgment.NO for q in ("test_aligned","failure_supports_signal","public_comment_appropriate")) for a in assessments if a.id in consensus["active_assessment_ids"]):false+=1
  successes=sum(state==ConsensusState.UNANIMOUSLY_ALIGNED.value for _,state,_ in included);den=len(included);lower=wilson_lower(successes,den)
  if den<MIN_SAMPLE:state=EligibilityState.INSUFFICIENT_SAMPLE
  elif false:state=EligibilityState.FALSE_ALIGNMENT_DETECTED
  elif disagreed:state=EligibilityState.DISAGREEMENT_PRESENT
  elif lower<THRESHOLD:state=EligibilityState.PRECISION_BELOW_THRESHOLD
  else:state=EligibilityState.MEASUREMENT_ELIGIBLE
  report={"policy_id":policy.id,"policy_hash":policy.policy_hash,"policy_version":policy.policy_version,"repositories":repos,"source_cutoff_at":now.isoformat(),"included_packet_ids":[p.id for p,_,_ in included],"counts":{"included":den,"pending_incomplete":pending,"successes":successes,"material_false_alignment":false,"disagreed":disagreed},"consensus_distribution":states,"reason_tags":tags,"statistics":{"method":"one-sided Wilson lower bound 95%, z=1.6448536269514722","point_estimate":successes/den if den else None,"lower_bound":lower,"threshold":THRESHOLD},"state":state.value,"meaning":"Measurement-only; does not change human approval or posting policy."}
  return self._save(policy,state,report,operator,now)
 def _consent(self,repo,now):
  def aware(value): return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
  return next((c for c in self.session.scalars(select(CorpusConsent).where(CorpusConsent.repository==repo)) if c.status==CorpusConsentStatus.ACTIVE and c.purpose=="EVALUATION_ONLY" and aware(c.effective_at)<=now and (c.expires_at is None or aware(c.expires_at)>now)),None)
 def _save(self,policy,state,report,operator,now):
  encoded=canonical_json(report);item=EligibilityReport(policy_id=policy.id,policy_hash=policy.policy_hash,state=state,report_json=encoded,report_hash=hashlib.sha256(encoded.encode()).hexdigest(),source_cutoff_at=now,operator_reference=operator,created_at=now);self.session.add(item);self.session.commit();return item
