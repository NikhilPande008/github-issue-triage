"""Deterministic, aggregate-only weekly pilot reporting."""
from __future__ import annotations
import csv, hashlib, io, json
from datetime import date, datetime, timedelta, timezone
from statistics import median
from sqlalchemy import select
from sqlalchemy.orm import Session
from triage.persistence.models import Investigation, PilotWeeklyReport, ReviewAssessment, ReviewPacket, ReviewWorkSession
from triage.review_consensus import ReviewConsensusService
from triage.review_packets import canonical_json

REPORT_SCHEMA_VERSION="1.0"
def weekly_window(week_start: date) -> tuple[datetime, datetime]:
    start=datetime.combine(week_start, datetime.min.time(), tzinfo=timezone.utc); return start, start+timedelta(days=7)
def percentile(values:list[float], p:float):
    if not values:return None
    ordered=sorted(values); return ordered[round((len(ordered)-1)*p)]
def distribution(values):
    return {"count":len(values),"p50":percentile(values,.5),"p90":percentile(values,.9)}

class PilotReportService:
 def __init__(self,session:Session):self.session=session
 def generate(self,repository:str,start:datetime,end:datetime,now:datetime|None=None)->PilotWeeklyReport:
  investigations=list(self.session.scalars(select(Investigation).where(Investigation.repository==repository,Investigation.created_at>=start,Investigation.created_at<end)))
  ids=[x.id for x in investigations]; packets=list(self.session.scalars(select(ReviewPacket).where(ReviewPacket.investigation_id.in_(ids)))) if ids else []
  works=list(self.session.scalars(select(ReviewWorkSession).where(ReviewWorkSession.investigation_id.in_(ids)))) if ids else []; assessments=list(self.session.scalars(select(ReviewAssessment).where(ReviewAssessment.investigation_id.in_(ids)))) if ids else []
  states={}; tags={}
  for packet in packets:
   state=ReviewConsensusService(self.session).current(packet.id)["state"]; states[state]=states.get(state,0)+1
  for assessment in assessments:
   for tag in json.loads(assessment.reason_tags_json):tags[tag]=tags.get(tag,0)+1
  report={"report_schema_version":REPORT_SCHEMA_VERSION,"repository":repository,"period_start":start.isoformat(),"period_end":end.isoformat(),"source_cutoff_at":(now or datetime.now(timezone.utc)).isoformat(),"investigation_funnel":{"total":len(investigations),"status":{s:sum(x.status.value==s for x in investigations) for s in {x.status.value for x in investigations}},"classifications":{c:sum((x.classification.value if x.classification else "UNCLASSIFIED")==c for x in investigations) for c in {(x.classification.value if x.classification else "UNCLASSIFIED") for x in investigations}}},"review_funnel":{"packets_issued":len(packets),"assessments":len(assessments),"consensus":states,"reason_tags":tags,"work_sessions":len(works)},"reviewer_effort":{"total_estimated_active_seconds":sum(x.active_seconds for x in works),"active_seconds":distribution([float(x.active_seconds) for x in works])},"measured_operational_inputs":{"tracked_openai_cost_usd_total":sum(float(x.tracked_openai_cost_usd or 0) for x in investigations),"tracked_openai_cost_per_investigation":distribution([float(x.tracked_openai_cost_usd) for x in investigations if x.tracked_openai_cost_usd is not None]),"codex_wall_seconds":distribution([float(x.codex_wall_seconds or 0) for x in investigations]),"codex_invocations":sum(x.codex_invocation_count for x in investigations)},"caveats":["Estimated review time is idle-capped.","Codex execution has no attributable dollar cost.","Legacy investigations without packets may be omitted from review metrics."],"sample_size":len(investigations)}
  generated=now or datetime.now(timezone.utc); encoded=canonical_json(report); item=PilotWeeklyReport(repository=repository,period_start=start,period_end=end,schema_version=REPORT_SCHEMA_VERSION,report_json=encoded,report_hash=hashlib.sha256(encoded.encode()).hexdigest(),generated_at=generated,source_cutoff_at=generated);self.session.add(item);self.session.commit();self.session.refresh(item);return item
 def csv(self, report:PilotWeeklyReport)->str:
  data=json.loads(report.report_json); out=io.StringIO(); writer=csv.writer(out);writer.writerow(["repository","period_start","period_end","sample_size","tracked_openai_cost_usd_total","estimated_active_seconds"]);writer.writerow([data["repository"],data["period_start"],data["period_end"],data["sample_size"],data["measured_operational_inputs"]["tracked_openai_cost_usd_total"],data["reviewer_effort"]["total_estimated_active_seconds"]]);return out.getvalue()
