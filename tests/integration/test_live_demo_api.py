import asyncio

import httpx

from triage.api.main import app
from triage.api.routes.investigations import get_session
from triage.domain.enums import CommentStatus, JobSource, WebhookJobStatus
from triage.persistence.database import Base, create_session_factory
from triage.persistence.models import WebhookJob


def test_live_demo_is_disabled_by_default_and_only_enqueues_when_enabled(tmp_path, monkeypatch) -> None:
    factory = create_session_factory(f"sqlite:///{tmp_path / 'live.db'}"); Base.metadata.create_all(factory.kw["bind"])
    def override():
        with factory() as session: yield session
    app.dependency_overrides[get_session] = override
    async def request():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            monkeypatch.delenv("LIVE_DEMO_ENABLED", raising=False)
            assert (await client.get("/demo/live/config")).json()["enabled"] is False
            assert (await client.post("/demo/live/investigations", json={"repository": "owner/repo", "issue_number": 7, "confirm_live_run": True})).status_code == 404
            monkeypatch.setenv("LIVE_DEMO_ENABLED", "true"); monkeypatch.setenv("LIVE_DEMO_REPOSITORIES", "owner/repo"); monkeypatch.setenv("LIVE_DEMO_ALLOWED_ISSUE_NUMBERS", "7"); monkeypatch.setenv("LIVE_DEMO_REQUEST_TOKEN", "demo-token")
            config = (await client.get("/demo/live/config")).json()
            assert config == {"enabled": True, "repositories": ["owner/repo"], "issue_numbers": [7], "max_concurrent_runs": 1, "reason": None}
            assert "token" not in str(config).lower()
            assert (await client.post("/demo/live/investigations", json={"repository": "owner/repo", "issue_number": 8, "confirm_live_run": True}, headers={"X-Live-Demo-Token": "demo-token"})).status_code == 403
            assert (await client.post("/demo/live/investigations", json={"repository": "owner/repo", "issue_number": 7, "confirm_live_run": False}, headers={"X-Live-Demo-Token": "demo-token"})).status_code == 400
            assert (await client.post("/demo/live/investigations", json={"repository": "owner/repo", "issue_number": 7, "confirm_live_run": True})).status_code == 401
            response = await client.post("/demo/live/investigations", json={"repository": "owner/repo", "issue_number": 7, "confirm_live_run": True}, headers={"X-Live-Demo-Token": "demo-token"})
            assert response.status_code == 202 and "demo-token" not in response.text
            job_id = response.json()["id"]
            progress = (await client.get(f"/demo/live/investigations/{job_id}")).json()
            assert progress["stage"] == "queued" and progress["investigation_id"] is None
    try: asyncio.run(request())
    finally: app.dependency_overrides.clear()
    with factory() as session:
        job = session.query(WebhookJob).one()
        assert job.source == JobSource.LIVE_DEMO and job.comment_status == CommentStatus.SKIPPED
        assert job.proposed_comment_body is None and job.status == WebhookJobStatus.QUEUED


def test_live_demo_progress_is_bounded_and_links_only_an_investigation_id(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LIVE_DEMO_ENABLED", "true"); monkeypatch.setenv("LIVE_DEMO_REPOSITORIES", "owner/repo"); monkeypatch.setenv("LIVE_DEMO_ALLOWED_ISSUE_NUMBERS", "7")
    factory = create_session_factory(f"sqlite:///{tmp_path / 'progress.db'}"); Base.metadata.create_all(factory.kw["bind"])
    with factory() as session:
        job = WebhookJob(delivery_id="live-demo:test", source=JobSource.LIVE_DEMO, repository="owner/repo", issue_number=7, event="live_demo", action="operator_request", status=WebhookJobStatus.SUCCEEDED, comment_status=CommentStatus.SKIPPED, progress_stage="completed_outcome", progress_detail="Bounded investigation completed", investigation_id="investigation-1")
        session.add(job); session.commit(); job_id = job.id
    def override():
        with factory() as session: yield session
    app.dependency_overrides[get_session] = override
    async def request():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            body = (await client.get(f"/demo/live/investigations/{job_id}")).json()
            assert body == {"id": job_id, "status": "succeeded", "stage": "completed_outcome", "detail": "Bounded investigation completed", "terminal": True, "investigation_id": "investigation-1"}
    try: asyncio.run(request())
    finally: app.dependency_overrides.clear()
