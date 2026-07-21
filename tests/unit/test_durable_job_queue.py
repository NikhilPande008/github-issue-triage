from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import sessionmaker

from triage.domain.enums import WebhookJobStatus
from triage.persistence.database import Base, create_engine_from_url
from triage.persistence.models import WebhookJob
from triage.persistence.repositories import WebhookJobRepository


def _factory(tmp_path):
    engine = create_engine_from_url(f"sqlite:///{tmp_path / 'queue.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def test_claim_is_exclusive_and_per_repository_limited(tmp_path) -> None:
    factory = _factory(tmp_path)
    with factory() as session:
        jobs = WebhookJobRepository(session)
        jobs.enqueue_batch("owner/a", 1)
        jobs.enqueue_batch("owner/a", 2)
        jobs.enqueue_batch("owner/b", 1)
    with factory() as first, factory() as second:
        a = WebhookJobRepository(first).claim_next("one", 60, per_repository_limit=1)
        b = WebhookJobRepository(second).claim_next("two", 60, per_repository_limit=1)
        assert a is not None and b is not None
        assert {a.repository, b.repository} == {"owner/a", "owner/b"}
    with factory() as session:
        assert WebhookJobRepository(session).claim_next("three", 60, per_repository_limit=1) is None


def test_expired_lease_retries_then_dead_letters_at_limit(tmp_path) -> None:
    factory = _factory(tmp_path)
    with factory() as session:
        job = WebhookJobRepository(session).enqueue_batch("owner/a", 1, max_attempts=2)
        job.status = WebhookJobStatus.RUNNING
        job.attempt_count = 1
        job.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.commit()
        assert WebhookJobRepository(session).recover_expired_leases() == 1
        assert job.status == WebhookJobStatus.RETRY_SCHEDULED
        job.status = WebhookJobStatus.RUNNING
        job.attempt_count = 2
        job.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.commit()
        WebhookJobRepository(session).recover_expired_leases()
        assert job.status == WebhookJobStatus.DEAD_LETTER


def test_terminal_job_cannot_be_claimed_again(tmp_path) -> None:
    factory = _factory(tmp_path)
    with factory() as session:
        repo = WebhookJobRepository(session)
        repo.enqueue_batch("owner/a", 1)
        job = repo.claim_next("one", 60)
        assert job is not None
        repo.finish(job, WebhookJobStatus.SUCCEEDED)
        assert repo.claim_next("two", 60) is None
