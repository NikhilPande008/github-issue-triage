import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from triage.api.main import app
from triage.api.routes.investigations import get_session
from triage.config.settings import Settings
from triage.domain.enums import Classification, CommentStatus, InvestigationStatus, WebhookJobStatus
from triage.persistence.database import Base, create_engine_from_url
from triage.persistence.models import Investigation, WebhookJob
from triage.webhook.worker import WebhookWorker


def _signed(secret: str, payload: dict) -> tuple[bytes, str]:
    body = json.dumps(payload).encode()
    return body, "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _payload(**issue) -> dict:
    return {"action": "opened", "repository": {"full_name": "owner/repo"}, "issue": {"number": 9, **issue}}


def test_webhook_requires_signature_and_deduplicates(tmp_path, monkeypatch) -> None:
    db_url = f"sqlite:///{tmp_path / 'triage.db'}"
    engine = create_engine_from_url(db_url)
    Base.metadata.create_all(engine)
    from sqlalchemy.orm import sessionmaker
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "test-secret")
    monkeypatch.setenv("WEBHOOK_ALLOWED_REPOSITORIES", "owner/repo")
    def session_override():
        with factory() as session:
            yield session
    app.dependency_overrides[get_session] = session_override
    try:
        client = TestClient(app)
        body, signature = _signed("test-secret", _payload())
        headers = {"X-Hub-Signature-256": signature, "X-GitHub-Event": "issues", "X-GitHub-Delivery": "d1"}
        assert client.post("/webhooks/github", content=body, headers=headers).status_code == 202
        assert client.post("/webhooks/github", content=body, headers=headers).json()["duplicate"] is True
        assert client.post("/webhooks/github", content=body, headers={"X-GitHub-Event": "issues"}).status_code == 401
        with factory() as session:
            assert session.query(WebhookJob).count() == 1
    finally:
        app.dependency_overrides.clear()


def test_worker_dry_run_creates_preview_without_write(tmp_path) -> None:
    engine = create_engine_from_url(f"sqlite:///{tmp_path / 'triage.db'}")
    Base.metadata.create_all(engine)
    from sqlalchemy.orm import sessionmaker
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        investigation = Investigation(repository="owner/repo", issue_number=1, status=InvestigationStatus.COMPLETED,
                                      classification=Classification.BEHAVIOR_GAP_CONFIRMED, validation_reason="focused test fails")
        session.add(investigation)
        session.commit()
        session.add(WebhookJob(delivery_id="d", repository="owner/repo", issue_number=1, event="issues", action="opened", status=WebhookJobStatus.QUEUED))
        session.commit()
        investigation_id = investigation.id

    class NeverWrite:
        def __init__(self, *args): pass
        def create_issue_comment(self, *args): raise AssertionError("must not post in dry-run")

    settings = Settings(github_auto_post_enabled=True, github_auto_post_dry_run=True, github_auto_post_repositories="owner/repo")
    assert WebhookWorker(settings, factory, process_issue=lambda *_: investigation_id, github_client_factory=NeverWrite).run_once()
    with factory() as session:
        job = session.query(WebhookJob).one()
        assert job.status == WebhookJobStatus.SUCCEEDED
        assert job.comment_status == CommentStatus.PROPOSED
        assert job.proposed_comment_body is not None


def test_worker_requires_per_result_approval_before_write(tmp_path) -> None:
    engine = create_engine_from_url(f"sqlite:///{tmp_path / 'approval.db'}")
    Base.metadata.create_all(engine)
    from sqlalchemy.orm import sessionmaker
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        investigation = Investigation(repository="owner/repo", issue_number=1, status=InvestigationStatus.COMPLETED, classification=Classification.NEEDS_INFO)
        session.add(investigation); session.commit()
        session.add(WebhookJob(delivery_id="approval", repository="owner/repo", issue_number=1, event="issues", action="opened", status=WebhookJobStatus.QUEUED)); session.commit()
        investigation_id = investigation.id
    class NeverWrite:
        def __init__(self, *args): pass
        def create_issue_comment(self, *args): raise AssertionError("approval is required")
    settings = Settings(github_auto_post_enabled=True, github_auto_post_dry_run=False, github_auto_post_repositories="owner/repo")
    assert WebhookWorker(settings, factory, process_issue=lambda *_: investigation_id, github_client_factory=NeverWrite).run_once()
    with factory() as session:
        job = session.query(WebhookJob).one()
        assert job.comment_status == CommentStatus.REVIEW_REQUIRED
        assert job.proposed_comment_body is not None
