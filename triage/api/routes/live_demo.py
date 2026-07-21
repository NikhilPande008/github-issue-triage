"""Operator-enabled, durable live-demo queue surface.

Handlers only validate/enqueue; no provider, Docker, or GitHub work occurs here.
"""
from __future__ import annotations

import hmac
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from triage.api.routes.investigations import get_session
from triage.config.settings import Settings
from triage.domain.enums import CommentStatus, JobSource, WebhookJobStatus
from triage.persistence.models import WebhookJob
from triage.persistence.repositories import WebhookJobRepository

router = APIRouter(prefix="/demo/live", tags=["live-demo"])


class LiveDemoRequest(BaseModel):
    repository: str
    issue_number: int
    confirm_live_run: bool = False


def _config(settings: Settings) -> tuple[set[str], set[int]]:
    return settings.live_demo_repository_allowlist(), settings.live_demo_issue_allowlist()


def _available_reason(settings: Settings) -> str | None:
    repositories, issues = _config(settings)
    if not settings.live_demo_enabled: return "Live demo is disabled for this deployment."
    if not repositories or not issues: return "Live demo allowlists are not configured."
    return None


def _capacity(session: Session, settings: Settings) -> bool:
    count = session.scalar(select(func.count()).select_from(WebhookJob).where(
        WebhookJob.source == JobSource.LIVE_DEMO,
        WebhookJob.status.in_([WebhookJobStatus.QUEUED, WebhookJobStatus.RETRY_SCHEDULED, WebhookJobStatus.RUNNING]),
    )) or 0
    return count < settings.live_demo_max_concurrent_runs


@router.get("/config")
def config() -> dict[str, object]:
    settings = Settings(); repositories, issues = _config(settings); reason = _available_reason(settings)
    return {"enabled": reason is None, "repositories": sorted(repositories), "issue_numbers": sorted(issues), "max_concurrent_runs": settings.live_demo_max_concurrent_runs, "reason": reason}


@router.post("/investigations", status_code=status.HTTP_202_ACCEPTED)
def enqueue(payload: LiveDemoRequest, request_token: str | None = Header(None, alias="X-Live-Demo-Token"), session: Session = Depends(get_session)) -> dict[str, str]:
    settings = Settings(); reason = _available_reason(settings)
    if reason: raise HTTPException(status_code=404, detail=reason)
    repositories, issues = _config(settings)
    if payload.repository.lower() not in repositories or payload.issue_number not in issues:
        raise HTTPException(status_code=403, detail="Repository or issue is not allowlisted for this live demo.")
    if not payload.confirm_live_run:
        raise HTTPException(status_code=400, detail="Explicit live-run acknowledgement is required.")
    if settings.live_demo_request_token and not (request_token and hmac.compare_digest(request_token, settings.live_demo_request_token)):
        raise HTTPException(status_code=401, detail="A valid live-demo request token is required.")
    existing = session.scalar(select(WebhookJob).where(WebhookJob.source == JobSource.LIVE_DEMO, WebhookJob.repository == payload.repository, WebhookJob.issue_number == payload.issue_number, WebhookJob.status.in_([WebhookJobStatus.QUEUED, WebhookJobStatus.RUNNING, WebhookJobStatus.RETRY_SCHEDULED])).order_by(WebhookJob.created_at.desc()))
    if existing: return {"id": existing.id, "status": "queued"}
    if not _capacity(session, settings): raise HTTPException(status_code=429, detail="Live-demo capacity is currently full.")
    job = WebhookJob(delivery_id=f"live-demo:{uuid4()}", source=JobSource.LIVE_DEMO, repository=payload.repository, issue_number=payload.issue_number, event="live_demo", action="operator_request", max_attempts=1, status=WebhookJobStatus.QUEUED, comment_status=CommentStatus.SKIPPED, comment_reason="Live demo never creates GitHub comments", progress_stage="queued", progress_detail="Queued for bounded live investigation")
    WebhookJobRepository(session).create(job)
    return {"id": job.id, "status": "queued"}


@router.get("/investigations/{job_id}")
def progress(job_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    job = session.get(WebhookJob, job_id)
    if job is None or job.source != JobSource.LIVE_DEMO: raise HTTPException(status_code=404, detail="Live-demo run not found")
    terminal = job.status in {WebhookJobStatus.SUCCEEDED, WebhookJobStatus.FAILED, WebhookJobStatus.DEAD_LETTER, WebhookJobStatus.CANCELLED}
    return {"id": job.id, "status": str(job.status).lower(), "stage": job.progress_stage or "queued", "detail": job.progress_detail or "Queued for bounded live investigation", "terminal": terminal, "investigation_id": job.investigation_id}
