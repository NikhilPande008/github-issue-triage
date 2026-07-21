from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from triage.config.settings import Settings
from triage.domain.enums import AssessmentConfidence, AssessmentJudgment, Classification
from triage.llm.pricing import OPENAI_PROVIDER
from triage.persistence.database import create_session_factory
import json
from triage.persistence.models import Artifact, DuplicateCandidate, Hypothesis, Investigation, LLMCall, PostingApproval, ReviewActivity, ReviewAssessment, ReviewConsensusSnapshot, ReviewPacket, ReviewWorkSession, SimilarityDocument, WebhookJob
from triage.posting_approvals import PostingApprovalService
from triage.pilot_sessions import COOKIE_NAME, create_session, destroy_session, get_session as get_pilot_session
from triage.review_assessments import AssessmentPermissionError, ReviewAssessmentService, verify_pilot_reviewer
from triage.review_consensus import ReviewConsensusService
from triage.review_telemetry import ReviewTelemetryService
from triage.pilot_reports import PilotReportService, weekly_window
from triage.semantic_review import consensus_label, packet_semantic_evidence, review_outcome
from triage.validation.explainer import explain as explain_validation

router = APIRouter(prefix="/investigations", tags=["investigations"])
review_packets_router = APIRouter(prefix="/review-packets", tags=["review-packets"])
pilot_router = APIRouter(prefix="/pilot-review", tags=["pilot-review"])


def get_session():
    factory = create_session_factory(Settings().database_url)
    with factory() as session:
        yield session


class AssessmentCreate(BaseModel):
    extraction_aligned: AssessmentJudgment
    test_aligned: AssessmentJudgment
    failure_supports_signal: AssessmentJudgment
    public_comment_appropriate: AssessmentJudgment
    confidence: AssessmentConfidence
    rationale: str | None = Field(default=None, max_length=4_000)
    reason_tags: list[str] = Field(default_factory=list, max_length=5)
    supersedes_assessment_id: str | None = None


class PostingApprovalCreate(BaseModel):
    rationale: str | None = Field(default=None, max_length=2_000)

class PilotLogin(BaseModel):
    reviewer_id: str = Field(min_length=1, max_length=128)
    token: str = Field(min_length=1, max_length=512)

class ReviewWorkAction(BaseModel):
    packet_id: str | None = None
    work_session_id: str | None = None


def _pilot_reviewer(request: Request, settings: Settings, reviewer_id: str | None, token: str | None):
    session = get_pilot_session(request.cookies.get(COOKIE_NAME))
    if session is not None:
        if request.headers.get("X-CSRF-Token") != session.csrf_token:
            raise HTTPException(status_code=403, detail="CSRF validation failed")
        return session.reviewer
    # Compatibility boundary for existing non-browser internal clients. Browser
    # UI uses the cookie session and never sends registry credentials again.
    try:
        return verify_pilot_reviewer(settings.pilot_reviewer_registry, reviewer_id, token)
    except AssessmentPermissionError:
        raise HTTPException(status_code=403, detail="Pilot reviewer verification failed") from None


@pilot_router.post("/login")
def pilot_login(payload: PilotLogin, response: Response) -> dict[str, object]:
    settings = Settings()
    if not settings.pilot_review_enabled: raise HTTPException(status_code=404, detail="Not found")
    try:
        session_id, item = create_session(settings.pilot_reviewer_registry, payload.reviewer_id, payload.token, settings.pilot_session_ttl_seconds)
    except AssessmentPermissionError:
        raise HTTPException(status_code=403, detail="Pilot reviewer verification failed") from None
    response.set_cookie(COOKIE_NAME, session_id, max_age=settings.pilot_session_ttl_seconds, httponly=True, samesite="strict", secure=settings.pilot_session_secure_cookie, path="/")
    return {"reviewer": {"external_id": item.reviewer.external_id, "cohort": item.reviewer.cohort.value, "posting_approver": item.reviewer.posting_approver, "repositories": sorted(item.reviewer.repositories)}, "csrf_token": item.csrf_token, "expires_at": _timestamp(item.expires_at)}


@pilot_router.post("/logout")
def pilot_logout(request: Request, response: Response) -> dict[str, bool]:
    item = get_pilot_session(request.cookies.get(COOKIE_NAME))
    if item is not None and request.headers.get("X-CSRF-Token") != item.csrf_token: raise HTTPException(status_code=403, detail="CSRF validation failed")
    destroy_session(request.cookies.get(COOKIE_NAME)); response.delete_cookie(COOKIE_NAME, path="/")
    return {"logged_out": True}


@pilot_router.get("/me")
def pilot_me(request: Request) -> dict[str, object]:
    item = get_pilot_session(request.cookies.get(COOKIE_NAME))
    if item is None: raise HTTPException(status_code=401, detail="Pilot session required")
    return {"reviewer": {"external_id": item.reviewer.external_id, "cohort": item.reviewer.cohort.value, "posting_approver": item.reviewer.posting_approver, "repositories": sorted(item.reviewer.repositories)}, "csrf_token": item.csrf_token, "expires_at": _timestamp(item.expires_at)}


