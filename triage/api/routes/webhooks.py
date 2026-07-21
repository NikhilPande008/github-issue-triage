"""GitHub webhook ingress.  This module must never execute investigations."""

import hashlib
import hmac
import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from triage.api.routes.investigations import get_session
from triage.config.settings import Settings
from triage.domain.enums import CommentStatus, JobSource, WebhookJobStatus
from triage.persistence.models import WebhookJob
from triage.persistence.repositories import WebhookJobRepository

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def verify_github_signature(body: bytes, signature: str | None, secret: str | None) -> bool:
    """Authenticate raw bytes before JSON parsing; malformed values are false."""
    if not secret or not signature or not signature.startswith("sha256="):
        return False
    provided = signature.removeprefix("sha256=")
    if len(provided) != 64 or any(char not in "0123456789abcdefABCDEF" for char in provided):
        return False
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, provided)


@router.post("/github", status_code=status.HTTP_202_ACCEPTED)
async def github_webhook(request: Request, session: Session = Depends(get_session)) -> dict[str, object]:
    settings = Settings()
    body = await request.body()
    if not verify_github_signature(body, request.headers.get("X-Hub-Signature-256"), settings.github_webhook_secret):
        # Do not expose details that help a signature oracle and never log headers/body.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature")

    event = request.headers.get("X-GitHub-Event")
    delivery_id = request.headers.get("X-GitHub-Delivery")
    if event != "issues" or not delivery_id:
        return {"accepted": True, "created": False}
    try:
        payload = json.loads(body)
        repository = str(payload["repository"]["full_name"])
        issue = payload["issue"]
        action = str(payload["action"])
        issue_number = int(issue["number"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid issues webhook payload") from None

    # GitHub includes pull_request for issue-shaped PR payloads.
    if action != "opened" or "pull_request" in issue or repository.lower() not in settings.repository_allowlist():
        return {"accepted": True, "created": False}

    jobs = WebhookJobRepository(session)
    if jobs.by_delivery_id(delivery_id) is not None:
        return {"accepted": True, "created": False, "duplicate": True}
    if jobs.queue_depth() >= settings.worker_queue_limit:
        # The signed event is intentionally not discarded: GitHub may retry a
        # 429 delivery after capacity is restored.
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Triage queue is at capacity; retry delivery later")
    try:
        job = jobs.create(WebhookJob(
            delivery_id=delivery_id, repository=repository, issue_number=issue_number,
            event=event, action=action, source=JobSource.WEBHOOK, max_attempts=settings.worker_max_attempts,
            status=WebhookJobStatus.QUEUED, comment_status=CommentStatus.PENDING,
        ))
    except IntegrityError:
        session.rollback()
        return {"accepted": True, "created": False, "duplicate": True}
    return {"accepted": True, "created": True, "job_id": job.id}
