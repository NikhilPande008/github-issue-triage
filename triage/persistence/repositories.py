from decimal import Decimal
from typing import Generic, TypeVar

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import and_, func, or_, select, update
from triage.domain.enums import InvestigationStatus, JobSource, WebhookJobStatus
from triage.llm.pricing import OPENAI_PROVIDER
from sqlalchemy.orm import Session

from triage.persistence.models import Artifact, Hypothesis, Investigation, LLMCall, WebhookJob

ModelT = TypeVar("ModelT")


class Repository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, session: Session):
        self.session = session

    def create(self, item: ModelT) -> ModelT:
        self.session.add(item)
        self.session.commit()
        self.session.refresh(item)
        return item

    def get(self, item_id: str) -> ModelT | None:
        return self.session.get(self.model, item_id)

    def list(self) -> list[ModelT]:
        return list(self.session.scalars(select(self.model)))

    def update(self, item: ModelT, **values: object) -> ModelT:
        for name, value in values.items():
            setattr(item, name, value)
        self.session.commit()
        self.session.refresh(item)
        return item

    def delete(self, item: ModelT) -> None:
        self.session.delete(item)
        self.session.commit()


class InvestigationRepository(Repository[Investigation]):
    model = Investigation

    def processed_issue_numbers(self, repository: str) -> set[int]:
        """Terminal runs are skipped by default; interrupted runs may be retried."""
        statement = select(Investigation.issue_number).where(
            Investigation.repository == repository,
            Investigation.status.in_([
                InvestigationStatus.COMPLETED,
                InvestigationStatus.COMPLETED_NO_GAP,
                InvestigationStatus.FAILED,
            ]),
        )
        return set(self.session.scalars(statement))


class HypothesisRepository(Repository[Hypothesis]):
    model = Hypothesis


class ArtifactRepository(Repository[Artifact]):
    model = Artifact


class LLMCallRepository(Repository[LLMCall]):
    model = LLMCall

    def tracked_cost_usd(self, investigation_id: str) -> float | None:
        """Return only fully priced, linked OpenAI API cost for terminal reporting."""
        costs = list(
            self.session.scalars(
                select(LLMCall.cost_usd).where(
                    LLMCall.investigation_id == investigation_id,
                    LLMCall.provider == OPENAI_PROVIDER,
                )
            )
        )
        if not costs or any(cost is None for cost in costs):
            return None
        return float(sum((Decimal(cost) for cost in costs), Decimal("0")))


class WebhookJobRepository(Repository[WebhookJob]):
    model = WebhookJob

    def by_delivery_id(self, delivery_id: str) -> WebhookJob | None:
        return self.session.scalar(select(WebhookJob).where(WebhookJob.delivery_id == delivery_id))

    def queue_depth(self) -> int:
        return int(self.session.scalar(select(func.count()).select_from(WebhookJob).where(WebhookJob.status.in_([WebhookJobStatus.QUEUED, WebhookJobStatus.RETRY_SCHEDULED]))) or 0)

    def enqueue_batch(self, repository: str, issue_number: int, priority: int = 0, max_attempts: int = 3) -> WebhookJob:
        # A synthetic, stable idempotency key makes batch and webhook work share
        # the same queue contract without colliding with GitHub delivery IDs.
        delivery_id = f"batch:{repository.lower()}:{issue_number}"
        existing = self.by_delivery_id(delivery_id)
        if existing is not None:
            return existing
        return self.create(WebhookJob(delivery_id=delivery_id, source=JobSource.BATCH, repository=repository, issue_number=issue_number, event="batch", action="enqueue", priority=priority, max_attempts=max_attempts))

    def recover_expired_leases(self, now: datetime | None = None) -> int:
        now = now or datetime.now(timezone.utc)
        expired = list(self.session.scalars(select(WebhookJob).where(WebhookJob.status == WebhookJobStatus.RUNNING, WebhookJob.lease_expires_at < now)))
        for job in expired:
            status = WebhookJobStatus.DEAD_LETTER if job.attempt_count >= job.max_attempts else WebhookJobStatus.RETRY_SCHEDULED
            job.status, job.lease_owner, job.lease_expires_at = status, None, None
            job.error_reason = "Worker lease expired"
            job.next_eligible_at = now if status == WebhookJobStatus.RETRY_SCHEDULED else None
        self.session.commit()
        return len(expired)

    def claim_next(self, owner: str, lease_seconds: int, per_repository_limit: int = 1) -> WebhookJob | None:
        """Atomically compare-and-set a claim; PostgreSQL can add SKIP LOCKED later.

        SQLite is safe for local single-host workers because the conditional
        update is the authority. It is not represented as multi-host scaling.
        """
        now = datetime.now(timezone.utc)
        self.recover_expired_leases(now)
        eligible = and_(
            WebhookJob.status.in_([WebhookJobStatus.QUEUED, WebhookJobStatus.RETRY_SCHEDULED]),
            or_(WebhookJob.next_eligible_at.is_(None), WebhookJob.next_eligible_at <= now),
        )
        candidates = list(self.session.scalars(select(WebhookJob).where(eligible).order_by(WebhookJob.priority.desc(), WebhookJob.created_at).limit(20)))
        for candidate in candidates:
            running_for_repo = self.session.scalar(select(func.count()).select_from(WebhookJob).where(WebhookJob.repository == candidate.repository, WebhookJob.status == WebhookJobStatus.RUNNING)) or 0
            if running_for_repo >= per_repository_limit:
                continue
            claimed = self.session.execute(
                update(WebhookJob).where(WebhookJob.id == candidate.id, eligible).values(
                    status=WebhookJobStatus.RUNNING, lease_owner=owner,
                    lease_expires_at=now + timedelta(seconds=lease_seconds),
                    started_at=now, attempt_count=WebhookJob.attempt_count + 1,
                )
            )
            self.session.commit()
            if claimed.rowcount:
                return self.session.get(WebhookJob, candidate.id)
        return None

    def finish(self, job: WebhookJob, status: WebhookJobStatus, **values: object) -> WebhookJob:
        if job.status != WebhookJobStatus.RUNNING:
            raise ValueError(f"Cannot finish job in {job.status}")
        if status not in {WebhookJobStatus.SUCCEEDED, WebhookJobStatus.FAILED, WebhookJobStatus.RETRY_SCHEDULED, WebhookJobStatus.DEAD_LETTER, WebhookJobStatus.CANCELLED}:
            raise ValueError(f"Invalid terminal transition to {status}")
        values.setdefault("lease_owner", None)
        values.setdefault("lease_expires_at", None)
        if status in {WebhookJobStatus.SUCCEEDED, WebhookJobStatus.FAILED, WebhookJobStatus.DEAD_LETTER, WebhookJobStatus.CANCELLED}:
            values.setdefault("completed_at", datetime.now(timezone.utc))
        return self.update(job, status=status, **values)