@pilot_router.get("/queue")
def pilot_queue(request: Request, repository: str | None = None, consensus_state: str | None = None, classification: Classification | None = None, posting: str | None = None, session: Session = Depends(get_session)) -> dict[str, object]:
    settings = Settings()
    if not settings.pilot_review_enabled: raise HTTPException(status_code=404, detail="Not found")
    if get_pilot_session(request.cookies.get(COOKIE_NAME)) is None: raise HTTPException(status_code=401, detail="Pilot session required")
    reviewer = get_pilot_session(request.cookies.get(COOKIE_NAME)); assert reviewer is not None
    rows = list(session.scalars(select(Investigation).where(Investigation.classification.is_not(None)).order_by(Investigation.created_at)))
    items = []
    for investigation in rows:
        if investigation.repository.lower() not in reviewer.reviewer.repositories: continue
        if repository and investigation.repository.lower() != repository.lower(): continue
        if classification and investigation.classification != classification: continue
        packet = session.scalar(select(ReviewPacket).where(ReviewPacket.investigation_id == investigation.id).order_by(ReviewPacket.version.desc()))
        if packet is None: continue
        consensus = _current_consensus_payload(session, packet)
        job = session.scalar(select(WebhookJob).where(WebhookJob.investigation_id == investigation.id).order_by(WebhookJob.created_at.desc()))
        eligibility = PostingApprovalService(session).eligibility(investigation.id)
        needs_attention = consensus["state"] in {"PENDING_REVIEW", "DISAGREED", "INSUFFICIENT_CONTEXT"} or (job is not None and job.comment_status.value in {"REVIEW_REQUIRED", "APPROVAL_EXPIRED", "CONSENSUS_REQUIRED", "PROPOSED"})
        if not needs_attention or (consensus_state and consensus["state"] != consensus_state) or (posting and str(eligibility["status"]) != posting): continue
        items.append({"investigation_id": investigation.id, "repository": investigation.repository, "issue_number": investigation.issue_number, "issue_title": investigation.issue_title, "classification": investigation.classification.value, "asserts_failure": investigation.asserts_failure, "consensus_state": consensus["state"], "coverage": consensus.get("coverage", {}), "comment_status": job.comment_status.value if job else None, "posting_eligibility": eligibility["status"], "review_age_started_at": _timestamp(investigation.classification_completed_at or investigation.created_at), "tracked_openai_cost_usd": float(investigation.tracked_openai_cost_usd) if investigation.tracked_openai_cost_usd is not None else None, "codex_wall_seconds": float(investigation.codex_wall_seconds or 0), "packet_id": packet.id, "packet_hash": packet.integrity_hash, "packet_version": packet.version})
    priority = {"DISAGREED": 0, "CONSENSUS_REQUIRED": 1, "REVIEW_REQUIRED": 2, "PENDING_REVIEW": 3, "INSUFFICIENT_CONTEXT": 4}
    items.sort(key=lambda item: (priority.get(str(item["consensus_state"]), priority.get(str(item["posting_eligibility"]), 9)), str(item["review_age_started_at"] or "")))
    return {"items": items}


@pilot_router.post("/review-work/start")
def start_review_work(payload: ReviewWorkAction, request: Request, session: Session = Depends(get_session)) -> dict[str, object]:
    settings = Settings(); reviewer = _pilot_reviewer(request, settings, None, None)
    if not payload.packet_id: raise HTTPException(status_code=422, detail="packet_id is required")
    packet = session.get(ReviewPacket, payload.packet_id)
    if packet is None: raise HTTPException(status_code=404, detail="Review packet not found")
    work = ReviewTelemetryService(session, settings.pilot_review_idle_timeout_seconds).start(packet.id, packet.investigation_id, reviewer, request.cookies.get(COOKIE_NAME))
    return {"work_session_id": work.id, "active_seconds": work.active_seconds, "estimated": work.estimated}


@pilot_router.post("/review-work/heartbeat")
def heartbeat_review_work(payload: ReviewWorkAction, request: Request, session: Session = Depends(get_session)) -> dict[str, object]:
    settings = Settings(); reviewer = _pilot_reviewer(request, settings, None, None)
    if not payload.work_session_id: raise HTTPException(status_code=422, detail="work_session_id is required")
    try: work = ReviewTelemetryService(session, settings.pilot_review_idle_timeout_seconds).heartbeat(payload.work_session_id, reviewer, request.cookies.get(COOKIE_NAME))
    except ValueError as error: raise HTTPException(status_code=404, detail=str(error)) from None
    return {"work_session_id": work.id, "active_seconds": work.active_seconds, "estimated": work.estimated}


@pilot_router.post("/review-work/complete")
def complete_review_work(payload: ReviewWorkAction, request: Request, session: Session = Depends(get_session)) -> dict[str, object]:
    settings = Settings(); reviewer = _pilot_reviewer(request, settings, None, None)
    if not payload.work_session_id: raise HTTPException(status_code=422, detail="work_session_id is required")
    try: work = ReviewTelemetryService(session, settings.pilot_review_idle_timeout_seconds).complete(payload.work_session_id, reviewer, request.cookies.get(COOKIE_NAME))
    except ValueError as error: raise HTTPException(status_code=404, detail=str(error)) from None
    return {"work_session_id": work.id, "active_seconds": work.active_seconds, "estimated": work.estimated, "completed": True}


@pilot_router.get("/metrics/investigations/{investigation_id}")
def pilot_investigation_metrics(investigation_id: str, request: Request, session: Session = Depends(get_session)) -> dict[str, object]:
    pilot = get_pilot_session(request.cookies.get(COOKIE_NAME))
    if pilot is None: raise HTTPException(status_code=401, detail="Pilot session required")
    investigation = _get_investigation(session, investigation_id)
    if investigation.repository.lower() not in pilot.reviewer.repositories: raise HTTPException(status_code=404, detail="Investigation not found")
    works = list(session.scalars(select(ReviewWorkSession).where(ReviewWorkSession.investigation_id == investigation_id)))
    assessments = list(session.scalars(select(ReviewAssessment).where(ReviewAssessment.investigation_id == investigation_id)))
    packet = session.scalar(select(ReviewPacket).where(ReviewPacket.investigation_id == investigation_id).order_by(ReviewPacket.version.desc()))
    consensus = _current_consensus_payload(session, packet) if packet else None
    first_open = min((work.started_at for work in works), default=None)
    return {"investigation_id": investigation_id, "measured_operational_inputs": {"tracked_openai_cost_usd": float(investigation.tracked_openai_cost_usd) if investigation.tracked_openai_cost_usd is not None else None, "codex_invocation_count": investigation.codex_invocation_count, "codex_wall_seconds": float(investigation.codex_wall_seconds or 0), "attempt_count": session.scalar(select(func.count()).select_from(Hypothesis).where(Hypothesis.investigation_id == investigation_id)) or 0}, "review": {"work_session_count": len(works), "estimated_active_seconds": sum(work.active_seconds for work in works), "assessment_count": len(assessments), "first_review_at": _timestamp(first_open), "time_to_first_review_seconds": ((first_open - packet.created_at).total_seconds() if first_open and packet and packet.created_at else None), "consensus_state": consensus["state"] if consensus else "PENDING_REVIEW", "time_to_consensus_seconds": None}}


@pilot_router.get("/metrics/repositories/{repository}")
def pilot_repository_metrics(repository: str, request: Request, days: int = Query(30, ge=1, le=365), session: Session = Depends(get_session)) -> dict[str, object]:
    pilot = get_pilot_session(request.cookies.get(COOKIE_NAME))
    if pilot is None: raise HTTPException(status_code=401, detail="Pilot session required")
    if repository.lower() not in pilot.reviewer.repositories: raise HTTPException(status_code=404, detail="Repository not found")
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    investigations = list(session.scalars(select(Investigation).where(Investigation.repository == repository, Investigation.created_at >= cutoff)))
    ids = [item.id for item in investigations]
    works = list(session.scalars(select(ReviewWorkSession).where(ReviewWorkSession.investigation_id.in_(ids)))) if ids else []
    return {"repository": repository, "days": days, "funnel": {"investigations": len(investigations), "work_sessions": len(works), "estimated_active_seconds": sum(item.active_seconds for item in works)}, "measured_operational_inputs": {"tracked_openai_cost_usd": sum(float(item.tracked_openai_cost_usd or 0) for item in investigations), "codex_wall_seconds": sum(float(item.codex_wall_seconds or 0) for item in investigations)}}


@pilot_router.get("/reports/weekly")
def weekly_report(repository: str, week_start: str, request: Request, session: Session = Depends(get_session)) -> dict[str, object]:
    pilot = get_pilot_session(request.cookies.get(COOKIE_NAME))
    if pilot is None: raise HTTPException(status_code=401, detail="Pilot session required")
    if repository.lower() not in pilot.reviewer.repositories: raise HTTPException(status_code=404, detail="Repository not found")
    try: start, end = weekly_window(datetime.fromisoformat(week_start).date())
    except ValueError: raise HTTPException(status_code=422, detail="week_start must be an ISO date") from None
    report = PilotReportService(session).generate(repository, start, end)
    return {"id":report.id,"report_hash":report.report_hash,"generated_at":_timestamp(report.generated_at),"report":json.loads(report.report_json)}


@pilot_router.get("/reports/weekly/export.csv")
def weekly_report_csv(repository: str, week_start: str, request: Request, session: Session = Depends(get_session)) -> Response:
    payload = weekly_report(repository, week_start, request, session)
    report = session.get(__import__("triage.persistence.models",fromlist=["PilotWeeklyReport"]).PilotWeeklyReport,payload["id"])
    return Response(PilotReportService(session).csv(report), media_type="text/csv", headers={"Content-Disposition":"attachment; filename=pilot-weekly-report.csv"})


def _timestamp(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _duration_seconds(investigation: Investigation) -> float | None:
    if investigation.created_at is None:
        return None
    end = investigation.classification_completed_at or investigation.updated_at
    if end is None:
        return None
    return max(0.0, (end - investigation.created_at).total_seconds())


def _tracked_llm_metrics(calls: list[LLMCall]) -> dict[str, object]:
    """Aggregate only linked, priced OpenAI API calls; Codex is intentionally excluded."""
    tracked_calls = [call for call in calls if call.provider == OPENAI_PROVIDER]
    caveat = "Tracked LLM API cost and latency include linked OpenAI API calls only; Codex usage is excluded because exact Codex billing data is unavailable."
    if not tracked_calls:
        return {
            "tracked_llm_api_cost_usd": None,
            "tracked_llm_api_latency_ms": None,
            "tracked_llm_api_input_tokens": None,
            "tracked_llm_api_cached_input_tokens": None,
            "tracked_llm_api_output_tokens": None,
            "tracked_llm_api_cost_status": "unavailable",
            "tracked_llm_api_latency_status": "unavailable",
            "tracked_llm_api_explanation": "No tracked LLM API calls are linked to this investigation. " + caveat,
        }
    cost_available = all(call.cost_usd is not None for call in tracked_calls)
    cost = sum((Decimal(call.cost_usd) for call in tracked_calls if call.cost_usd is not None), Decimal("0"))
    return {
        "tracked_llm_api_cost_usd": float(cost) if cost_available else None,
        "tracked_llm_api_latency_ms": sum(call.latency_ms for call in tracked_calls),
        "tracked_llm_api_input_tokens": sum(call.input_tokens for call in tracked_calls),
        "tracked_llm_api_cached_input_tokens": sum(call.cached_input_tokens for call in tracked_calls),
        "tracked_llm_api_output_tokens": sum(call.output_tokens for call in tracked_calls),
        "tracked_llm_api_cost_status": "available" if cost_available else "unavailable",
        "tracked_llm_api_latency_status": "available",
        "tracked_llm_api_explanation": caveat if cost_available else "A linked LLM API call has unknown pricing; cost is unavailable. " + caveat,
    }


def _investigation_payload(
    investigation: Investigation, attempt_count: int, tracked_metrics: dict[str, object] | None = None
) -> dict[str, object]:
    tracked_metrics = tracked_metrics or _tracked_llm_metrics([])
    return {
        "id": investigation.id,
        "repository": investigation.repository,
        "issue_number": investigation.issue_number,
        "issue_title": investigation.issue_title,
        "test_runner": investigation.test_runner,
        "status": investigation.status.value,
        "classification": investigation.classification.value if investigation.classification else None,
        "asserts_failure": investigation.asserts_failure,
        "validation_reason": investigation.validation_reason,
        "validation_provenance": "Structured test results" if investigation.asserts_failure else None,
        "tracked_openai_cost_usd": float(investigation.tracked_openai_cost_usd) if investigation.tracked_openai_cost_usd is not None else None,
        "reserved_openai_cost_usd": float(investigation.reserved_openai_cost_usd or 0),
        "codex_invocation_count": investigation.codex_invocation_count,
        "codex_wall_seconds": float(investigation.codex_wall_seconds or 0),
        "codex_wall_cap_seconds": investigation.codex_wall_cap_seconds,
        "budget_status": investigation.budget_status.value,
        "budget_reason": investigation.budget_reason,
        "attempt_count": attempt_count,
        "started_at": _timestamp(investigation.created_at),
        "updated_at": _timestamp(investigation.updated_at),
        "completed_at": _timestamp(investigation.classification_completed_at),
        "duration_seconds": _duration_seconds(investigation),
        # Legacy generic cost is kept for compatibility, but now has the same
        # honest OpenAI-only availability semantics as the tracked metric.
        "cost_usd": tracked_metrics["tracked_llm_api_cost_usd"],
        **tracked_metrics,
    }


def _get_investigation(session: Session, investigation_id: str) -> Investigation:
    investigation = session.get(Investigation, investigation_id)
    if investigation is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return investigation


def _require_packet_scope(session: Session, packet: ReviewPacket, reviewer) -> Investigation:
    investigation = _get_investigation(session, packet.investigation_id)
    if investigation.repository.lower() not in reviewer.repositories:
        raise HTTPException(status_code=404, detail="Review packet not found")
    return investigation


def _review_packet_payload(packet: ReviewPacket, *, include_snapshot: bool = True) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": packet.id,
        "investigation_id": packet.investigation_id,
        "version": packet.version,
        "schema_version": packet.schema_version,
        "integrity_hash": packet.integrity_hash,
        "created_at": _timestamp(packet.created_at),
    }
    if include_snapshot:
        payload["snapshot"] = json.loads(packet.snapshot_json)
    return payload


def _public_review_packet_payload(packet: ReviewPacket) -> dict[str, object]:
    return {"id": packet.id, "investigation_id": packet.investigation_id, "version": packet.version, "schema_version": packet.schema_version, "created_at": _timestamp(packet.created_at)}


def _assessment_payload(assessment: ReviewAssessment) -> dict[str, object]:
    return {
        "id": assessment.id, "review_packet_id": assessment.review_packet_id,
        "investigation_id": assessment.investigation_id, "packet_hash": assessment.packet_hash,
        "packet_version": assessment.packet_version, "reviewer_external_id": assessment.reviewer_external_id,
        "reviewer_cohort": assessment.reviewer_cohort.value, "schema_version": assessment.schema_version,
        "extraction_aligned": assessment.extraction_aligned.value, "test_aligned": assessment.test_aligned.value,
        "failure_supports_signal": assessment.failure_supports_signal.value,
        "public_comment_appropriate": assessment.public_comment_appropriate.value,
        "derived_review_outcome": review_outcome(assessment.extraction_aligned, assessment.test_aligned, assessment.failure_supports_signal, assessment.public_comment_appropriate),
        "confidence": assessment.confidence.value, "rationale": assessment.rationale,
        "reason_tags": json.loads(assessment.reason_tags_json),
        "supersedes_assessment_id": assessment.supersedes_assessment_id, "created_at": _timestamp(assessment.created_at),
    }


def _posting_approval_payload(approval: PostingApproval) -> dict[str, object]:
    return {"id": approval.id, "investigation_id": approval.investigation_id, "review_packet_id": approval.review_packet_id, "packet_hash": approval.packet_hash, "packet_version": approval.packet_version, "consensus_snapshot_id": approval.consensus_snapshot_id, "consensus_snapshot_hash": approval.consensus_snapshot_hash, "consensus_algorithm_version": approval.consensus_algorithm_version, "comment_body_hash": approval.comment_body_hash, "classification": approval.classification.value, "comment_type": approval.comment_type, "policy_version": approval.policy_version, "reviewer_external_id": approval.reviewer_external_id, "reviewer_cohort": approval.reviewer_cohort.value, "reviewer_role": approval.reviewer_role, "status": approval.status.value, "rationale": approval.rationale, "approval_hash": approval.approval_hash, "created_at": _timestamp(approval.created_at), "expires_at": _timestamp(approval.expires_at)}


def _consensus_snapshot_payload(snapshot: ReviewConsensusSnapshot) -> dict[str, object]:
    return {"id": snapshot.id, "review_packet_id": snapshot.review_packet_id, "investigation_id": snapshot.investigation_id, "packet_hash": snapshot.packet_hash, "packet_version": snapshot.packet_version, "algorithm_version": snapshot.algorithm_version, "state": snapshot.state.value, "snapshot": json.loads(snapshot.snapshot_json), "snapshot_hash": snapshot.snapshot_hash, "computed_at": _timestamp(snapshot.computed_at)}


def _current_consensus_payload(session: Session, packet: ReviewPacket) -> dict[str, object]:
    try:
        current = ReviewConsensusService(session).current(packet.id)
        latest = session.scalar(select(ReviewConsensusSnapshot).where(ReviewConsensusSnapshot.review_packet_id == packet.id).order_by(ReviewConsensusSnapshot.computed_at.desc(), ReviewConsensusSnapshot.id.desc()))
        return {**current, "display_state": consensus_label(str(current.get("state"))), "latest_snapshot_hash": latest.snapshot_hash if latest else None, "latest_snapshot_at": _timestamp(latest.computed_at) if latest else None}
    except Exception:
        return {"packet_id": packet.id, "packet_hash": packet.integrity_hash, "packet_version": packet.version, "state": "UNAVAILABLE", "display_state": "Review evidence unavailable", "coverage": {"MAINTAINER": 0, "INDEPENDENT_ENGINEER": 0}, "algorithm_version": "1.0", "disagreement": [], "unavailable_reason": "Consensus calculation unavailable.", "latest_snapshot_hash": None, "latest_snapshot_at": None}


def _webhook_job_payload(job: WebhookJob) -> dict[str, object]:
    return {
        "id": job.id, "delivery_id": job.delivery_id, "repository": job.repository,
        "issue_number": job.issue_number, "source": job.source.value, "status": job.status.value,
        "priority": job.priority, "attempt_count": job.attempt_count, "max_attempts": job.max_attempts,
        "lease_owner": job.lease_owner, "lease_expires_at": _timestamp(job.lease_expires_at),
        "next_eligible_at": _timestamp(job.next_eligible_at),
        "investigation_id": job.investigation_id, "error_reason": job.error_reason,
        "comment_status": job.comment_status.value, "comment_reason": job.comment_reason,
        "comment_body": job.posted_comment_body or job.proposed_comment_body,
        "github_comment_id": job.github_comment_id, "is_preview": job.comment_status.value == "PROPOSED",
        "posting_approval_id": job.posting_approval_id, "posting_approval_hash": job.posting_approval_hash,
        "created_at": _timestamp(job.created_at), "started_at": _timestamp(job.started_at), "completed_at": _timestamp(job.completed_at),
        "queue_wait_seconds": ((job.started_at - job.created_at).total_seconds() if job.started_at and job.created_at else None),
        "execution_seconds": ((job.completed_at - job.started_at).total_seconds() if job.completed_at and job.started_at else None),
    }


@router.get("/webhook-jobs")
def list_webhook_jobs(session: Session = Depends(get_session)) -> dict[str, object]:
    jobs = list(session.scalars(select(WebhookJob).order_by(WebhookJob.created_at.desc()).limit(100)))
    active = [job for job in jobs if job.status.value in {"QUEUED", "RETRY_SCHEDULED"}]
    running = [job for job in jobs if job.status.value == "RUNNING"]
    return {"items": [_webhook_job_payload(job) for job in jobs], "queue_depth": len(active), "running_count": len(running)}


@router.get("")
def list_investigations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    classification: Classification | None = None,
    session: Session = Depends(get_session),
) -> dict[str, object]:
    statement = select(Investigation)
    count_statement = select(func.count()).select_from(Investigation)
    if classification is not None:
        statement = statement.where(Investigation.classification == classification)
        count_statement = count_statement.where(Investigation.classification == classification)
    investigations = list(
        session.scalars(
            statement.order_by(Investigation.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
    )
    counts = dict(
        session.execute(
            select(Hypothesis.investigation_id, func.count(Hypothesis.id)).group_by(Hypothesis.investigation_id)
        ).all()
    )
    calls_by_investigation: dict[str, list[LLMCall]] = {}
    if investigations:
        for call in session.scalars(select(LLMCall).where(LLMCall.investigation_id.in_([item.id for item in investigations]))):
            if call.investigation_id is not None:
                calls_by_investigation.setdefault(call.investigation_id, []).append(call)
    return {
        "items": [
            _investigation_payload(item, counts.get(item.id, 0), _tracked_llm_metrics(calls_by_investigation.get(item.id, [])))
            for item in investigations
        ],
        "page": page,
        "page_size": page_size,
        "total": session.scalar(count_statement) or 0,
    }


@router.get("/{investigation_id}")
def get_investigation(investigation_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    investigation = _get_investigation(session, investigation_id)
    attempt_count = session.scalar(
        select(func.count()).select_from(Hypothesis).where(Hypothesis.investigation_id == investigation.id)
    ) or 0
    calls = list(session.scalars(select(LLMCall).where(LLMCall.investigation_id == investigation.id)))
    payload = _investigation_payload(investigation, attempt_count, tracked_metrics=_tracked_llm_metrics(calls))
    job = session.scalar(select(WebhookJob).where(WebhookJob.investigation_id == investigation.id))
    if job is not None:
        payload["webhook_job"] = _webhook_job_payload(job)
    has_manifest = session.scalar(select(func.count()).select_from(Artifact).where(Artifact.investigation_id == investigation.id, Artifact.kind == "reproducibility_manifest")) or 0
    payload["reproducibility_status"] = ("STABLE" if investigation.asserts_failure and has_manifest else "NOT_CONFIRMED" if has_manifest else "LEGACY")
    return payload


@router.get("/{investigation_id}/review-packets")
def list_review_packets(investigation_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    investigation = _get_investigation(session, investigation_id)
    packets = list(session.scalars(select(ReviewPacket).where(ReviewPacket.investigation_id == investigation_id).order_by(ReviewPacket.version)))
    if packets:
        status, reason = "AVAILABLE", None
    elif investigation.review_packet_status == "UNAVAILABLE":
        status, reason = "UNAVAILABLE", investigation.review_packet_reason
    else:
        status, reason = "NOT_ISSUED", "No immutable review packet has been issued for this investigation."
    return {"status": status, "reason": reason, "items": [_public_review_packet_payload(packet) for packet in packets]}


@router.get("/{investigation_id}/review-assessments")
def list_investigation_assessments(investigation_id: str, request: Request, x_pilot_reviewer: str | None = Header(default=None), x_pilot_review_token: str | None = Header(default=None), session: Session = Depends(get_session)) -> dict[str, object]:
    investigation = _get_investigation(session, investigation_id)
    settings = Settings()
    if not settings.pilot_review_enabled:
        raise HTTPException(status_code=404, detail="Not found")
    reviewer = _pilot_reviewer(request, settings, x_pilot_reviewer, x_pilot_review_token)
    if investigation.repository.lower() not in reviewer.repositories:
        raise HTTPException(status_code=404, detail="Investigation not found")
    assessments = list(session.scalars(select(ReviewAssessment).where(ReviewAssessment.investigation_id == investigation_id).order_by(ReviewAssessment.created_at, ReviewAssessment.id)))
    return {"items": [_assessment_payload(item) for item in assessments]}


@router.get("/{investigation_id}/semantic-review")
def semantic_review_summary(investigation_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    """Public, read-only aggregate review provenance with no reviewer data."""
    investigation = _get_investigation(session, investigation_id)
    packet = session.scalar(select(ReviewPacket).where(ReviewPacket.investigation_id == investigation.id).order_by(ReviewPacket.version.desc()))
    if packet is None:
        status = "UNAVAILABLE" if investigation.review_packet_status == "UNAVAILABLE" else "NOT_ISSUED"
        return {"packet_status": status, "reason": investigation.review_packet_reason if status == "UNAVAILABLE" else "No immutable review packet has been issued for this investigation.", "review": None}
    consensus = _current_consensus_payload(session, packet)
    snapshot = json.loads(packet.snapshot_json)
    evidence = packet_semantic_evidence(snapshot)
    hypothesis = session.scalar(select(Hypothesis).where(Hypothesis.investigation_id == investigation.id).order_by(Hypothesis.attempt_number.desc(), Hypothesis.id.desc()))
    generated = dict(evidence["generated_test"])
    generated["hypothesis"] = hypothesis.statement if hypothesis else None
    evidence["generated_test"] = generated
    return {
        "packet_status": "AVAILABLE", "reason": None,
        "review": {"packet_version": packet.version, "evidence": evidence, "state": consensus["state"], "display_state": consensus["display_state"], "coverage": consensus["coverage"]},
    }


@router.get("/{investigation_id}/validation-explainer")
def validation_explainer(investigation_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    investigation = _get_investigation(session, investigation_id)
    artifacts = list(session.scalars(select(Artifact).where(Artifact.investigation_id == investigation.id).order_by(Artifact.created_at, Artifact.id)))
    return explain_validation(investigation, artifacts)


@router.get("/{investigation_id}/posting-eligibility")
def posting_eligibility(investigation_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    _get_investigation(session, investigation_id)
    result = PostingApprovalService(session).eligibility(investigation_id)
    # ORM objects are internal implementation details, not API payloads.
    return {key: value for key, value in result.items() if key not in {"packet", "consensus_snapshot"}}


@router.get("/{investigation_id}/posting-approvals")
def list_posting_approvals(investigation_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    _get_investigation(session, investigation_id)
    approvals = list(session.scalars(select(PostingApproval).where(PostingApproval.investigation_id == investigation_id).order_by(PostingApproval.created_at, PostingApproval.id)))
    return {"items": [_posting_approval_payload(item) for item in approvals]}


@router.post("/{investigation_id}/posting-approvals", status_code=status.HTTP_201_CREATED)
def create_posting_approval(investigation_id: str, payload: PostingApprovalCreate, request: Request, x_pilot_reviewer: str | None = Header(default=None), x_pilot_review_token: str | None = Header(default=None), session: Session = Depends(get_session)) -> dict[str, object]:
    settings = Settings()
    if not settings.pilot_review_enabled:
        raise HTTPException(status_code=404, detail="Not found")
    reviewer = _pilot_reviewer(request, settings, x_pilot_reviewer, x_pilot_review_token)
    try:
        approval = PostingApprovalService(session).create(investigation_id, reviewer, rationale=payload.rationale, ttl_seconds=settings.posting_approval_ttl_seconds)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from None
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    return _posting_approval_payload(approval)


@review_packets_router.get("/{packet_id}")
def get_review_packet(packet_id: str, request: Request, x_pilot_reviewer: str | None = Header(default=None), x_pilot_review_token: str | None = Header(default=None), session: Session = Depends(get_session)) -> dict[str, object]:
    packet = session.get(ReviewPacket, packet_id)
    if packet is None:
        raise HTTPException(status_code=404, detail="Review packet not found")
    settings = Settings()
    if not settings.pilot_review_enabled:
        raise HTTPException(status_code=404, detail="Not found")
    reviewer = _pilot_reviewer(request, settings, x_pilot_reviewer, x_pilot_review_token)
    _require_packet_scope(session, packet, reviewer)
    return {**_review_packet_payload(packet), "current_consensus": _current_consensus_payload(session, packet)}


@review_packets_router.get("/{packet_id}/assessments")
def list_packet_assessments(packet_id: str, request: Request, x_pilot_reviewer: str | None = Header(default=None), x_pilot_review_token: str | None = Header(default=None), session: Session = Depends(get_session)) -> dict[str, object]:
    packet = session.get(ReviewPacket, packet_id)
    if packet is None:
        raise HTTPException(status_code=404, detail="Review packet not found")
    settings = Settings()
    if not settings.pilot_review_enabled:
        raise HTTPException(status_code=404, detail="Not found")
    reviewer = _pilot_reviewer(request, settings, x_pilot_reviewer, x_pilot_review_token)
    _require_packet_scope(session, packet, reviewer)
    assessments = list(session.scalars(select(ReviewAssessment).where(ReviewAssessment.review_packet_id == packet_id).order_by(ReviewAssessment.created_at, ReviewAssessment.id)))
    return {"items": [_assessment_payload(item) for item in assessments]}


@review_packets_router.get("/{packet_id}/consensus-history")
def list_consensus_history(packet_id: str, request: Request, x_pilot_reviewer: str | None = Header(default=None), x_pilot_review_token: str | None = Header(default=None), session: Session = Depends(get_session)) -> dict[str, object]:
    packet = session.get(ReviewPacket, packet_id)
    if packet is None:
        raise HTTPException(status_code=404, detail="Review packet not found")
    settings = Settings()
    if not settings.pilot_review_enabled:
        raise HTTPException(status_code=404, detail="Not found")
    reviewer = _pilot_reviewer(request, settings, x_pilot_reviewer, x_pilot_review_token)
    _require_packet_scope(session, packet, reviewer)
    snapshots = list(session.scalars(select(ReviewConsensusSnapshot).where(ReviewConsensusSnapshot.review_packet_id == packet_id).order_by(ReviewConsensusSnapshot.computed_at, ReviewConsensusSnapshot.id)))
    return {"items": [_consensus_snapshot_payload(item) for item in snapshots]}


@review_packets_router.post("/{packet_id}/assessments", status_code=status.HTTP_201_CREATED)
def create_packet_assessment(
    packet_id: str, payload: AssessmentCreate, request: Request, x_pilot_reviewer: str | None = Header(default=None),
    x_pilot_review_token: str | None = Header(default=None), session: Session = Depends(get_session),
) -> dict[str, object]:
    settings = Settings()
    # A disabled pilot deliberately exposes no internal write capability.
    if not settings.pilot_review_enabled:
        raise HTTPException(status_code=404, detail="Not found")
    reviewer = _pilot_reviewer(request, settings, x_pilot_reviewer, x_pilot_review_token)
    packet = session.get(ReviewPacket, packet_id)
    if packet is None:
        raise HTTPException(status_code=404, detail="Review packet not found")
    _require_packet_scope(session, packet, reviewer)
    try:
        assessment = ReviewAssessmentService(session).create(packet_id, reviewer, **payload.model_dump())
    except ValueError as error:
        # Never disclose registry or token configuration; ordinary input errors are safe.
        raise HTTPException(status_code=409 if "active assessment" in str(error) else 422, detail=str(error)) from None
    return _assessment_payload(assessment)


@pilot_router.get("/packets/{packet_id}")
def pilot_packet_detail(packet_id: str, request: Request, x_pilot_reviewer: str | None = Header(default=None), x_pilot_review_token: str | None = Header(default=None), session: Session = Depends(get_session)) -> dict[str, object]:
    """Authenticated, repository-scoped reviewer evidence view."""
    settings = Settings()
    if not settings.pilot_review_enabled:
        raise HTTPException(status_code=404, detail="Not found")
    reviewer = _pilot_reviewer(request, settings, x_pilot_reviewer, x_pilot_review_token)
    packet = session.get(ReviewPacket, packet_id)
    if packet is None:
        raise HTTPException(status_code=404, detail="Review packet not found")
    investigation = _require_packet_scope(session, packet, reviewer)
    consensus = _current_consensus_payload(session, packet)
    evidence = packet_semantic_evidence(json.loads(packet.snapshot_json))
    hypothesis = session.scalar(select(Hypothesis).where(Hypothesis.investigation_id == investigation.id).order_by(Hypothesis.attempt_number.desc(), Hypothesis.id.desc()))
    generated = dict(evidence["generated_test"]); generated["hypothesis"] = hypothesis.statement if hypothesis else None; evidence["generated_test"] = generated
    return {"packet": {"id": packet.id, "version": packet.version, "investigation_id": investigation.id, "repository": investigation.repository, "issue_number": investigation.issue_number, "issue_title": investigation.issue_title, "evidence": evidence, "state": consensus["state"], "display_state": consensus["display_state"], "coverage": consensus["coverage"]}}




@router.get("/{investigation_id}/timeline")
def get_timeline(investigation_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    investigation = _get_investigation(session, investigation_id)
    hypotheses = list(
        session.scalars(
            select(Hypothesis)
            .where(Hypothesis.investigation_id == investigation.id)
            .order_by(Hypothesis.attempt_number)
        )
    )
    artifacts = list(session.scalars(select(Artifact).where(Artifact.investigation_id == investigation.id)))
    proof_by_attempt: dict[int, str] = {}
    for artifact in artifacts:
        if artifact.kind != "proof_integrity_report": continue
        try:
            part = next(part for part in artifact.path.split("/") if part.startswith("attempt_"))
            report = json.loads(Path(artifact.path).read_text(encoding="utf-8"))
            proof_by_attempt[int(part.removeprefix("attempt_"))] = str(report.get("result", "UNAVAILABLE"))
        except (OSError, StopIteration, ValueError, json.JSONDecodeError):
            continue
    artifact_attempts = {
        int(part.removeprefix("attempt_"))
        for artifact in artifacts
        for part in artifact.path.split("/")
        if part.startswith("attempt_") and part.removeprefix("attempt_").isdigit()
    }
    return {
        "items": [
            {
                "attempt_number": hypothesis.attempt_number,
                "hypothesis": hypothesis.statement,
                "revision_reason": hypothesis.revision_reason,
                "action": "Codex investigation and pytest execution",
                "result": "Rejected proof pattern" if proof_by_attempt.get(hypothesis.attempt_number) == "REJECTED_PROOF_PATTERN" else "Proof review flagged" if proof_by_attempt.get(hypothesis.attempt_number) == "REVIEW_FLAGGED" else "Evidence captured" if hypothesis.attempt_number in artifact_attempts else "Evidence unavailable",
                "duration_ms": None,
            }
            for hypothesis in hypotheses
        ]
    }


@router.get("/{investigation_id}/related")
def related_investigations(investigation_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    investigation = _get_investigation(session, investigation_id)
    rows = list(session.scalars(select(DuplicateCandidate).where((DuplicateCandidate.source_investigation_id == investigation.id) | (DuplicateCandidate.candidate_investigation_id == investigation.id)).order_by(DuplicateCandidate.similarity_score.desc())))
    items = []
    for row in rows:
        other_id = row.candidate_investigation_id if row.source_investigation_id == investigation.id else row.source_investigation_id
        other = session.get(Investigation, other_id)
        if other is None:
            continue
        items.append({"investigation_id": other.id, "repository": other.repository, "issue_number": other.issue_number, "classification": other.classification.value if other.classification else None, "status": other.status.value, "similarity_score": float(row.similarity_score), "matched_signals": json.loads(row.matched_signals), "label": "Potentially related investigation"})
    document = session.scalar(select(SimilarityDocument).where(SimilarityDocument.investigation_id == investigation.id))
    return {"items": items, "available": document is not None, "reason": None if document else "Duplicate analysis unavailable: no completed similarity document"}


@router.get("/{investigation_id}/summary")
def get_summary(investigation_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    investigation = _get_investigation(session, investigation_id)
    attempts = session.scalar(
        select(func.count()).select_from(Hypothesis).where(Hypothesis.investigation_id == investigation.id)
    ) or 0
    calls = list(session.scalars(select(LLMCall).where(LLMCall.investigation_id == investigation.id)))
    tracked_metrics = _tracked_llm_metrics(calls)
    payload = {
        **_investigation_payload(investigation, attempts, tracked_metrics=tracked_metrics),
        "total_duration_seconds": _duration_seconds(investigation),
        "input_tokens": tracked_metrics["tracked_llm_api_input_tokens"],
        "cached_input_tokens": tracked_metrics["tracked_llm_api_cached_input_tokens"],
        "output_tokens": tracked_metrics["tracked_llm_api_output_tokens"],
        "total_tokens": (
            int(tracked_metrics["tracked_llm_api_input_tokens"]) + int(tracked_metrics["tracked_llm_api_output_tokens"])
            if tracked_metrics["tracked_llm_api_input_tokens"] is not None else None
        ),
        "cache_hit_percent": (
            round((int(tracked_metrics["tracked_llm_api_cached_input_tokens"]) / int(tracked_metrics["tracked_llm_api_input_tokens"])) * 100, 2)
            if tracked_metrics["tracked_llm_api_input_tokens"] else None
        ),
        "latency_ms": tracked_metrics["tracked_llm_api_latency_ms"],
    }
    job = session.scalar(select(WebhookJob).where(WebhookJob.investigation_id == investigation.id))
    if job is not None:
        payload["webhook_job"] = _webhook_job_payload(job)
    has_manifest = session.scalar(select(func.count()).select_from(Artifact).where(Artifact.investigation_id == investigation.id, Artifact.kind == "reproducibility_manifest")) or 0
    payload["reproducibility_status"] = ("STABLE" if investigation.asserts_failure and has_manifest else "NOT_CONFIRMED" if has_manifest else "LEGACY")
    return payload
